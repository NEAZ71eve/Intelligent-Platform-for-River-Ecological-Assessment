import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageOps, PngImagePlugin
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from accounts.services import issue_session
from .models import Asset
from .services import create_asset


class UploadImageTests(TestCase):
    def setUp(self):
        cache.clear()
        directory = tempfile.TemporaryDirectory()
        self.directory = Path(directory.name)
        self.addCleanup(directory.cleanup)
        media = override_settings(MEDIA_ROOT=directory.name)
        media.enable()
        self.addCleanup(media.disable)
        self.user = User.objects.create_user(username='image-owner', password=None)

    def upload(self, image, format='PNG', **metadata):
        with io.BytesIO() as output:
            image.save(output, format=format, **metadata)
            return SimpleUploadedFile('fixture.' + format.lower(), output.getvalue())

    def assert_clean_jpeg(self, asset, variant, expected_size):
        with getattr(asset, variant).open('rb') as file, Image.open(file) as image:
            self.assertEqual(image.format, 'JPEG')
            self.assertEqual(image.mode, 'RGB')
            self.assertEqual(image.size, expected_size)
            self.assertFalse(image.getexif())
            for key in ('exif', 'icc_profile', 'comment', 'Description', 'XML:com.adobe.xmp'):
                self.assertNotIn(key, image.info)
            return image.copy()

    def test_twenty_megapixel_rgba_is_reduced_and_metadata_removed(self):
        # Highly compressible images can reach the allowed pixel limit below 5 MB.
        with Image.new('RGBA', (5000, 4000), (255, 0, 0, 0)) as image:
            image.paste((40, 100, 160, 255), (2500, 0, 5000, 4000))
            metadata = PngImagePlugin.PngInfo()
            metadata.add_text('Description', 'private-location-detail')
            exif = Image.Exif()
            exif[270] = 'private-photo-description'
            uploaded = self.upload(image, pnginfo=metadata, exif=exif,
                                   icc_profile=b'private-profile-marker')
        self.assertLess(uploaded.size, 5 * 1024 * 1024)
        asset = create_asset(self.user, uploaded, 'recognition')
        self.assertEqual((asset.width, asset.height), (2048, 1638))
        self.assertEqual(asset.byte_size, asset.original.size)
        for variant, size in (('original', (2048, 1638)), ('thumbnail', (480, 384))):
            with self.assert_clean_jpeg(asset, variant, size) as saved:
                self.assertTrue(all(channel >= 250 for channel in saved.getpixel((10, 10))))
                actual = saved.getpixel((size[0] - 10, 10))
                self.assertTrue(all(abs(left - right) <= 5 for left, right in zip(actual, (40, 100, 160))))

    def test_exif_rotation_matches_stored_dimensions_and_pixels(self):
        with Image.new('RGB', (3000, 1000), 'red') as image:
            image.paste('blue', (1500, 0, 3000, 1000))
            exif = Image.Exif()
            exif[274] = 6  # Rotate 90 degrees clockwise for display.
            exif[270] = 'private-photo-description'
            uploaded = self.upload(image, format='JPEG', exif=exif)
        asset = create_asset(self.user, uploaded, 'recognition')
        self.assertEqual((asset.width, asset.height), (683, 2048))
        for variant, size in (('original', (683, 2048)), ('thumbnail', (160, 480))):
            with self.assert_clean_jpeg(asset, variant, size) as saved:
                top = saved.getpixel((size[0] // 2, 10))
                bottom = saved.getpixel((size[0] // 2, size[1] - 10))
                self.assertGreater(top[0], 240)
                self.assertLess(top[2], 10)
                self.assertGreater(bottom[2], 240)
                self.assertLess(bottom[0], 10)

    def test_rgba_la_and_palette_transparency_use_white_background(self):
        for mode in ('RGBA', 'LA', 'P'):
            with self.subTest(mode=mode):
                if mode == 'RGBA':
                    image = Image.new(mode, (80, 60), (255, 0, 0, 0))
                    image.paste((0, 0, 0, 255), (40, 0, 80, 60))
                elif mode == 'LA':
                    image = Image.new(mode, (80, 60), (0, 0))
                    image.paste((0, 255), (40, 0, 80, 60))
                else:
                    image = Image.new(mode, (80, 60), 0)
                    image.putpalette([255, 0, 0, 0, 0, 0] + [0] * 762)
                    image.info['transparency'] = 0
                    image.paste(1, (40, 0, 80, 60))
                with image:
                    asset = create_asset(self.user, self.upload(image), 'recognition')
                for variant in ('original', 'thumbnail'):
                    with self.assert_clean_jpeg(asset, variant, (80, 60)) as saved:
                        self.assertTrue(all(channel >= 250 for channel in saved.getpixel((10, 10))))
                        self.assertTrue(all(channel <= 5 for channel in saved.getpixel((70, 10))))

    def test_account_deleted_during_decoding_returns_401_without_files(self):
        with Image.new('RGB', (80, 60), 'green') as image:
            uploaded = self.upload(image)
        token, _ = issue_session(self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        transpose = ImageOps.exif_transpose

        def delete_account_after_decode(image, **kwargs):
            result = transpose(image, **kwargs)
            User.objects.filter(pk=self.user.pk).delete()
            return result

        with patch('assets.services.ImageOps.exif_transpose', side_effect=delete_account_after_decode):
            response = client.post('/api/v1/uploads/', {'file': uploaded, 'purpose': 'recognition'}, format='multipart')
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['error']['code'], 'AUTH_REQUIRED')
        self.assertFalse(Asset.objects.exists())
        self.assertEqual(list(self.directory.rglob('*.jpg')), [])
