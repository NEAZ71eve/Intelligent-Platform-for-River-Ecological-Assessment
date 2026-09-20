/** Explicit local development integration; creates and deletes only its own two accounts. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createClient } = require('../lib/client');
const { createSession } = require('../lib/session');
const baseURL = process.env.HYHQ_TEST_API || 'http://127.0.0.1:18203/api/v1';
const origin = new URL(baseURL);
assert.equal(origin.protocol, 'http:'); assert.equal(origin.hostname, '127.0.0.1');
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'hyhq-m2-business-'));
const imagePath = path.join(temporary, 'avatar.png');
fs.writeFileSync(imagePath, Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=', 'base64'));
const handoff = process.env.HYHQ_FEEDBACK_HANDOFF;
let handoffCreated = false;
const checks = [], navigation = [];
function application() {
  const storage = new Map(); let downloadIndex = 0;
  const wx = {
    getStorageSync: (key) => storage.get(key), setStorageSync: (key, value) => storage.set(key, value), removeStorageSync: (key) => storage.delete(key),
    stopPullDownRefresh() {}, setNavigationBarTitle() {}, showToast() {},
    navigateTo: ({ url }) => navigation.push(url), switchTab: ({ url }) => navigation.push(url),
    showModal() { throw new Error('Confirmations must be explicitly handled by the smoke test.'); },
    request(options) {
      const url = new URL(options.url), method = options.method || 'GET'; assert.equal(url.origin, origin.origin);
      if (method === 'GET') {
        Object.entries(options.data || {}).forEach(([key, value]) => url.searchParams.set(key, value));
        if (/\/(favorites|histories|visits|feedback)\/$/.test(url.pathname)) url.searchParams.set('page_size', '2');
      }
      fetch(url, { method, headers: options.header, body: method === 'GET' || options.data === undefined ? undefined : JSON.stringify(options.data), signal: AbortSignal.timeout(5000), redirect: 'error' })
        .then(async (response) => options.success({ statusCode: response.status, data: await response.text() }))
        .catch((error) => options.fail({ errMsg: error.message }));
    },
    uploadFile(options) {
      assert.equal(new URL(options.url).origin, origin.origin);
      const data = new FormData(); data.append(options.name, new Blob([fs.readFileSync(options.filePath)], { type: 'image/png' }), 'avatar.png');
      Object.entries(options.formData).forEach(([key, value]) => data.append(key, value));
      fetch(options.url, { method: 'POST', headers: options.header, body: data, redirect: 'error', signal: AbortSignal.timeout(5000) })
        .then(async (response) => options.success({ statusCode: response.status, data: await response.text() }))
        .catch((error) => options.fail({ errMsg: error.message }));
    },
    downloadFile(options) {
      assert.equal(new URL(options.url).origin, origin.origin);
      fetch(options.url, { headers: options.header, redirect: 'error', signal: AbortSignal.timeout(5000) })
        .then(async (response) => {
          const filename = path.join(temporary, 'download-' + downloadIndex++ + '.jpg');
          if (response.ok) fs.writeFileSync(filename, Buffer.from(await response.arrayBuffer()));
          options.success({ statusCode: response.status, tempFilePath: filename });
        }).catch((error) => options.fail({ errMsg: error.message }));
    },
  };
  const session = createSession(wx), config = { baseURL, development: true, timeout: 5000, uploadTimeout: 5000 };
  return { wx, session, config, globalData: {}, api: createClient(wx, config, session), created: false };
}
const app = application(), other = application();
function page(name) {
  let definition;
  global.Page = (input) => { definition = input; }; global.getApp = () => app; global.wx = app.wx;
  const filename = require.resolve('../pages/' + name + '/index'); delete require.cache[filename]; require(filename);
  return { ...definition, data: structuredClone(definition.data), setData(patch) { Object.assign(this.data, patch); } };
}
const event = (dataset) => ({ currentTarget: { dataset } });
async function confirm(action) {
  let confirmation;
  app.wx.showModal = (options) => { confirmation = options; };
  action(); assert.ok(confirmation, 'Expected an explicit confirmation');
  await confirmation.success({ confirm: true });
}
async function login(target) {
  const result = (await target.api.request('auth/dev/', { method: 'POST', data: { device_id: target.session.deviceId() } })).data;
  target.created = true; target.session.save({ ...result, auth_mode: 'development' });
}
async function main() {
  assert.equal((await app.api.request('health/')).data.dev_auth_enabled, true, 'Requires explicit local development auth');
  try {
    await login(app); await login(other);
    const places = (await app.api.request('places/', { data: { page_size: 3 } })).data; assert.equal(places.length, 3);
    for (const kind of ['favorites', 'histories', 'visits']) {
      for (const place of places) {
        const first = (await app.api.request(kind + '/', { method: 'POST', data: { place_id: place.id } })).data;
        const again = (await app.api.request(kind + '/', { method: 'POST', data: { place_id: place.id } })).data;
        assert.equal(again.id, first.id);
      }
      const records = page('records'); records.onLoad({ kind }); await records.onShow();
      assert.equal(records.data.error, ''); assert.equal(records.data.records.length, 2); assert.ok(records.data.next);
      await records.more(); assert.equal(records.data.records.length, 3); assert.equal(records.data.next, null);
      const selected = records.data.records[0]; records.open(event({ id: selected.id }));
      assert.ok(navigation.at(-1).includes('kind=place&id=' + selected.target_id));
      await assert.rejects(other.api.request(kind + '/' + selected.id + '/', { method: 'DELETE' }), { status: 404 });
      await confirm(() => records.remove(event({ id: selected.id })));
      assert.equal(records.data.error, ''); assert.equal(records.data.records.length, 2);
      assert.ok(records.data.records.every((record) => record.id !== selected.id));
    }
    checks.push('B03_favorites_histories_visits_pagination_idempotence_navigation_owner_delete');
    const profile = page('profile'); await profile.load();
    profile.data.nickname = 'M2本机验证'; await profile.saveProfile();
    assert.equal(profile.data.user.nickname, 'M2本机验证');
    await profile.chooseAvatar({ detail: { avatarUrl: imagePath } });
    assert.ok(profile.data.user.avatar_url && fs.existsSync(profile.data.avatar));
    await profile.privacyChange({ detail: { value: false } }); assert.equal(profile.data.user.record_history, false);
    await assert.rejects(app.api.request('histories/', { method: 'POST', data: { place_id: places[0].id } }), { code: 'HISTORY_DISABLED' });
    await profile.privacyChange({ detail: { value: true } }); assert.equal(profile.data.user.record_history, true);
    checks.push('B04_profile_nickname_private_avatar_and_history_switch');
    const feedback = page('feedback'); feedback.onLoad(); await feedback.onShow();
    for (let index = 0; index < 3; index += 1) {
      feedback.inputBody({ detail: { value: '本机联调反馈 ' + (index + 1) } }); await feedback.submit();
      assert.equal(feedback.data.actionError, ''); assert.equal(feedback.data.body, '');
    }
    assert.equal(feedback.data.records.length, 2); await feedback.more(); assert.equal(feedback.data.records.length, 3);
    const selected = feedback.data.records[0]; assert.equal(selected.status, 'pending');
    assert.deepEqual((await other.api.request('feedback/')).data, []);
    await assert.rejects(other.api.request('feedback/' + selected.id + '/', { method: 'DELETE' }), { status: 404 });
    await assert.rejects(app.api.request('feedback/' + selected.id + '/', { method: 'PATCH', data: { status: 'resolved', reply: '伪造答复' } }), { status: 405 });
    let adminReplyVerified = false;
    if (handoff) {
      fs.writeFileSync(handoff, JSON.stringify({ feedback_id: selected.id }), { flag: 'wx', mode: 0o600 });
      handoffCreated = true;
      const deadline = Date.now() + 30000;
      while (Date.now() < deadline) {
        await feedback.load();
        const updated = feedback.data.records.find((record) => record.id === selected.id);
        if (updated && updated.status === 'resolved') { assert.ok(updated.reply && updated.resolved_at && updated.resolved_label); adminReplyVerified = true; break; }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      assert.ok(adminReplyVerified, 'Local administrator must respond within the handoff window');
      checks.push('B04_real_admin_reply_read_back_by_owning_user');
    }
    await confirm(() => feedback.remove(event({ id: selected.id })));
    assert.equal(feedback.data.actionError, ''); assert.equal(feedback.data.records.length, 2);
    checks.push('B04_feedback_submit_paginate_readonly_moderation_and_owner_delete');
    await confirm(() => profile.logout()); assert.equal(app.session.token(), '');
    await login(app); await profile.load(); assert.equal(profile.data.user.nickname, 'M2本机验证');
    const oldToken = app.session.token();
    await confirm(() => profile.deleteAccount()); assert.equal(app.session.token(), '');
    assert.equal((await fetch(baseURL + '/me/', { headers: { Authorization: 'Bearer ' + oldToken }, redirect: 'error', signal: AbortSignal.timeout(5000) })).status, 401);
    app.created = false;
    checks.push('B04_logout_relogin_account_deletion_and_old_session_rejection');
    return { status: 'passed', checks, admin_reply_verified: adminReplyVerified, page_size_override: 2, transport: 'real_local_http_with_wx_mock', wechat_device_verified: false, server_deployed: false };
  } finally {
    const cleanup = await Promise.allSettled([app, other].map(async (target) => {
      if (!target.created) return;
      if (!target.session.token()) await login(target);
      await target.api.request('me/', { method: 'DELETE' }); target.session.clear(); target.created = false;
    }));
    const failure = cleanup.find((result) => result.status === 'rejected');
    if (failure) throw new Error('Test account cleanup failed: ' + failure.reason.message);
  }
}
main().then((result) => process.stdout.write(JSON.stringify({ ...result, test_accounts_cleaned: true }, null, 2) + '\n')).catch((error) => { process.stderr.write(String(error.stack || error) + '\n'); process.exitCode = 1; }).finally(() => {
  fs.rmSync(temporary, { recursive: true, force: true });
  if (handoffCreated && fs.existsSync(handoff)) fs.unlinkSync(handoff);
});
