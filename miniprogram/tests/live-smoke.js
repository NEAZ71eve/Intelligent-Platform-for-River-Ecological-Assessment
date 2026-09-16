/** Explicitly run against a local DEVELOPMENT server; creates/deletes its own accounts. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createClient } = require('../lib/client');
const { createSession } = require('../lib/session');
const baseURL = process.env.HYHQ_TEST_API || 'http://127.0.0.1:8000/api/v1';
const config = { baseURL, development: true, timeout: 10000, uploadTimeout: 15000 };
const output = [];
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'hyhq-mini-smoke-'));
const imagePath = path.join(temp, 'pixel.png');
// A complete, valid tiny PNG (CRC verified by the backend decoder).
fs.writeFileSync(imagePath, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'));

function transport() {
  const storage = new Map();
  let downloadIndex = 0;
  const wx = {
    getStorageSync: (key) => storage.get(key),
    setStorageSync: (key, value) => storage.set(key, value),
    removeStorageSync: (key) => storage.delete(key),
    stopPullDownRefresh() {}, showToast() {}, setNavigationBarTitle() {},
    showModal() { throw new Error('A live smoke test must explicitly handle destructive confirmations'); },
    request(options) {
      const url = new URL(options.url);
      const method = options.method || 'GET';
      if (method === 'GET' && options.data) Object.entries(options.data).forEach(([key, value]) => url.searchParams.set(key, value));
      fetch(url, { method, headers: options.header, body: method === 'GET' || options.data === undefined ? undefined : JSON.stringify(options.data), signal: AbortSignal.timeout(options.timeout) })
        .then(async (response) => options.success({ statusCode: response.status, data: await response.text() }))
        .catch((error) => options.fail({ errMsg: error.message }));
    },
    uploadFile(options) {
      const data = new FormData();
      data.append(options.name, new Blob([fs.readFileSync(options.filePath)], { type: 'image/png' }), 'fixture.png');
      Object.entries(options.formData).forEach(([key, value]) => data.append(key, value));
      fetch(options.url, { method: 'POST', headers: options.header, body: data, signal: AbortSignal.timeout(options.timeout) })
        .then(async (response) => options.success({ statusCode: response.status, data: await response.text() }))
        .catch((error) => options.fail({ errMsg: error.message }));
    },
    downloadFile(options) {
      fetch(options.url, { headers: options.header, signal: AbortSignal.timeout(options.timeout) })
        .then(async (response) => {
          const downloadPath = path.join(temp, `download-${downloadIndex++}.jpg`);
          if (response.ok) fs.writeFileSync(downloadPath, Buffer.from(await response.arrayBuffer()));
          options.success({ statusCode: response.status, tempFilePath: downloadPath });
        }).catch((error) => options.fail({ errMsg: error.message }));
    },
  };
  return wx;
}
function application(wx) {
  const session = createSession(wx);
  return { config, session, globalData: {}, api: createClient(wx, config, session) };
}
function loadPage(name, app, wx) {
  let definition;
  global.Page = (value) => { definition = value; };
  global.getApp = () => app;
  global.wx = wx;
  const file = require.resolve('../pages/' + name + '/index');
  delete require.cache[file];
  require(file);
  return Object.assign({}, definition, { data: structuredClone(definition.data), setData(patch) { Object.assign(this.data, patch); } });
}
const wx = transport();
const app = application(wx);
const second = application(transport());

async function main() {
  const health = (await app.api.request('health/')).data;
  assert.equal(health.dev_auth_enabled, true, 'Only a development server with explicit dev auth can run this smoke test');
  const home = loadPage('home', app, wx);
  await home.load();
  assert.equal(home.data.error, '');
  assert.equal(home.data.weather.source_type, 'simulation');
  assert.equal(home.data.air.source_type, 'simulation');
  assert.ok(home.data.alertNotice);
  assert.equal(home.data.sections.length, 0);
  output.push('首页天气/空气/预警状态与真实 API 对接通过');

  const profile = loadPage('profile', app, wx);
  await profile.load();
  assert.equal(profile.data.devAvailable, true);
  profile.data.agreed = true;
  await profile.login({ currentTarget: { dataset: { mode: 'dev' } } });
  assert.equal(profile.data.error, '');
  assert.ok(profile.data.user.id);
  assert.equal(profile.data.authMode, 'development');
  profile.data.nickname = '前端联调测试';
  await profile.saveProfile();
  assert.equal(profile.data.user.nickname, '前端联调测试');
  await profile.chooseAvatar({ detail: { avatarUrl: imagePath } });
  assert.ok(profile.data.user.avatar_url);
  assert.ok(fs.existsSync(profile.data.avatar));
  output.push('开发登录、昵称、头像上传及鉴权缩略图下载通过');

  const place = (await app.api.request('places/')).data[0];
  assert.ok(place.id);
  const detail = loadPage('detail', app, wx);
  detail._id = place.id;
  detail._path = 'places/' + place.id + '/';
  detail.data.kind = 'place';
  await detail.load();
  assert.equal(detail.data.error, '');
  assert.equal(detail.data.recordError, '');
  await detail.toggleFavorite();
  assert.ok(detail.data.favoriteId);
  assert.equal((await app.api.request('favorites/')).data[0].place.id, place.id);
  assert.equal((await app.api.request('histories/')).data[0].place.id, place.id);
  const visit = (await app.api.request('visits/', { method: 'POST', data: { place_id: place.id } })).data;
  assert.equal(visit.place.id, place.id);
  const records = loadPage('records', app, wx);
  records.data.kind = 'favorites';
  await records.load();
  assert.equal(records.data.records[0].title, place.name);
  await profile.privacyChange({ detail: { value: false } });
  assert.equal(profile.data.user.record_history, false);
  await assert.rejects(app.api.request('histories/', { method: 'POST', data: { place_id: place.id } }), { code: 'HISTORY_DISABLED' });
  output.push('收藏、浏览、游览、个人记录标题与隐私开关联调通过');

  const otherLogin = (await second.api.request('auth/dev/', { method: 'POST', data: { device_id: second.session.deviceId() } })).data;
  second.session.save(otherLogin);
  assert.equal((await second.api.request('favorites/')).data.length, 0);
  await assert.rejects(second.api.download(profile.data.user.avatar_url));
  output.push('第二个账号无法访问第一个账号的收藏或私有头像');

  const asset = await app.api.upload(imagePath, 'recognition');
  const job = (await app.api.request('recognition-jobs/', { method: 'POST', data: { asset_id: asset.id } })).data;
  assert.ok(['queued', 'failed'].includes(job.status));
  let final = job;
  const limit = Date.now() + 20000;
  while (['queued', 'running'].includes(final.status) && Date.now() < limit) {
    await new Promise((resolve) => setTimeout(resolve, 500));
    final = (await app.api.request('recognition-jobs/' + job.id + '/')).data;
  }
  assert.equal(final.status, 'failed', 'Start run_recognition_worker before running this script');
  assert.equal(final.error_code, 'MODEL_NOT_CONFIGURED');
  const recognize = loadPage('recognize', app, wx);
  await recognize.load();
  assert.equal(recognize.data.jobs[0].error_code, 'MODEL_NOT_CONFIGURED');
  assert.match(recognize.data.jobs[0].error_label, /未产生识别结论/);
  await app.api.request('recognition-jobs/' + job.id + '/', { method: 'DELETE' });
  await assert.rejects(app.api.download(asset.thumbnail_url));
  output.push('上传、任务队列、明确 MODEL_NOT_CONFIGURED 及任务/图片删除通过');

  const previous = app.session.get();
  await app.api.request('auth/logout/', { method: 'POST' });
  await assert.rejects(app.api.request('me/'), { status: 401 });
  assert.equal(app.session.token(), '');
  // Re-enter only our own development account, then permanently delete it.
  const login = (await app.api.request('auth/dev/', { method: 'POST', data: { device_id: app.session.deviceId() } })).data;
  app.session.save(login);
  assert.equal(login.user.id, previous.user.id);
  await app.api.request('me/', { method: 'DELETE' });
  await assert.rejects(app.api.request('me/'), { status: 401 });
  assert.equal(app.session.token(), '');
  output.push('退出与注销后旧会话失效、客户端 401 清理通过');
  process.stdout.write(JSON.stringify({ status: 'passed', checks: output, boundary: '真实 HTTP + wx mock；未运行微信开发者工具或真机' }, null, 2) + '\n');
}

main().catch((error) => { process.stderr.write(`Live smoke failed: ${error.code || error.name}: ${error.message}\n`); process.exitCode = 1; }).finally(async () => {
  for (const testApp of [app, second]) {
    if (testApp.session.token()) {
      try { await testApp.api.request('me/', { method: 'DELETE' }); } catch (error) { /* Do not mask the primary result. */ }
      testApp.session.clear();
    }
  }
  fs.rmSync(temp, { recursive: true, force: true });
});
