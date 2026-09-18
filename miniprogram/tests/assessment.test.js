const test = require('node:test');
const assert = require('node:assert/strict');
const { createSession } = require('../lib/session');
const { resultView, issueList, assessmentTask, metricView } = require('../lib/assessment');

function page(name, application) {
  let definition;
  global.Page = (input) => { definition = input; };
  global.getApp = () => application;
  global.wx = { stopPullDownRefresh() {}, showToast() {}, showModal() {}, setNavigationBarTitle() {}, navigateTo() {}, switchTab() {} };
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
function loggedApp(api) {
  const current = session();
  current.save({ token: 'active-token', user: { id: 'active-user' } });
  return { globalData: {}, config: { maxUploadBytes: 5 * 1024 * 1024 }, session: current, api };
}
function det(eval_category, area_ratio) {
  return { eval_category, conf: 0.8, area_ratio, x1: 10, y1: 20, x2: 50, y2: 100, class_id: 0, label: 'bottle' };
}

test('issueList aggregates detections by eval category with area percentages', () => {
  const issues = issueList([det('floating_debris', 0.01), det('floating_debris', 0.005), det('bank_problem', 0.02)]);
  assert.equal(issues.length, 2);
  assert.equal(issues[0].key, 'floating_debris');
  assert.equal(issues[0].count, 2);
  assert.equal(issues[0].area_label, '1.5%');
  assert.equal(issues[1].label, '岸带环境问题');
  assert.ok(issues[0].color);
});

test('resultView maps grades, causes and boxes only for succeeded jobs', () => {
  const failed = resultView({ status: 'failed', error_code: 'MODEL_NOT_CONFIGURED' });
  assert.equal(failed, null);
  const view = resultView({ status: 'succeeded', grade: '中', score: 62, detections: [det('floating_debris', 0.02)], causes: [{ rule: 'bloom', text: '建议核查上游氮磷来源' }], rule_version: 'v1', duration_ms: 8300, disclaimer: '平台演示评分，非官方水质评价。' });
  assert.equal(view.grade, '中');
  assert.equal(view.grade_key, 'fair');
  assert.equal(view.score, 62);
  assert.deepEqual(view.causes, ['建议核查上游氮磷来源']);
  assert.equal(view.boxes.length, 1);
  assert.equal(view.boxes[0].conf_label, '80%');
  assert.equal(view.duration_label, '8.3s');
  assert.equal(view.disclaimer, '平台演示评分，非官方水质评价。');
});

test('assessmentTask keeps failed error labels explicit instead of faking conclusions', () => {
  const task = assessmentTask({ status: 'failed', error_code: 'MODEL_NOT_CONFIGURED' });
  assert.equal(task.status_label, '评估失败');
  assert.match(task.error_label, /未启用/);
  const ok = assessmentTask({ status: 'succeeded', grade: '优', score: 100, created_at: '2026-09-17T00:00:00Z' });
  assert.equal(ok.sub_label, '生态等级 优 · 100 分');
  assert.equal(ok.created_label, '2026-09-17 08:00 UTC+8');
});

test('metricView flags simulated observations', () => {
  const metric = metricView({ metric_name: '水温', value: 24.5, unit: '°C', observed_at: '2026-09-17T00:00:00Z', is_simulated: true });
  assert.equal(metric.simulated, true);
  assert.equal(metric.value_label, '24.5');
});

test('patrol submit without location toasts and never uploads', async () => {
  const calls = { upload: 0, post: 0 };
  const instance = page('recognize', loggedApp({
    upload: async () => { calls.upload += 1; return { id: 'asset' }; },
    request: async () => { calls.post += 1; return { data: {} }; },
  }));
  const toasts = [];
  global.wx.showToast = (options) => toasts.push(options.title);
  Object.assign(instance.data, { imagePath: '/tmp/river.jpg', consent: true, location: null });
  await instance.submit();
  assert.equal(calls.upload, 0);
  assert.equal(calls.post, 0);
  assert.equal(toasts.length, 1);
  assert.match(toasts[0], /定位/);
});

test('patrol submit uploads the photo, posts coordinates and opens the result page', async () => {
  const posts = [];
  const instance = page('recognize', loggedApp({
    upload: async () => ({ id: 'asset-1' }),
    request: async (url, options) => {
      if (options && options.method === 'POST') posts.push({ url, data: options.data });
      return { data: { id: 'job-9', status: 'queued' } };
    },
  }));
  const navigations = [];
  global.wx.navigateTo = (options) => navigations.push(options.url);
  Object.assign(instance.data, { imagePath: '/tmp/river.jpg', consent: true, location: { latitude: 39.9, longitude: 116.4 } });
  await instance.submit();
  assert.equal(posts.length, 1);
  assert.equal(posts[0].url, 'assessment-jobs/');
  assert.equal(posts[0].data.asset_id, 'asset-1');
  assert.equal(posts[0].data.latitude, 39.9);
  assert.equal(posts[0].data.coordinate_system, 'GCJ02');
  assert.equal(navigations.length, 1);
  assert.equal(navigations[0], '/pages/assessment/index?jobId=job-9');
  assert.equal(instance.data.busy, false);
});

test('patrol page lists recent assessment jobs and opens the result page on tap', async () => {
  const instance = page('recognize', loggedApp({
    request: async () => ({ data: [{ id: 'job-1', status: 'succeeded', grade: '良', score: 75, created_at: '2026-09-17T00:00:00Z' }] }),
  }));
  await instance.load();
  assert.equal(instance.data.jobs[0].sub_label, '生态等级 良 · 75 分');
  const navigations = [];
  global.wx.navigateTo = (options) => navigations.push(options.url);
  instance.openJob({ currentTarget: { dataset: { id: 'job-1' } } });
  assert.equal(navigations[0], '/pages/assessment/index?jobId=job-1');
});

test('result page renders queued status and keeps polling on a timer', async () => {
  const instance = page('assessment', loggedApp({
    request: async () => ({ data: { id: 'job-q', status: 'queued' } }),
  }));
  const timers = [];
  const realSetTimeout = global.setTimeout;
  global.setTimeout = (fn, ms) => { timers.push(ms); return null; };
  try {
    await instance.onLoad({ jobId: 'job-q' });
    await new Promise((resolve) => realSetTimeout(resolve, 0));
    assert.equal(instance.data.job.status_label, '等待处理');
    assert.equal(instance.data.result, null);
    assert.equal(timers.length, 1);
    assert.equal(timers[0], 3000);
  } finally { global.setTimeout = realSetTimeout; }
});

test('result page renders grade, issues, causes and metrics for a succeeded job', async () => {
  const requests = [];
  const instance = page('assessment', loggedApp({
    request: async (url, options) => {
      requests.push({ url, options });
      if (url === 'assessment-jobs/job-ok/') return { data: {
        id: 'job-ok', status: 'succeeded', asset_id: 'asset-1', station_id: 'station-1',
        grade: '良', score: 75, rule_version: 'v1', duration_ms: 6400,
        detections: [det('floating_debris', 0.03), det('floating_debris', 0.01)],
        causes: [{ rule: 'fd_bank', text: '漂浮物与岸带垃圾并存' }],
      } };
      if (url === 'observations/') return { data: [{ metric_name: '水温', value: 24.5, unit: '°C', observed_at: '2026-09-17T00:00:00Z', is_simulated: true }] };
      return { data: {} };
    },
    download: async () => { throw Object.assign(new Error('expired'), { status: 404 }); },
  }));
  await instance.onLoad({ jobId: 'job-ok' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(instance.data.result.grade, '良');
  assert.equal(instance.data.result.grade_key, 'good');
  assert.equal(instance.data.result.issues[0].count, 2);
  assert.equal(instance.data.result.issues[0].area_label, '4.0%');
  assert.deepEqual(instance.data.result.causes, ['漂浮物与岸带垃圾并存']);
  assert.match(instance.data.imageUnavailable, /仍可查看/);
  assert.equal(instance.data.metrics[0].simulated, true);
  assert.equal(instance.data.metrics[0].name, '水温');
  assert.ok(requests.some((r) => r.url === 'observations/' && r.options.data.station === 'station-1'));
});

test('result page exposes failure codes without faking a conclusion', async () => {
  const instance = page('assessment', loggedApp({
    request: async () => ({ data: { id: 'job-f', status: 'failed', error_code: 'MODEL_NOT_CONFIGURED', created_at: '2026-09-17T00:00:00Z' } }),
  }));
  await instance.onLoad({ jobId: 'job-f' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(instance.data.result, null);
  assert.match(instance.data.job.error_label, /未启用/);
});

test('records page lists assessment jobs with grade titles and routes to the result page', async () => {
  const instance = page('records', loggedApp({
    request: async () => ({ data: [
      { id: 'job-a', status: 'succeeded', grade: '差', score: 40, detections: [det('outfall_discharge', 0.1)], rule_version: 'v1', created_at: '2026-09-17T00:00:00Z' },
      { id: 'job-b', status: 'failed', error_code: 'INFERENCE_TIMEOUT', created_at: '2026-09-17T01:00:00Z' },
    ], meta: { next: null } }),
  }));
  await instance.onLoad({ kind: 'assessment-jobs' });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(instance.data.title, '巡查记录');
  assert.equal(instance.data.records[0].title, '生态等级 差 · 40 分');
  assert.match(instance.data.records[1].title, /评估失败/);
  assert.match(instance.data.records[1].error_label, /超时/);
  const navigations = [];
  global.wx.navigateTo = (options) => navigations.push(options.url);
  instance.open({ currentTarget: { dataset: { id: 'job-a' } } });
  assert.equal(navigations[0], '/pages/assessment/index?jobId=job-a');
});
