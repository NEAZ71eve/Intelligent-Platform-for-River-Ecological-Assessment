const test = require('node:test');
const assert = require('node:assert/strict');
const { createSession } = require('../lib/session');
const { time, value } = require('../lib/format');

function page(name, application) {
  let definition;
  global.Page = (input) => { definition = input; };
  global.getApp = () => application;
  global.wx = { stopPullDownRefresh() {}, showToast() {}, showModal() {}, setNavigationBarTitle() {} };
  const path = require.resolve('../pages/' + name + '/index');
  delete require.cache[path];
  require(path);
  const instance = { ...definition, data: structuredClone(definition.data) };
  instance.setData = (patch) => Object.assign(instance.data, patch);
  return instance;
}
function session() {
  const storage = new Map();
  return createSession({ getStorageSync: (key) => storage.get(key), setStorageSync: (key, val) => storage.set(key, val), removeStorageSync: (key) => storage.delete(key) });
}

test('home obtains real API fixtures, preserves zero values and warns that official alerts are not connected', async () => {
  const calls = [];
  const fixtures = {
    'health/': { status: 'ok', mode: 'simulation' },
    'regions/': [{ id: 'region1', name: '示范区域' }],
    'weather/': { temperature: 0, humidity: 0, source_type: 'simulation', status: 'available' },
    'air-quality/': { pm25: 0, pm10: 10, source_type: 'simulation' },
    'weather-alerts/': { status: 'not_connected', alerts: [], notice: '官方气象预警尚未接入' },
  };
  const app = { globalData: {}, api: { request: async (url, options) => { calls.push({ url, options }); return { data: fixtures[url] }; } } };
  const instance = page('home', app);
  await instance.load();
  assert.equal(instance.data.weather.temp_label, '0°');
  assert.equal(instance.data.air.pm25_label, '0');
  assert.equal(instance.data.alertNotice, '官方气象预警尚未接入');
  assert.equal(calls.find((call) => call.url === 'weather/').options.data.region, 'region1');
  assert.equal(instance.data.loading, false);
});

test('home displays partial failure instead of silently replacing upstream data', async () => {
  const app = { globalData: {}, api: { request: async (url) => {
    if (url === 'health/') return { data: { mode: 'simulation' } };
    if (url === 'regions/') return { data: [{ id: 'region' }] };
    if (url === 'weather/') throw new Error('weather unavailable');
    return { data: { source_type: 'simulation', alerts: [] } };
  } } };
  const instance = page('home', app);
  await instance.load();
  assert.equal(instance.data.weather, null);
  assert.equal(instance.data.sections[0].key, 'weather');
  assert.equal(instance.data.sections[0].error, 'weather unavailable');
});

test('development login is offered only when both client and server enable it', async () => {
  for (const [local, remote, expected] of [[true, true, true], [false, true, false], [true, false, false]]) {
    const app = { config: { development: local }, globalData: {}, session: session(), api: { request: async () => ({ data: { dev_auth_enabled: remote } }) } };
    const instance = page('profile', app);
    await instance.load();
    assert.equal(instance.data.devAvailable, expected);
  }
});

test('recognition clears private task data when identity changes or authorization fails', async () => {
  const current = session();
  current.save({ token: 'a', user: { id: 'user-a' } });
  const app = { session: current, api: { request: async () => ({ data: [] }) } };
  const instance = page('recognize', app);
  instance._userId = 'user-before';
  instance.data.task = { id: 'private-old-task' };
  instance.onShow();
  assert.equal(instance.data.task, null);
  instance.data.task = { id: 'private-new-task' };
  instance.data.jobs = [{ id: 'private-new-task' }];
  current.clear();
  instance.authError(new Error('请重新登录'));
  assert.equal(instance.data.task, null);
  assert.deepEqual(instance.data.jobs, []);
});

test('formatters preserve missing data and use fixed UTC+8 display', () => {
  assert.equal(value(null), '—');
  assert.equal(value(0, 'mg/L'), '0mg/L');
  assert.equal(time('2026-09-16T00:00:00Z'), '2026-09-16 08:00 UTC+8');
});
