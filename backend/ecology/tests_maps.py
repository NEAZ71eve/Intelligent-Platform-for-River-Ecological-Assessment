"""Static images and relative coordinates share an immutable layout version."""
import io
from unittest.mock import Mock

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from .admin import MapLayoutAdmin
from .models import MapLayout, Place, Region
from .views import MapList

BUILTIN = '/assets/maps/demo-campus-v1.png'


class MapLayoutContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', no_observations=True, stdout=io.StringIO())

    def setUp(self):
        self.layout = MapLayout.objects.get(region__slug='demo-campus', version=1)

    def test_demo_seed_binds_builtin_dimensions_and_preserves_place_ratios(self):
        self.assertEqual((self.layout.image_url, self.layout.image_width, self.layout.image_height), (BUILTIN, 1000, 700))
        place = Place.objects.get(slug='clear-river')
        self.assertEqual(place.map_layout_id, self.layout.pk)
        self.assertEqual((place.x_ratio, place.y_ratio), (0.26, 0.48))
        call_command('seed_demo', no_observations=True, stdout=io.StringIO())
        self.assertEqual(MapLayout.objects.count(), 1)
        self.assertEqual(Place.objects.count(), 12)

    def test_existing_point_layout_cannot_relabel_coordinates_or_replace_image(self):
        other = Region.objects.create(slug='another', name='另一区域')
        changes = {'version': 2, 'image_width': 900, 'image_height': 900, 'region': other,
                   'image_url': 'https://example.org/replacement.png'}
        for field, value in changes.items():
            with self.subTest(field=field):
                layout = MapLayout.objects.get(pk=self.layout.pk)
                setattr(layout, field, value)
                with self.assertRaises(ValidationError):
                    layout.save()
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.image_url, BUILTIN)

    def test_new_layout_version_accepts_new_image_and_coordinates_require_same_region(self):
        layout = MapLayout.objects.create(region=self.layout.region, version=2, name='布局第二版',
                        image_url='https://example.org/map-v2.png', image_width=1400, image_height=900)
        point = Place.objects.create(region=layout.region, map_layout=layout, slug='new-point', name='新点位',
                                     kind='park', x_ratio=0.1, y_ratio=0.7)
        self.assertEqual(point.map_layout.version, 2)
        other = Region.objects.create(slug='elsewhere', name='其他区域')
        with self.assertRaises(ValidationError):
            Place.objects.create(region=other, map_layout=layout, slug='cross-point', name='错误点位', kind='park', x_ratio=0.1, y_ratio=0.2)

    def test_builtin_path_requires_exact_demo_region_version_and_dimensions(self):
        other = Region.objects.create(slug='another', name='另一区域')
        bad = [dict(region=other), dict(version=2), dict(image_width=1200), dict(image_height=500)]
        for changes in bad:
            with self.subTest(changes=changes):
                values = dict(region=self.layout.region, name='不匹配底图', version=99, image_url=BUILTIN)
                values.update(changes)
                with self.assertRaises(ValidationError):
                    MapLayout(**values).full_clean()

    def test_image_validation_rejects_unbound_paths_insecure_urls_and_invalid_sizes(self):
        bad = [{'image_url': value} for value in ['http://example.org/map.png', '/assets/maps/unapproved.png', 'javascript:alert(1)']]
        bad += [{field: value} for field in ('image_width', 'image_height') for value in (0, 8193)]
        bad += [{'version': 0}]
        for overrides in bad:
            with self.subTest(overrides=overrides):
                values = dict(region=self.layout.region, name='无点位新图', version=2)
                values.update(overrides)
                with self.assertRaises(ValidationError):
                    MapLayout(**values).full_clean()
        MapLayout(region=self.layout.region, version=2, name='等待上传图片').full_clean()

    def test_seed_upgrades_only_original_empty_placeholder_and_keeps_admin_customization(self):
        # Recreate the original M1 placeholder state without using the intentional write protection.
        MapLayout.objects.filter(pk=self.layout.pk).update(image_url='')
        call_command('seed_demo', no_observations=True, stdout=io.StringIO())
        self.layout.refresh_from_db()
        self.assertEqual(self.layout.image_url, BUILTIN)
        changes = [dict(image_url='https://example.org/admin.png'),
                   dict(image_url='', image_width=1200),
                   dict(image_url='', name='管理员编辑'),
                   dict(image_url='', attribution='管理员版权说明')]
        for change in changes:
            original = dict(image_url='', image_width=1000, image_height=700,
                            name='示范校园导览布局', attribution='HYHQ 原创示意布局，非实际地理地图。')
            original.update(change)
            MapLayout.objects.filter(pk=self.layout.pk).update(**original)
            call_command('seed_demo', no_observations=True, stdout=io.StringIO())
            layout = MapLayout.objects.get(pk=self.layout.pk)
            for field, value in original.items():
                self.assertEqual(getattr(layout, field), value)

    def test_seed_preserves_admin_place_edit_and_rejects_real_demo_namespace(self):
        place = Place.objects.get(slug='clear-river')
        place.x_ratio, place.y_ratio, place.is_published = 0.4, 0.5, False
        place.save()
        call_command('seed_demo', no_observations=True, stdout=io.StringIO())
        place.refresh_from_db()
        self.assertEqual((place.x_ratio, place.y_ratio, place.is_published), (0.4, 0.5, False))
        Region.objects.filter(pk=self.layout.region_id).update(is_demo=False)
        with self.assertRaises(CommandError):
            call_command('seed_demo', no_observations=True, stdout=io.StringIO())

    def test_public_map_points_are_published_and_tied_to_returned_version(self):
        layout = MapLayout.objects.create(region=self.layout.region, version=2, name='新图')
        Place.objects.create(region=layout.region, map_layout=layout, slug='v2-point', name='第二版点位', kind='park', x_ratio=0.2, y_ratio=0.3)
        Place.objects.filter(slug='clear-river').update(is_published=False)
        response = MapList.as_view()(APIRequestFactory().get('/api/v1/maps/'))
        self.assertEqual(response.status_code, 200)
        by_version = {item['version']: item for item in response.data['data']}
        self.assertEqual([p['slug'] for p in by_version[2]['points']], ['v2-point'])
        self.assertNotIn('clear-river', [p['slug'] for p in by_version[1]['points']])
        for item in by_version.values():
            self.assertTrue(all(str(point['map_layout']) == item['id'] for point in item['points']))
        layout.is_active = False
        layout.save()
        response = MapList.as_view()(APIRequestFactory().get('/api/v1/maps/'))
        self.assertEqual([item['version'] for item in response.data['data']], [1])

    def test_admin_freezes_bound_fields_but_allows_placeholder_image_binding(self):
        panel = MapLayoutAdmin(MapLayout, admin.site)
        self.assertEqual(set(panel.get_readonly_fields(Mock(), self.layout)),
                         {'region', 'version', 'image_width', 'image_height', 'image_url'})
        MapLayout.objects.filter(pk=self.layout.pk).update(image_url='')
        self.layout.refresh_from_db()
        self.assertNotIn('image_url', panel.get_readonly_fields(Mock(), self.layout))
        self.layout.image_url = BUILTIN
        self.layout.save()
        self.assertEqual(panel.get_readonly_fields(Mock()), ())
