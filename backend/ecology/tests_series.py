"""Public series contract: bounded complete windows, provenance and visibility."""
import io
from datetime import datetime, timedelta, timezone as datetime_timezone
from uuid import uuid4

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from assessments.views import WaterBodyList
from .models import DataSource, Metric, Observation, Place, Region, SimulationRun, SimulationScenario, Station
from .series import ObservationSeries, SimulationRunList
from .simulation import observation_key
from .views import ObservationList, SourceList, StationList

START = datetime(2026, 9, 1, tzinfo=datetime_timezone.utc)


class SeriesContractTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_demo', no_observations=True, stdout=io.StringIO())
        cls.station = Station.objects.get(code='demo-water-01')
        cls.metric = Metric.objects.get(code='ph')
        cls.source = DataSource.objects.get(code='demo-normal')
        cls.scenario = SimulationScenario.objects.get(code='normal')
        cls.batch = SimulationRun.objects.create(key='series-baseline', source=cls.source, scenario=cls.scenario,
                                               start=START, end=START + timedelta(days=31), seed=1, status='succeeded')

    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()

    def row(self, value, offset=0, quality='valid', **overrides):
        fields = dict(station=self.station, metric=self.metric, source=self.source, simulation_run=self.batch,
                      value=value, quality_status=quality, observed_at=START + timedelta(seconds=offset))
        fields.update(overrides)
        fields['dedupe_key'] = observation_key(fields['station'], fields['metric'], fields['source'], fields['observed_at'], fields['simulation_run'])
        return Observation.objects.create(**fields)

    def get(self, view=ObservationSeries, **params):
        return view.as_view()(self.factory.get('/api/v1/test/', params))

    def query(self, **params):
        return self.get(station=self.station.code, metrics='ph', start=START.isoformat(),
                        end=(START + timedelta(hours=4)).isoformat(), **params)

    def test_complete_window_includes_gaps_and_preserves_zero_suspect_missing(self):
        self.row(0)
        self.row(None, 3600, 'missing')
        self.row(12, 7200, 'suspect')
        response = self.query(max_points=4)
        self.assertEqual(response.status_code, 200, response.data)
        result = response.data['series'][0]
        self.assertEqual(result['metric']['unit'], 'pH')
        self.assertEqual([p['at'] for p in result['points']], [START + timedelta(hours=i) for i in range(4)])
        self.assertEqual([p['value'] for p in result['points']], [0, None, None, None])
        self.assertEqual([p['quality_status'] for p in result['points']], ['valid', 'missing', 'suspect', 'missing'])
        self.assertEqual(result['summary'], dict(valid_count=1, missing_count=1, suspect_count=1, min=0, max=0, mean=0))
        self.assertEqual(result['latest']['value'], 12)
        self.assertEqual(result['latest']['quality_status'], 'suspect')
        self.assertEqual(response.data['simulation_run_id'], str(self.batch.pk))

    def test_aggregation_spans_full_window_and_statistics_use_raw_valid_observations(self):
        self.row(0)
        self.row(2, 60)
        self.row(10, 3 * 3600)
        response = self.query(max_points=2)
        result = response.data['series'][0]
        self.assertEqual([p['value'] for p in result['points']], [1, 10])
        self.assertEqual(result['summary']['mean'], 4)  # Not the unweighted bucket mean 5.5.
        self.assertEqual(result['summary']['valid_count'], 3)
        self.assertEqual(result['latest']['observed_at'], START + timedelta(hours=3))
        self.assertEqual(response.data['window']['end'], START + timedelta(hours=4))

    def test_mixed_quality_bucket_remains_a_gap_but_retains_valid_extrema(self):
        self.row(0)
        self.row(4, 60)
        self.row(None, 120, 'missing')
        self.row(9, 180, 'suspect')
        point = self.query(max_points=1).data['series'][0]['points'][0]
        self.assertIsNone(point['value'])
        self.assertEqual((point['quality_status'], point['min'], point['max']), ('suspect', 0, 4))
        self.assertEqual((point['valid_count'], point['missing_count'], point['suspect_count']), (2, 1, 1))

    def test_empty_window_returns_full_missing_grid_and_unavailable_status(self):
        self.row(7)
        response = self.get(station=self.station.code, metrics='ph', start=(START + timedelta(days=2)).isoformat(),
                            end=(START + timedelta(days=2, hours=1)).isoformat(), max_points=4)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'unavailable')
        series = response.data['series'][0]
        self.assertIsNone(series['latest'])
        self.assertIsNone(series['summary']['mean'])
        self.assertEqual(len(series['points']), 4)
        self.assertTrue(all(p['quality_status'] == 'missing' and p['value'] is None for p in series['points']))

    def test_half_open_window_excludes_end_boundary(self):
        self.row(3)
        self.row(5, 4 * 3600)
        self.assertEqual(self.query().data['series'][0]['summary']['valid_count'], 1)

    def test_default_window_anchors_to_latest_selected_history_not_wall_clock(self):
        self.row(4, 3600)
        self.row(5, 7200)
        response = self.get(station=self.station.code, metrics='ph', hours=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['window']['end'], START + timedelta(hours=2, seconds=1))
        self.assertEqual(response.data['series'][0]['summary']['valid_count'], 1)
        self.assertEqual(response.data['series'][0]['latest']['observed_at'], START + timedelta(hours=2))

    def test_hourly_display_resolution_covers_all_48_samples_without_artificial_gaps(self):
        for hour in range(48):
            self.row(float(hour % 10), hour * 3600)
        response = self.get(station=self.station.code, metrics='ph', hours=48, max_points=48)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['window']['end'], START + timedelta(hours=47, seconds=1))
        self.assertEqual(response.data['window']['start'], START - timedelta(hours=1) + timedelta(seconds=1))
        points = response.data['series'][0]['points']
        self.assertEqual(len(points), 48)
        self.assertEqual([p['valid_count'] for p in points], [1] * 48)
        self.assertTrue(all(p['quality_status'] == 'valid' for p in points))
        self.assertEqual(response.data['series'][0]['summary']['valid_count'], 48)

    def test_one_successful_batch_only_and_explicit_old_batch(self):
        self.row(2)
        latest = SimulationRun.objects.create(key='newest', source=self.source, scenario=self.scenario,
                                             start=START, end=self.batch.end, seed=2, status='succeeded')
        self.row(8, simulation_run=latest)
        failed = SimulationRun.objects.create(key='failed', source=self.source, scenario=self.scenario,
                                             start=START, end=self.batch.end, seed=3, status='failed')
        self.row(13, simulation_run=failed)
        self.assertEqual(self.query().data['series'][0]['summary']['mean'], 8)
        self.assertEqual(self.query(simulation_run=str(self.batch.pk)).data['series'][0]['summary']['mean'], 2)
        self.assertEqual(self.query(simulation_run=str(failed.pk)).status_code, 400)

    def test_explicit_batch_can_select_another_scenario_but_conflict_is_rejected(self):
        other = SimulationRun.objects.create(key='missing-series', source=DataSource.objects.get(code='demo-missing'),
                    scenario=SimulationScenario.objects.get(code='missing'), start=START, end=self.batch.end, seed=1, status='succeeded')
        self.row(None, quality='missing', simulation_run=other, source=other.source)
        response = self.query(simulation_run=str(other.pk))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['source']['code'], 'demo-missing')
        self.assertEqual(self.query(simulation_run=str(other.pk), scenario='normal').status_code, 400)

    def test_multiple_simulation_sources_require_selection_in_series_and_legacy_api(self):
        self.row(2)
        source = DataSource.objects.create(code='second-simulation', name='另一模拟来源', kind='simulation')
        run = SimulationRun.objects.create(key='other-source', source=source, scenario=self.scenario,
                                         start=START, end=self.batch.end, seed=1, status='succeeded')
        self.row(11, source=source, simulation_run=run)
        self.assertEqual(self.query().status_code, 400)
        self.assertEqual(self.get(ObservationList, station=self.station.code).status_code, 400)
        selected = self.query(source=source.code)
        self.assertEqual(selected.data['series'][0]['summary']['mean'], 11)
        self.assertEqual(selected.data['source']['id'], str(source.pk))

    def test_non_simulated_source_never_mixes_sources_or_accepts_simulation_options(self):
        for number in (1, 2):
            source = DataSource.objects.create(code=f'manual-{number}', name=f'人工{number}', kind='manual')
            self.row(number, source=source, simulation_run=None)
        self.assertEqual(self.query(source_type='manual').status_code, 400)
        response = self.query(source_type='manual', source='manual-1')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['is_simulated'])
        self.assertIsNone(response.data['simulation_run_id'])
        self.assertEqual(response.data['series'][0]['summary']['mean'], 1)
        for extra in ({'scenario': 'normal'}, {'simulation_run': str(self.batch.pk)}):
            self.assertEqual(self.query(source_type='manual', source='manual-1', **extra).status_code, 400)
        self.assertEqual(self.query(source_type='dataset', source='manual-1').status_code, 400)

    def test_disabled_source_disappears_from_runs_sources_and_series(self):
        self.row(5)
        self.source.is_active = False
        self.source.save()
        self.assertEqual(self.query(source=self.source.code).status_code, 400)
        self.assertEqual(self.query().data['status'], 'unavailable')
        self.assertEqual(self.get(SimulationRunList).data['meta']['count'], 0)
        self.assertNotIn(self.source.code, [item['code'] for item in self.get(SourceList).data['data']])

    def test_hidden_places_and_disabled_stations_are_not_exposed_by_related_apis(self):
        self.row(5)
        hidden = self.station.place
        hidden.is_published = False
        hidden.save()
        self.assertEqual(self.query().status_code, 400)
        self.assertEqual(self.get(ObservationList, station=self.station.code).status_code, 400)
        self.assertEqual(self.get(SimulationRunList).data['meta']['count'], 0)
        self.assertEqual(self.get(StationList, water_body=str(self.station.water_body_id)).status_code, 400)
        self.assertNotIn(str(self.station.pk), [item['id'] for item in self.get(StationList).data['data']])
        self.assertNotIn(str(self.station.water_body_id), [item['id'] for item in self.get(WaterBodyList).data['data']])
        hidden.is_published = True
        hidden.save()
        self.station.is_active = False
        self.station.save()
        self.assertEqual(self.query().status_code, 400)
        self.assertEqual(self.get(SimulationRunList).data['meta']['count'], 0)

    def test_hidden_water_body_cannot_leak_through_station_with_separate_public_place(self):
        station = Station.objects.create(region=self.station.region, place=Place.objects.get(slug='library'),
                        water_body=self.station.water_body, code='separate-place', name='另一断面', kind='water')
        self.row(5, station=station)
        hidden = self.station.water_body.place
        hidden.is_published = False
        hidden.save()
        self.assertNotIn(str(station.pk), [item['id'] for item in self.get(StationList).data['data']])
        self.assertEqual(self.get(station=station.code).status_code, 400)

    def test_region_and_water_body_filters_and_scoped_batch_counts(self):
        self.row(4)
        other_station = Station.objects.get(code='demo-water-02')
        self.row(6, station=other_station)
        other = Region.objects.create(slug='other-area', name='其他区域')
        foreign_station = Station.objects.create(region=other, code='foreign-water', name='异地水站', kind='water')
        self.row(8, station=foreign_station)
        self.assertEqual(self.get(WaterBodyList, region=other.slug).data['meta']['count'], 0)
        rows = self.get(StationList, region=self.station.region.slug, water_body=str(self.station.water_body_id)).data['data']
        self.assertEqual([row['code'] for row in rows], [self.station.code])
        self.assertEqual(self.get(StationList, region=other.slug, water_body=str(self.station.water_body_id)).data['meta']['count'], 0)
        self.assertEqual(self.get(SimulationRunList).data['data'][0]['counts'], 2)
        self.assertEqual(self.get(SimulationRunList, station=self.station.code).data['data'][0]['counts'], 1)
        self.assertEqual(self.get(SimulationRunList, region=other.slug).data['data'][0]['counts'], 1)
        self.assertEqual(self.get(station=foreign_station.code).status_code, 400)
        self.assertEqual(self.get(station=foreign_station.code, region=other.slug).status_code, 200)

    def test_batch_directory_only_successful_matching_batches_and_public_counts(self):
        self.row(4)
        second = SimulationRun.objects.create(key='not-done', source=self.source, scenario=self.scenario,
                         start=START, end=self.batch.end, seed=2, status='running')
        self.row(7, simulation_run=second)
        results = self.get(SimulationRunList, source=self.source.code, scenario='normal').data['data']
        self.assertEqual([item['id'] for item in results], [str(self.batch.pk)])
        self.assertEqual(results[0]['counts'], 1)
        self.assertNotIn('parameters', results[0])
        self.assertEqual(self.get(SimulationRunList, scenario='unknown').status_code, 400)

    def test_invalid_bounds_and_ambiguous_parameters_return_validation_errors(self):
        self.row(4)
        invalid = [
            {'hours': 0}, {'hours': 745}, {'hours': '1.5'}, {'hours': '9' * 5000},
            {'max_points': 0}, {'max_points': 241}, {'max_points': '-1'},
            {'start': START.isoformat()}, {'end': START.isoformat()},
            {'start': START.isoformat(), 'end': (START + timedelta(days=32)).isoformat()},
            {'start': START.isoformat(), 'end': START.isoformat()},
            {'start': '2026-09-01T00:00:00', 'end': (START + timedelta(days=1)).isoformat()},
            {'start': START.isoformat(), 'end': (START + timedelta(days=1)).isoformat(), 'hours': 2},
            {'metrics': 'ph,ph'}, {'metrics': ''}, {'metrics': 'pm25'}, {'metrics': 'ph,unknown'},
            {'source_type': 'all'}, {'source': ''}, {'source': str(uuid4())},
            {'simulation_run': ''}, {'simulation_run': 'not-a-uuid'}, {'simulation_run': str(uuid4())},
            {'scenario': 'unknown'}, {'station': ['demo-water-01', 'demo-water-02']},
            {'region': ['demo-campus', 'demo-campus']}, {'max_points': [10, 20]},
        ]
        for params in invalid:
            with self.subTest(params=str(params)[:150]):
                response = self.get(**{'station': self.station.code, **params})
                self.assertEqual(response.status_code, 400, response.data)
        response = self.get(station=self.station.code, start=START.isoformat(), end=(START + timedelta(days=31)).isoformat(), max_points=240)
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(response.data['series'][0]['points']), 240)

    def test_metrics_units_remain_separate_and_explicit_selection_is_bounded(self):
        self.row(0)
        metric = Metric.objects.get(code='dissolved_oxygen')
        self.row(12, metric=metric)
        response = self.get(station=str(self.station.pk), metrics='ph,dissolved_oxygen', source=str(self.source.pk))
        values = {item['metric']['code']: item for item in response.data['series']}
        self.assertEqual(values['ph']['metric']['unit'], 'pH')
        self.assertEqual(values['dissolved_oxygen']['metric']['unit'], 'mg/L')
        self.assertEqual(values['ph']['summary']['mean'], 0)
        self.assertEqual(values['dissolved_oxygen']['summary']['mean'], 12)
        for i in range(6):
            Metric.objects.create(code=f'extra-{i}', name=f'额外{i}', unit='x', station_kind='water')
        self.assertEqual(self.get(station=self.station.code).status_code, 400)
        self.assertEqual(self.get(station=self.station.code, metrics='ph').status_code, 200)

    def test_finite_large_valid_values_do_not_overflow_during_mean_aggregation(self):
        metric = Metric.objects.create(code='unbounded', name='无界测试指标', unit='x', station_kind='water')
        self.row(1e308, metric=metric)
        self.row(1e308, 60, metric=metric)
        response = self.get(station=self.station.code, metrics='unbounded', hours=1, max_points=1)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['series'][0]['summary']['mean'], 1e308)
        self.assertEqual(response.data['series'][0]['points'][0]['value'], 1e308)

    def test_raw_row_limit_rejects_overflow_instead_of_silently_truncating(self):
        source = DataSource.objects.create(code='dense-history', name='密集测试历史', kind='dataset')
        Observation.objects.bulk_create([
            Observation(station=self.station, metric=self.metric, source=source, value=float(i % 11),
                        observed_at=START + timedelta(seconds=i), dedupe_key=f'dense-{i}')
            for i in range(50001)
        ], batch_size=1000)
        params = dict(station=self.station.code, source_type='dataset', source=source.code, metrics='ph',
                      start=START.isoformat(), max_points=240)
        ok = self.get(**params, end=(START + timedelta(seconds=50000)).isoformat())
        self.assertEqual(ok.status_code, 200, ok.data)
        self.assertEqual(ok.data['series'][0]['summary']['valid_count'], 50000)
        self.assertLessEqual(len(ok.data['series'][0]['points']), 240)
        overflow = self.get(**params, end=(START + timedelta(seconds=50001)).isoformat())
        self.assertEqual(overflow.status_code, 400)
