const test = require('node:test');
const assert = require('node:assert/strict');
const { createSession } = require('../lib/session');
const record = (id, extra = {}) => Object.assign({ id, body: '页面显示建议', status: 'pending', created_at: '2026-09-20T00:00:00Z', reply: '', resolved_at: null }, extra);
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function setup(handler, guest = false) {
  const storage = new Map(), calls = [], modals = [], redirects = [];
  const session = createSession({ getStorageSync: (key) => storage.get(key), setStorageSync: (key, value) => storage.set(key, value), removeStorageSync: (key) => storage.delete(key) });
  if (!guest) session.save({ token: 'a', user: { id: 'user-a' } });
  const application = { session, globalData: {}, api: { request: async (path, options) => {
    calls.push({ path, options });
    if (handler) { const result = await handler(path, options); if (result !== undefined) return result; }
    if (options && options.method === 'POST') return { data: record('new', { body: options.data.body }) };
    if (options && options.method === 'DELETE') return { data: null };
    return { data: [record('one')] };
  } } };
  global.getApp = () => application;
  global.wx = { stopPullDownRefresh() {}, switchTab: (options) => redirects.push(options.url), showModal: (options) => modals.push(options) };
  let definition; global.Page = (input) => { definition = input; };
  const filename = require.resolve('../pages/feedback/index'); delete require.cache[filename]; require(filename);
  const instance = { ...definition, data: structuredClone(definition.data) };
  instance.setData = (patch) => Object.assign(instance.data, patch); instance.onLoad();
  return { instance, application, calls, modals, redirects };
}
const input = (value) => ({ detail: { value } });
const remove = (id) => ({ currentTarget: { dataset: { id } } });

test('guest sees a voluntary login entry without requesting private lists or logging in automatically', async () => {
  const { instance, calls, redirects, modals } = setup(undefined, true); await instance.onShow();
  assert.equal(instance.data.loggedIn, false); assert.equal(calls.length, 0); assert.equal(modals.length, 0);
  instance.login(); assert.deepEqual(redirects, ['/pages/profile/index']);
  instance.inputBody(input('guest draft')); await instance.submit(); assert.equal(calls.length, 0);
});
test('submission trims content, sends only body, clears the confirmed draft and refreshes the list', async () => {
  let saved;
  const { instance, calls } = setup(async (path, options) => {
    if (options && options.method === 'POST') { saved = record('new', { body: options.data.body }); return { data: saved }; }
    if (saved) return { data: [saved, record('one')] };
  });
  await instance.onShow(); instance.inputBody(input('  修正河湖说明\n ')); await instance.submit();
  assert.deepEqual(calls.find((item) => item.options && item.options.method === 'POST').options.data, { body: '修正河湖说明' });
  assert.equal(instance.data.body, ''); assert.equal(instance.data.records[0].id, 'new'); assert.equal(instance.data.busy, false); assert.match(instance.data.notice, /已提交/);
});
test('empty or over-limit feedback never posts, while a thousand Unicode characters are counted correctly', async () => {
  const { instance, calls } = setup(); await instance.onShow();
  instance.inputBody(input(' \n ')); await instance.submit(); assert.match(instance.data.actionError, /1 至 1000/);
  instance.inputBody(input('字'.repeat(1001))); await instance.submit(); assert.equal(calls.filter((item) => item.options && item.options.method).length, 0);
  instance.inputBody(input('🌿'.repeat(1000))); assert.equal(instance.data.bodyCount, 1000); await instance.submit();
  assert.equal(calls.filter((item) => item.options && item.options.method === 'POST').length, 1);
});
test('duplicate submits create one request and failed submit retains the draft and prior records for retry', async () => {
  const pending = deferred(); let posts = 0;
  const { instance } = setup(async (path, options) => { if (options && options.method === 'POST') { posts += 1; if (posts === 1) return pending.promise; } });
  await instance.onShow(); instance.inputBody(input('保留草稿'));
  const saving = instance.submit(); await instance.submit(); assert.equal(posts, 1);
  pending.reject(new Error('连接中断')); await saving;
  assert.equal(instance.data.records[0].id, 'one'); assert.equal(instance.data.body, '保留草稿'); assert.equal(instance.data.busy, false); assert.match(instance.data.actionError, /先刷新记录核对/);
  await instance.submit(); assert.equal(posts, 2);
});
test('a successful submission remains visible when the following refresh fails', async () => {
  let saved = false;
  const { instance } = setup(async (path, options) => {
    if (options && options.method === 'POST') { saved = true; return { data: record('confirmed') }; }
    if (saved) throw new Error('列表暂不可用');
  });
  await instance.onShow(); instance.inputBody(input('新建议')); await instance.submit();
  assert.equal(instance.data.body, ''); assert.equal(instance.data.records[0].id, 'confirmed'); assert.equal(instance.data.busy, false); assert.match(instance.data.listError, /列表暂不可用/);
});
test('resolved replies show a fixed timezone and pending records never display unpublished replies', async () => {
  const { instance } = setup(async () => ({ data: [record('pending', { reply: '未公开草稿', resolved_at: '2026-09-20T01:00:00Z' }), record('resolved', { status: 'resolved', reply: '问题已修复', resolved_at: '2026-09-20T01:00:00Z' }), record('legacy', { status: 'resolved' })] }));
  await instance.onShow();
  assert.equal(instance.data.records[0].reply, ''); assert.equal(instance.data.records[0].resolved_label, '');
  assert.equal(instance.data.records[1].reply, '问题已修复'); assert.equal(instance.data.records[1].resolved_label, '2026-09-20 09:00 UTC+8');
  assert.equal(instance.data.records[2].status_label, '已处理'); assert.equal(instance.data.records[2].resolved_label, '');
});
test('load-more follows server pagination without a twenty-item truncation and deduplicates ids', async () => {
  const rows = Array.from({ length: 42 }, (_, index) => record(String(index)));
  const { instance, calls } = setup(async (path) => {
    if (path === 'feedback/') return { data: rows.slice(0, 20), meta: { next: '/api/v1/feedback/?page=2' } };
    return { data: rows.slice(19), meta: { next: null } };
  });
  await instance.onShow(); await instance.more(); assert.equal(instance.data.records.length, 42); assert.equal(instance.data.next, '');
  assert.equal(calls[1].options, undefined);
});
test('later-page failure retains records and can be retried without duplicating the first page', async () => {
  let fail = true;
  const { instance } = setup(async (path) => {
    if (path === 'feedback/') return { data: [record('one')], meta: { next: '/api/v1/feedback/?page=2' } };
    if (fail) throw new Error('分页失败'); return { data: [record('two')] };
  });
  await instance.onShow(); await instance.more(); assert.equal(instance.data.records.length, 1); assert.equal(instance.data.moreError, '分页失败');
  fail = false; await instance.more(); assert.deepEqual(instance.data.records.map((item) => item.id), ['one', 'two']);
});
test('duplicate pagination events issue one request and invalid next endpoints fail visibly', async () => {
  const pending = deferred(); let more = 0;
  const { instance } = setup(async (path) => {
    if (path === 'feedback/') return { data: [record('one')], meta: { next: '/api/v1/feedback/?page=2' } };
    more += 1; return pending.promise;
  });
  await instance.onShow(); const loading = instance.more(); await instance.more(); assert.equal(more, 1);
  pending.resolve({ data: [record('two')], meta: { next: '/api/v1/favorites/?page=3' } }); await loading;
  assert.match(instance.data.moreError, /分页地址/); assert.equal(instance.data.records.length, 1);
});
test('token renewal during pending load removes prior private records instead of accepting the old response', async () => {
  const pending = deferred(); let delay = false;
  const { instance, application } = setup(async () => delay ? pending.promise : undefined); await instance.onShow();
  instance.inputBody(input('私有草稿')); delay = true; const loading = instance.load();
  application.session.save({ token: 'renewed-a', user: { id: 'user-a' } }); pending.resolve({ data: [record('old-token')] }); await loading;
  assert.deepEqual(instance.data.records, []); assert.equal(instance.data.body, ''); assert.match(instance.data.listError, /登录状态/);
});
test('old-account list responses cannot overwrite or clear the newly loaded account', async () => {
  const pending = deferred(); let waitOld = false;
  const { instance, application } = setup(async () => {
    if (application.session.token() === 'a' && waitOld) return pending.promise;
    return { data: [record(application.session.token())] };
  });
  await instance.onShow(); waitOld = true; const old = instance.load();
  application.session.save({ token: 'b', user: { id: 'user-b' } }); await instance.load();
  pending.resolve({ data: [record('private-a')] }); await old; assert.equal(instance.data.records[0].id, 'b');
});
test('old-account submit results cannot leak content into a new account or clear its draft', async () => {
  const pending = deferred();
  const { instance, application } = setup(async (path, options) => { if (options && options.method === 'POST') return pending.promise; return { data: [record(application.session.token())] }; });
  await instance.onShow(); instance.inputBody(input('account-a')); const posting = instance.submit();
  instance.onHide(); application.session.save({ token: 'b', user: { id: 'user-b' } }); await instance.onShow(); instance.inputBody(input('account-b'));
  pending.resolve({ data: record('private-a') }); await posting;
  assert.equal(instance.data.records[0].id, 'b'); assert.equal(instance.data.body, 'account-b');
});
test('hide clears private data and late load results plus queued controls cannot write after unload', async () => {
  const pending = deferred(); const { instance, calls } = setup(async () => pending.promise);
  const loading = instance.onShow(); instance.onHide(); assert.deepEqual(instance.data.records, []); assert.equal(instance.data.body, '');
  instance.onUnload(); instance.setData = () => { throw new Error('write after unload'); };
  await instance.load(); await instance.submit(); await instance.more(); instance.inputBody(input('late')); instance.remove(remove('one')); instance.login();
  pending.resolve({ data: [record('late')] }); await loading; assert.equal(calls.length, 1);
});
test('a private 401 clears session and records and returns to the manual login state', async () => {
  let fail = false;
  const { instance, application } = setup(async () => { if (fail) throw Object.assign(new Error('expired'), { status: 401 }); });
  await instance.onShow(); fail = true; await instance.load();
  assert.equal(application.session.token(), ''); assert.equal(instance.data.loggedIn, false); assert.deepEqual(instance.data.records, []);
});
test('delete requires explicit confirmation and repeated modal callbacks never submit twice', async () => {
  let deleted = false;
  const { instance, calls, modals } = setup(async (path, options) => {
    if (options && options.method === 'DELETE') { deleted = true; return { data: null }; }
    if (deleted) return { data: [] };
  });
  await instance.onShow(); instance.remove(remove('one')); instance.remove(remove('one')); assert.equal(modals.length, 1);
  assert.equal(calls.filter((item) => item.options && item.options.method).length, 0);
  await modals[0].success({ confirm: true }); await modals[0].success({ confirm: true });
  assert.equal(calls.filter((item) => item.options && item.options.method === 'DELETE').length, 1); assert.deepEqual(instance.data.records, []); assert.equal(instance.data.busy, false);
});
test('stale delete confirmation after hide, account switch or explicit refresh cannot delete', async () => {
  for (const reason of ['hide', 'account', 'refresh']) {
    const { instance, application, modals, calls } = setup(); await instance.onShow(); instance.remove(remove('one'));
    if (reason === 'hide') instance.onHide();
    if (reason === 'account') application.session.save({ token: 'b', user: { id: 'user-b' } });
    if (reason === 'refresh') await instance.load();
    await modals[0].success({ confirm: true });
    assert.equal(calls.filter((item) => item.options && item.options.method === 'DELETE').length, 0, reason);
  }
});
test('a page already in flight cannot resurrect a deleted feedback record', async () => {
  const pending = deferred(); let deleted = false;
  const { instance, modals } = setup(async (path, options) => {
    if (options && options.method === 'DELETE') { deleted = true; return { data: null }; }
    if (path !== 'feedback/') return pending.promise;
    return deleted ? { data: [] } : { data: [record('one')], meta: { next: '/api/v1/feedback/?page=2' } };
  });
  await instance.onShow(); const more = instance.more(); instance.remove(remove('one')); await modals[0].success({ confirm: true });
  pending.resolve({ data: [record('one'), record('old-page')] }); await more;
  assert.deepEqual(instance.data.records, []); assert.equal(instance.data.next, '');
});
test('failed delete preserves prior records and a 404 permits idempotent local removal', async () => {
  let mode = 'failed';
  const { instance, modals } = setup(async (path, options) => {
    if (options && options.method === 'DELETE') throw Object.assign(new Error(mode), { status: mode === 'failed' ? 503 : 404 });
    if (mode === 'gone') throw new Error('refresh offline');
  });
  await instance.onShow(); instance.remove(remove('one')); await modals[0].success({ confirm: true });
  assert.equal(instance.data.records[0].id, 'one'); assert.equal(instance.data.actionError, 'failed'); assert.equal(instance.data.busy, false);
  mode = 'gone'; instance.remove(remove('one')); await modals[1].success({ confirm: true });
  assert.deepEqual(instance.data.records, []); assert.match(instance.data.notice, /已删除/);
});
test('old mutation completion after session change clears private state without reporting success', async () => {
  const pending = deferred();
  const { instance, application } = setup(async (path, options) => options && options.method === 'POST' ? pending.promise : undefined);
  await instance.onShow(); instance.inputBody(input('private')); const post = instance.submit();
  application.session.save({ token: 'b', user: { id: 'user-b' } }); pending.resolve({ data: record('private-a') }); await post;
  assert.deepEqual(instance.data.records, []); assert.equal(instance.data.body, ''); assert.equal(instance.data.notice, ''); assert.equal(instance.data.busy, false);
});
test('pull-to-refresh during a pending submission stops its indicator even if the submission fails', async () => {
  const pending = deferred(); let stopped = 0;
  const { instance, calls } = setup(async (path, options) => options && options.method === 'POST' ? pending.promise : undefined);
  await instance.onShow(); instance.inputBody(input('保留草稿'));
  const submitting = instance.submit(), count = calls.length;
  global.wx.stopPullDownRefresh = () => { stopped += 1; };
  await instance.onPullDownRefresh(); assert.equal(stopped, 1); assert.equal(calls.length, count);
  pending.reject(new Error('network offline')); await submitting;
  assert.equal(instance.data.busy, false); assert.equal(instance.data.body, '保留草稿');
});
