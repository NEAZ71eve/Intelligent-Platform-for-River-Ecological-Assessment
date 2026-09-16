import io
import uuid
import warnings
from datetime import timedelta

from PIL import Image, ImageOps, UnidentifiedImageError
from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from common.exceptions import ServiceError
from .models import Asset


def create_asset(owner, uploaded, purpose):
    if uploaded.size > settings.MAX_UPLOAD_BYTES:
        raise ServiceError('图片不能超过 5MB', 'FILE_TOO_LARGE', 413)
    raw = uploaded.read(settings.MAX_UPLOAD_BYTES + 1)
    if len(raw) > settings.MAX_UPLOAD_BYTES:
        raise ServiceError('图片不能超过 5MB', 'FILE_TOO_LARGE', 413)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as source:
                if source.format not in {'JPEG', 'PNG', 'WEBP'} or getattr(source, 'is_animated', False):
                    raise ValueError('unsupported image')
                if source.width * source.height > settings.MAX_IMAGE_PIXELS:
                    raise ValueError('image dimensions too large')
                source.verify()
            with Image.open(io.BytesIO(raw)) as source:
                oriented = ImageOps.exif_transpose(source)
                # Rebuild pixel data: strips EXIF, GPS, comments and other metadata.
                clean = Image.new('RGB', oriented.size, 'white')
                if oriented.mode in ('RGBA', 'LA') or 'transparency' in oriented.info:
                    rgba = oriented.convert('RGBA')
                    clean.paste(rgba, mask=rgba.getchannel('A'))
                else:
                    clean.paste(oriented.convert('RGB'))
                clean.thumbnail((2048, 2048))
                width, height = clean.size
                original = io.BytesIO()
                clean.save(original, format='JPEG', quality=88)
                clean.thumbnail((480, 480))
                thumbnail = io.BytesIO()
                clean.save(thumbnail, format='JPEG', quality=82)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ServiceError('请上传有效的 JPG、PNG 或静态 WebP 图片（不超过 2000 万像素）', 'INVALID_IMAGE', 400) from None
    now = timezone.now()
    asset = Asset(owner=owner, purpose=purpose, width=width, height=height, byte_size=len(original.getvalue()),
                  original_expires_at=now + timedelta(hours=settings.ORIGINAL_RETENTION_HOURS),
                  expires_at=now + timedelta(hours=24) if purpose == 'avatar' else now + timedelta(days=settings.RECORD_RETENTION_DAYS))
    try:
        with transaction.atomic():
            # Serialize per-user quota checks so concurrent uploads cannot bypass the cap.
            type(owner).objects.select_for_update().get(pk=owner.pk)
            if Asset.objects.filter(owner=owner).count() >= 100:
                raise ServiceError('图片存储数量已达上限，请先删除旧记录', 'STORAGE_QUOTA', 429)
            name = f'{uuid.uuid4().hex}.jpg'
            asset.original.save(name, ContentFile(original.getvalue()), save=False)
            asset.thumbnail.save(name, ContentFile(thumbnail.getvalue()), save=False)
            asset.save()
    except Exception:
        for field in (asset.original, asset.thumbnail):
            if field.name:
                field.storage.delete(field.name)
        raise
    return asset

