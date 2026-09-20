const test = require('node:test');
const assert = require('node:assert/strict');
const { createSession } = require('../lib/session');
const { quotaView, requestId, readPage } = require('../lib/llm');
const quota = { date: '2026-09-20', limit: 5, used: 1, reserved: 0, remaining: 4, reset_at: '2026-09-20T16:00:00Z' };
const session = (id = 's1', extra = {}) => ({ id, kind: 'recognition', title: '花卉结果解读', context_summary: '候选为雏菊类，仅供参考。', recognition_job_id: 'j1', assessment_job_id: null, include_image: false, image_available: false, created_at: '2026-09-20T00:00:00Z', expires_at: '2026-10-20T00:00:00Z', ...extra });
const turn = (id = 't1', extra = {}) => ({ id, session_id: 's1', question: '如何核对？', answer: '观察其他特征。', status: 'succeeded', used_image: false, message: '', error_code: '', created_at: '2026-09-20T01:00:00Z', finished_at: '2026-09-20T01:00:03Z', model: 'test-model', ...extra });
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
const nativeSet = global.setTimeout, nativeClear = global.clearTimeout;
test.after(() => { global.setTimeout = nativeSet; global.clearTimeout = nativeClear; });
function fixture(handler, options = { sessionId: 's1' }, guest = false, pageName = 'llm') {
  const storage = new Map(), calls = [], modals = [], timers = [], navigation = [];
  const auth = createSession({ getStorageSync: (key) => storage.get(key), setStorageSync: (key, value) => storage.set(key, value), removeStorageSync: (key) => storage.delete(key) });
  if (!guest) auth.save({ token: 'A', user: { id: 'A' } });
  const application = { session: auth, globalData: {}, api: { request: async (path, requestOptions) => {
    calls.push({ path, options: requestOptions });
    if (handler) { const result = await handler(path, requestOptions); if (result !== undefined) return result; }
    if (path === 'llm/status/') return { data: { enabled: true, consent_version: 'deepseek-v1', daily_limit: 5, notice: '测试服务', quota: guest ? null : quota } };
    if (path === 'recognition-jobs/j1/') return { data: { id: 'j1', status: 'succeeded', result: { decision: 'recognized', candidates: [{ name: '雏菊类', score: 0.8 }], threshold: 0 } } };
    if (path === 'assessment-jobs/a1/') return { data: { id: 'a1', status: 'succeeded', detections: [] } };
    if (path === 'llm/sessions/' && requestOptions && requestOptions.method === 'POST') return { data: session() };
    if (path === 'llm/sessions/') return { data: [session()] };
    if (path === 'llm/sessions/s1/turns/' && requestOptions && requestOptions.method === 'POST') return { data: turn('new', { question: requestOptions.data.question }) };
    if (path === 'llm/sessions/s1/turns/') return { data: [] };
    if (path.startsWith('llm/turns/')) return { data: turn(path.split('/')[2]) };
    return { data: session() };
  } } };
  global.getApp = () => application;
  global.wx = { stopPullDownRefresh() {}, showModal: (modal) => modals.push(modal), switchTab: ({ url }) => navigation.push(url), navigateTo: ({ url }) => navigation.push(url) };
  global.setTimeout = (fn, ms) => { const timer = { fn, ms, cleared: false }; timers.push(timer); return timer; };
  global.clearTimeout = (timer) => { if (timer) timer.cleared = true; };
  let definition; global.Page = (value) => { definition = value; };
  const path = require.resolve('../pages/' + pageName + '/index'); delete require.cache[path]; require(path);
  const page = { ...definition, data: structuredClone(definition.data), setData(patch) { Object.assign(this.data, patch); } }; page.onLoad(options);
  return { page, application, calls, modals, timers, navigation };
}
const change = (value) => ({ detail: { value } });
const idEvent = (id) => ({ currentTarget: { dataset: { id } } });
const flush = async () => { for (let count = 0; count < 8; count += 1) await Promise.resolve(); };

test('quota dates use server values and explicitly show the next Beijing midnight', () => {
  const value = quotaView(quota);
  assert.equal(value.remaining, 4); assert.equal(value.date, '2026-09-20'); assert.equal(value.reset_label, '2026-09-21 00:00 UTC+8');
  assert.equal(quotaView(null), null); assert.equal(quotaView({ remaining: '4' }), null);
  assert.match(requestId(), /^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/);
});
test('guest reads service notice without fetching private source, sessions or sending a question', async () => {
  const { page, calls, navigation } = fixture(undefined, { kind: 'recognition', jobId: 'j1' }, true);
  await page.onShow(); assert.equal(page.data.loggedIn, false); assert.deepEqual(calls.map((item) => item.path), ['llm/status/']);
  await page.send(); page.createSession(); page.login(); assert.equal(calls.length, 1); assert.deepEqual(navigation, ['/pages/profile/index']);
});
test('unbound chat links fail and disabled service retains an explicit status without creating a session', async () => {
  const invalid = fixture(undefined, {}); await invalid.page.onShow(); assert.match(invalid.page.data.error, /已有花卉识别/); assert.equal(invalid.calls.length, 0);
  const { page, calls, modals } = fixture(async (path) => path === 'llm/status/' ? { data: { enabled: false, notice: '密钥尚未配置', quota: null } } : undefined, { kind: 'recognition', jobId: 'j1' });
  await page.onShow(); page.consentChange(change(['agree'])); page.createSession();
  assert.equal(page.data.status.enabled, false); assert.equal(page.data.status.notice, '密钥尚未配置'); assert.equal(modals.length, 0); assert.equal(calls.some((item) => item.options && item.options.method), false);
});
test('source entry defaults to no image and cancellation never sends data to create a conversation', async () => {
  const { page, calls, modals } = fixture(undefined, { kind: 'recognition', jobId: 'j1' }); await page.onShow();
  assert.equal(page.data.includeImage, false); assert.ok(page.data.source.result_view); assert.equal(page.data.turns.length, 0);
  page.createSession(); assert.equal(modals.length, 0);
  page.consentChange(change(['agree'])); page.createSession(); await modals[0].success({ confirm: false });
  assert.equal(calls.some((item) => item.options && item.options.method === 'POST'), false);
});
test('native consent modal respects the four-character button limit and failed opening safely permits retry', async () => {
  const { page, calls, modals } = fixture(undefined, { kind: 'recognition', jobId: 'j1' }); await page.onShow();
  global.wx.showModal = (modal) => {
    assert.ok(Array.from(modal.confirmText).length >= 1 && Array.from(modal.confirmText).length <= 4, 'native confirmText accepts at most four characters');
    modals.push(modal);
    if (modals.length === 1) modal.fail({ errMsg: 'platform-internal-diagnostic' });
  };
  page.consentChange(change(['agree'])); page.createSession();
  assert.match(page.data.actionError, /确认窗口未能打开/); assert.equal(page.data.actionError.includes('platform-internal-diagnostic'), false);
  assert.equal(page._confirming, false); assert.equal(page.data.session, null);
  await modals[0].success({ confirm: true });
  assert.equal(calls.some((item) => item.options && item.options.method === 'POST'), false);
  page.createSession(); assert.equal(modals.length, 2); await modals[1].success({ confirm: true });
  assert.equal(page.data.session.id, 's1'); assert.equal(page.data.actionError, '');
  assert.equal(calls.filter((item) => item.options && item.options.method === 'POST').length, 1);
});
test('confirmed image preference is explicit and creating a session never automatically spends a turn', async () => {
  const { page, calls, modals } = fixture(undefined, { kind: 'recognition', jobId: 'j1' }); await page.onShow();
  page.consentChange(change(['agree'])); page.imageChange(change(true)); assert.equal(page.data.consent, false);
  page.consentChange(change(['agree'])); page.createSession(); page.createSession(); assert.equal(modals.length, 1);
  assert.match(modals[0].content, /另外选择附送本次原图/);
  await modals[0].success({ confirm: true }); await modals[0].success({ confirm: true });
  const posts = calls.filter((item) => item.options && item.options.method === 'POST');
  assert.equal(posts.length, 1); assert.deepEqual(posts[0].options.data, { recognition_job_id: 'j1', consent_version: 'deepseek-v1', include_image: true });
  assert.equal(page.data.session.id, 's1'); assert.ok(page.data.question); assert.equal(page.data.turns.length, 0);
});
test('expired original image is an explicit failure; no automatic retry uses a thumbnail or removes consent', async () => {
  const { page, calls, modals } = fixture(async (path, options) => { if (path === 'llm/sessions/' && options.method === 'POST') throw Object.assign(new Error('原图已过期'), { code: 'IMAGE_UNAVAILABLE', status: 409 }); }, { kind: 'recognition', jobId: 'j1' });
  await page.onShow(); page.imageChange(change(true)); page.consentChange(change(['agree'])); page.createSession(); await modals[0].success({ confirm: true });
  assert.equal(page.data.session, null); assert.match(page.data.actionError, /关闭附图/); assert.equal(calls.filter((item) => item.options && item.options.method === 'POST').length, 1);
});
test('stale consent after hide or account switch cannot create a session', async () => {
  for (const mode of ['hide', 'account']) {
    const { page, application, calls, modals } = fixture(undefined, { kind: 'recognition', jobId: 'j1' }); await page.onShow();
    page.consentChange(change(['agree'])); page.createSession();
    if (mode === 'hide') page.onHide(); else application.session.save({ token: 'B', user: { id: 'B' } });
    await modals[0].success({ confirm: true }); assert.equal(calls.some((item) => item.options && item.options.method === 'POST'), false);
  }
});
test('first question requires send, has the same one-turn quota semantics, and duplicate clicks send once', async () => {
  const posted = deferred(); let submissions = 0;
  const { page, calls } = fixture(async (path, options) => { if (options && options.method === 'POST') { submissions += 1; return posted.promise; } });
  await page.onShow(); assert.equal(submissions, 0);
  const sending = page.send(); await page.send(); assert.equal(submissions, 1);
  posted.resolve({ data: turn() }); await sending;
  assert.equal(page.data.question, ''); assert.equal(page.data.turns.length, 1); assert.equal(page.data.busy, false);
  assert.ok(calls.filter((item) => item.path === 'llm/status/').length >= 2);
});
test('uncertain network failure preserves the question and reuses request_id on retry', async () => {
  const ids = []; let fail = true;
  const { page } = fixture(async (path, options) => {
    if (options && options.method === 'POST') { ids.push(options.data.request_id); if (fail) throw new Error('连接中断'); return { data: turn() }; }
  });
  await page.onShow(); page.inputQuestion(change('  核对叶片特征  ')); await page.send();
  assert.equal(page.data.question.trim(), '核对叶片特征'); assert.match(page.data.actionError, /先刷新核对/);
  fail = false; await page.send(); assert.equal(ids.length, 2); assert.equal(ids[0], ids[1]);
});
test('daily quota zero or unknown and oversized or empty questions never create a turn', async () => {
  const { page, calls } = fixture(); await page.onShow();
  page.data.quota.remaining = 0; await page.send(); assert.match(page.data.actionError, /可用额度/);
  page.data.quota = null; await page.send(); page.data.quota = { ...quota };
  page.inputQuestion(change(' ')); await page.send(); page.inputQuestion(change('字'.repeat(501))); await page.send();
  assert.equal(calls.some((item) => item.options && item.options.method === 'POST'), false);
});
test('old account turn responses never display answers or clear a new account draft', async () => {
  const posted = deferred();
  const { page, application } = fixture(async (path, options) => options && options.method === 'POST' ? posted.promise : undefined);
  await page.onShow(); const sending = page.send(); application.session.save({ token: 'B', user: { id: 'B' } });
  posted.resolve({ data: turn('private-A', { answer: '私有回答' }) }); await sending;
  assert.equal(page.data.session, null); assert.equal(page.data.turns.length, 0); assert.equal(page.data.busy, false); assert.equal(application.session.token(), 'B');
});
test('hide stops polling, late replies cannot write, and returning resumes from authoritative turns', async () => {
  const polled = deferred(); let pendingPoll = true;
  const { page, calls } = fixture(async (path) => {
    if (path === 'llm/sessions/s1/turns/') return { data: [turn('t1', { status: pendingPoll ? 'running' : 'succeeded' })] };
    if (path === 'llm/turns/t1/') return polled.promise;
  });
  await page.onShow(); page.onHide(); const write = page.setData; page.setData = () => { throw new Error('hidden write'); };
  polled.resolve({ data: turn() }); await flush();
  assert.equal(page.data.turns.length, 0); page.setData = write; pendingPoll = false; await page.onShow();
  assert.equal(page.data.turns[0].status, 'succeeded'); assert.equal(calls.filter((item) => item.path === 'llm/sessions/s1/turns/').length, 2);
});
test('pause cancels timers, old callbacks cannot poll, and resume explicitly continues', async () => {
  const { page, timers, calls } = fixture(async (path) => path === 'llm/sessions/s1/turns/' ? { data: [turn('t1', { status: 'running' })] } : path === 'llm/turns/t1/' ? { data: turn('t1', { status: 'running' }) } : undefined);
  await page.onShow(); await flush(); assert.equal(timers.length, 1);
  page.pausePolling(); const count = calls.length; await timers[0].fn(); assert.equal(calls.length, count); assert.equal(timers[0].cleared, true); assert.equal(page.data.polling, false);
  await page.resumePolling(); assert.equal(page.data.polling, true); page.onUnload();
});
test('failed polling is recoverable and a deleted session clears private answers without continuing timers', async () => {
  const { page, timers } = fixture(async (path) => path === 'llm/sessions/s1/turns/' ? { data: [turn('t1', { status: 'queued' })] } : path === 'llm/turns/t1/' ? Promise.reject(Object.assign(new Error('会话已删除'), { status: 404 })) : undefined);
  await page.onShow(); await flush(); assert.equal(page.data.unavailable, true); assert.equal(page.data.turns.length, 0); assert.equal(page.data.polling, false); assert.equal(timers.length, 0);
});
test('turn pages stay scoped to one session and include pages beyond the latest twenty', async () => {
  const rows = Array.from({ length: 25 }, (_, index) => turn('t' + index));
  const { page } = fixture(async (path) => path === 'llm/sessions/s1/turns/' ? { data: rows.slice(0, 20), meta: { next: '/api/v1/llm/sessions/s1/turns/?page=2' } } : path.includes('page=2') ? { data: rows.slice(20) } : undefined);
  await page.onShow(); await page.more(); assert.equal(page.data.turns.length, 25);
  assert.throws(() => readPage({ data: [], meta: { next: '/api/v1/llm/sessions/other/turns/?page=2' } }, 'llm/sessions/s1/turns/', 'llm/sessions/s1/turns/', new Set()), /分页地址/);
});
test('existing no-image session states remain distinct from original machine results and unknown water quality', async () => {
  const { page, navigation } = fixture(async (path) => path === 'llm/sessions/s1/' ? { data: session('s1', { kind: 'assessment', assessment_job_id: 'a1', recognition_job_id: null, include_image: true, image_available: false }) } : undefined);
  await page.onShow(); assert.equal(page.data.session.image_available, false); assert.match(page.data.disclaimer, /官方水质评价/); page.original();
  assert.deepEqual(navigation, ['/pages/assessment/index?jobId=a1']);
});
test('returning while a turn is posting waits, and pull-to-refresh cannot bypass the mutation', async () => {
  const posted = deferred(); let reads = 0;
  const { page } = fixture(async (path, options) => { if (options && options.method === 'POST') return posted.promise; if (path === 'llm/sessions/s1/turns/') reads += 1; });
  await page.onShow(); const sending = page.send(); page.onHide(); const showing = page.onShow(); await page.onPullDownRefresh(); assert.equal(reads, 1);
  posted.resolve({ data: turn() }); await sending; await showing; assert.equal(reads, 2);
});
test('history lists all pages and creates no generic conversation', async () => {
  const { page, calls, navigation } = fixture(async (path) => path === 'llm/sessions/' ? { data: [session('s1')], meta: { next: '/api/v1/llm/sessions/?page=2' } } : path.includes('page=2') ? { data: [session('s2')] } : undefined, {}, false, 'llm-history');
  await page.onShow(); await page.more(); assert.equal(page.data.sessions.length, 2); page.open(idEvent('s2'));
  assert.deepEqual(navigation, ['/pages/llm/index?sessionId=s2']); assert.equal(calls.some((item) => item.options && item.options.method), false);
});
test('history deletion needs explicit confirmation, is private, and stale modal never deletes', async () => {
  for (const changeAccount of [false, true]) {
    let gone = false;
    const { page, application, calls, modals } = fixture(async (path, options) => { if (options && options.method === 'DELETE') { gone = true; return { data: null }; } if (path === 'llm/sessions/' && gone) return { data: [] }; }, {}, false, 'llm-history');
    await page.onShow(); page.remove(idEvent('s1')); page.remove(idEvent('s1')); assert.equal(modals.length, 1);
    if (changeAccount) application.session.save({ token: 'B', user: { id: 'B' } });
    await modals[0].success({ confirm: true }); await modals[0].success({ confirm: true });
    assert.equal(calls.filter((item) => item.options && item.options.method === 'DELETE').length, changeAccount ? 0 : 1); assert.equal(page.data.sessions.length, 0);
  }
});
test('private history results after hide and session renewal never enter the next account', async () => {
  const loading = deferred(); const { page, application } = fixture(async (path) => path === 'llm/sessions/' ? loading.promise : undefined, {}, false, 'llm-history');
  const showing = page.onShow(); application.session.save({ token: 'B', user: { id: 'B' } }); loading.resolve({ data: [session('private-A')] }); await showing;
  assert.equal(page.data.sessions.length, 0); assert.equal(page.data.quota, null);
});
test('a history delete response after account renewal clears the old list without changing the new login', async () => {
  const removed = deferred(); const { page, application, modals } = fixture(async (path, options) => options && options.method === 'DELETE' ? removed.promise : undefined, {}, false, 'llm-history');
  await page.onShow(); page.remove(idEvent('s1')); const deleting = modals[0].success({ confirm: true });
  application.session.save({ token: 'B', user: { id: 'B' } }); removed.resolve({ data: null }); await deleting;
  assert.equal(page.data.sessions.length, 0); assert.equal(page.data.busy, false); assert.equal(application.session.token(), 'B');
});
test('result entries only navigate from a completed current-account task, never create or send automatically', () => {
  for (const kind of ['recognition', 'assessment']) {
    let definition; const navigation = []; let token = 'A';
    global.Page = (value) => { definition = value; }; global.wx = { navigateTo: ({ url }) => navigation.push(url) };
    global.getApp = () => ({ session: { token: () => token } });
    const path = require.resolve('../pages/' + (kind === 'recognition' ? 'recognize' : 'assessment') + '/index'); delete require.cache[path]; require(path);
    const page = { ...definition, data: { task: { id: 'job', status: 'queued' }, busy: false }, _visible: true, _sessionToken: 'A' };
    page.openAI(); assert.equal(navigation.length, 0); page.data.task.status = 'succeeded'; page.openAI();
    assert.deepEqual(navigation, ['/pages/llm/index?kind=' + kind + '&jobId=job']);
    token = 'B'; page.openAI(); token = 'A'; page._visible = false; page.openAI(); assert.equal(navigation.length, 1);
  }
});
