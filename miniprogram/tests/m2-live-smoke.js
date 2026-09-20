/** Read-only M2 integration against an explicitly local HTTP API with seeded scenarios. */
const assert = require('node:assert/strict');
const { createClient } = require('../lib/client');
const { createSession } = require('../lib/session');
const { loadAll } = require('../lib/region');
const { chartGeometry } = require('../lib/series');
const baseURL = process.env.HYHQ_TEST_API || 'http://127.0.0.1:18202/api/v1';
const origin = new URL(baseURL);
assert.equal(origin.protocol, 'http:');
assert.equal(origin.hostname, '127.0.0.1', 'This check is restricted to a local API');
const calls = [];
const storage = new Map();
const wx = {
  getStorageSync: (key) => storage.get(key), setStorageSync: (key, value) => storage.set(key, value), removeStorageSync: (key) => storage.delete(key),
  stopPullDownRefresh() {}, setNavigationBarTitle() {}, getWindowInfo() { return { windowWidth: 375 }; },
  navigateTo(options) { calls.push(options.url); },
  request(options) {
    assert.equal(options.method, 'GET', 'M2 public browsing must not create users or write data');
    assert.equal(new URL(options.url).origin, origin.origin);
    const url = new URL(options.url);
    Object.entries(options.data || {}).forEach(([key, value]) => url.searchParams.set(key, value));
    fetch(url, { headers: options.header, signal: AbortSignal.timeout(5000), redirect: 'error' })
      .then(async (response) => options.success({ statusCode: response.status, data: await response.text() }))
      .catch((error) => options.fail({ errMsg: error.message }));
  },
};
const session = createSession(wx);
const application = { session, globalData: {}, api: createClient(wx, { baseURL, timeout: 5000 }, session) };
function page(name) {
  let definition;
  global.Page = (value) => { definition = value; }; global.getApp = () => application; global.wx = wx;
  const filename = require.resolve('../pages/' + name + '/index'); delete require.cache[filename]; require(filename);
  return Object.assign({}, definition, { data: structuredClone(definition.data), setData(patch) { Object.assign(this.data, patch); } });
}
async function main() {
  const checks = [], scenarios = [];
  const health = (await application.api.request('health/')).data;
  assert.equal(health.mode, 'simulation');
  const home = page('home'); await home.onLoad();
  assert.equal(home.data.error, ''); assert.equal(home.data.sections.length, 0);
  assert.equal(home.data.region.slug, 'demo-campus');
  const region = home.data.region;
  const explore = page('explore'); await explore.onShow();
  assert.equal(explore.data.error, ''); assert.equal(explore.data.placesError, '');
  assert.equal(explore.data.activeMap.image_url, '/assets/maps/demo-campus-v1.png');
  assert.equal(explore.data.markers.length, 12);
  assert.ok(explore.data.markers.every((point) => point.x_ratio >= 0 && point.x_ratio <= 1 && point.y_ratio >= 0 && point.y_ratio <= 1));
  checks.push('home_and_twelve_version_bound_map_points');
  const waterBodies = await loadAll(application.api, 'water-bodies/', { region: region.id });
  assert.equal(waterBodies.length, 2);
  const water = page('water'); await water.onLoad({ region: region.id, waterBodyId: waterBodies[1].id });
  assert.equal(water.data.error, '');
  assert.equal(water.data.waterBodies[water.data.waterIndex].id, waterBodies[1].id);
  assert.equal(water.data.view.series.length, 4);
  const station = water.data.stations[water.data.stationIndex];
  for (const scenario of ['normal', 'turbidity', 'missing']) {
    const index = water.data.sources.findIndex((source) => source.code === 'demo-' + scenario);
    assert.ok(index >= 0); await water.changeSource({ detail: { value: index } });
    assert.equal(water.data.error, ''); assert.equal(water.data.view.status, 'available');
    const run = water.data.runs[water.data.runIndex];
    assert.equal(run.scenario.code, scenario);
    assert.equal(water.data.view.simulation_run_id, run.id);
    assert.equal(water.data.view.source.id, water.data.sources[index].id);
    const series = water.data.view.series;
    for (const entry of series) {
      assert.ok(entry.points.length <= 240);
      assert.equal(entry.valid_count + entry.missing_count + entry.suspect_count, 48);
      assert.equal(entry.points.filter((point) => point.quality_status === 'valid').length, entry.valid_count);
    }
    const turbidity = series.find((entry) => entry.metric.code === 'turbidity');
    if (scenario === 'turbidity') assert.ok(Number(turbidity.maximum_label) > 50);
    const gaps = series.reduce((count, entry) => count + entry.points.filter((point) => point.value === null).length, 0);
    const geometry = chartGeometry(turbidity.points, 340, 200, { start: water.data.view.start, end: water.data.view.end });
    assert.ok(geometry && geometry.segments.length);
    if (scenario === 'missing') { assert.ok(gaps > 0); assert.ok(geometry.segments.length > 1); }
    else assert.equal(gaps, 0);
    scenarios.push({ scenario, metrics: series.length, points_per_metric: series[0].points.length, missing_points: gaps, line_segments: geometry.segments.length });
  }
  checks.push('water_selection_and_three_isolated_simulation_scenarios');
  const stations = await loadAll(application.api, 'stations/', { region: region.id });
  const air = stations.find((item) => item.kind === 'air'); assert.ok(air);
  const center = page('data-center'); await center.onLoad({ region: region.id, stationId: air.id });
  assert.equal(center.data.error, ''); assert.equal(center.data.stations[center.data.stationIndex].id, air.id);
  assert.equal(center.data.kinds[center.data.kindIndex].code, 'air'); assert.equal(center.data.view.series.length, 3);
  const detail = page('detail'); await detail.onLoad({ kind: 'place', id: station.place });
  assert.equal(detail.data.error, ''); assert.equal(detail.data.recordError, '');
  detail.openWater(); detail.openDataCenter();
  assert.ok(calls.some((url) => url.includes('waterBodyId=' + waterBodies[1].id)));
  assert.ok(calls.some((url) => url.includes('stationId=' + station.id)));
  checks.push('detail_navigation_and_air_station_deep_link');
  assert.equal(session.token(), '');
  checks.push('all_screens_browse_without_login_or_location');
  process.stdout.write(JSON.stringify({ status: 'passed', checks, scenarios, transport: 'real_local_http_with_wx_mock', wechat_device_verified: false, server_deployed: false }, null, 2) + '\n');
}
main().catch((error) => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; });
