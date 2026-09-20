const test = require('node:test');
const assert = require('node:assert/strict');
const { routeView } = require('../lib/route-view');
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
function fixture(extra) {
  const calls = [], navigation = [];
  const application = { globalData: {}, session: { token: () => '', get: () => ({ user: null }) }, api: { request: async (path, options) => {
    calls.push({ path, options });
    const custom = extra && await extra(path, options);
    if (custom) return custom;
    if (path === 'places/p/') return { data: { id: 'p', name: '公开地点', region: 'r' } };
    if (path === 'contents/c/') return { data: { id: 'c', title: '观察稿', place: 'p', place_summary: { id: 'p', name: '公开地点' }, plant_label: 'daisy', source: '原创' } };
    return { data: [], meta: { count: 0, next: null } };
  } } };
  let definition;
  global.getApp = () => application;
  global.Page = (value) => { definition = value; };
  global.wx = { stopPullDownRefresh() {}, setNavigationBarTitle() {}, navigateTo: ({ url }) => navigation.push(url), switchTab: ({ url }) => navigation.push(url) };
  const path = require.resolve('../pages/detail/index'); delete require.cache[path]; require(path);
  const page = { ...definition, data: structuredClone(definition.data), setData(patch) { Object.assign(this.data, patch); } };
  return { page, application, calls, navigation };
}
test('place previews public related articles and carries the exact place filter to the paginated catalogue', async () => {
  const { page, calls, navigation, application } = fixture(async (path) => path === 'contents/' ? { data: [{ id: 'c', title: '关联文章', source: '原创' }], meta: { count: 8, next: 'contents/?page=2' } } : null);
  await page.onLoad({ kind: 'place', id: 'p' });
  assert.deepEqual(calls.find((call) => call.path === 'contents/').options.data, { place: 'p', page_size: 3 });
  assert.equal(page.data.relatedCount, 8); assert.equal(page.data.relatedContents.length, 1);
  page.openRelatedContent({ currentTarget: { dataset: { id: 'c' } } });
  page.openRelatedContent({ currentTarget: { dataset: { id: 'not-returned' } } });
  page.openRelatedContents();
  assert.deepEqual(application.globalData.pendingKnowledgeFilter, { tab: 'contents', region: 'r', place: 'p' });
  assert.deepEqual(navigation, ['/pages/detail/index?kind=content&id=c', '/pages/learn/index']);
});
test('related article failure does not hide place details and retry recovers independently', async () => {
  let failed = true;
  const { page } = fixture(async (path) => { if (path === 'contents/' && failed) throw new Error('资料暂不可用'); return null; });
  await page.onLoad({ kind: 'place', id: 'p' });
  assert.equal(page.data.item.id, 'p'); assert.equal(page.data.error, '');
  assert.match(page.data.relatedError, /暂不可用/);
  failed = false; await page.loadRelatedContents();
  assert.equal(page.data.relatedError, ''); assert.equal(page.data.relatedLoading, false);
});
test('a content detail links only its public associated place and opens its plant label without an old place filter', async () => {
  const { page, application, navigation } = fixture();
  application.globalData.pendingKnowledgeFilter = { tab: 'contents', place: 'old' };
  await page.onLoad({ kind: 'content', id: 'c' });
  page.openAssociatedPlace(); page.openPlantContents();
  assert.deepEqual(application.globalData.pendingKnowledgeFilter, { tab: 'contents', plant_label: 'daisy' });
  assert.deepEqual(navigation, ['/pages/detail/index?kind=place&id=p', '/pages/learn/index']);
  page.data.item.place_summary = null; page.openAssociatedPlace();
  assert.equal(navigation.length, 2);
});
test('old related responses and queued navigation cannot mutate a hidden or destroyed detail', async () => {
  const pending = deferred();
  const { page, application, navigation } = fixture(async (path) => path === 'contents/' ? pending.promise : null);
  const loading = page.onLoad({ kind: 'place', id: 'p' }); await new Promise(setImmediate);
  page.onHide(); page.setData = () => { throw new Error('hidden write'); };
  pending.resolve({ data: [{ id: 'c' }], meta: { count: 1 } }); await loading;
  for (const unload of [false, true]) {
    if (unload) page.onUnload();
    await page.loadRelatedContents(); page.openRelatedContents();
    page.openRelatedContent({ currentTarget: { dataset: { id: 'c' } } });
    page.openAssociatedPlace(); page.openPlantContents();
  }
  assert.deepEqual(navigation, []); assert.equal(application.globalData.pendingKnowledgeFilter, undefined);
});
test('a late related retry cannot replace a newer result', async () => {
  const pending = deferred(); let sequence = 0;
  const { page } = fixture(async (path) => {
    if (path !== 'contents/') return null;
    sequence += 1;
    if (sequence === 2) return pending.promise;
    return { data: [{ id: sequence === 1 ? 'initial' : 'new' }], meta: { count: 1 } };
  });
  await page.onLoad({ kind: 'place', id: 'p' });
  const old = page.loadRelatedContents(); await page.loadRelatedContents();
  pending.resolve({ data: [{ id: 'old' }], meta: { count: 1 } }); await old;
  assert.equal(page.data.relatedContents[0].id, 'new');
});
const route = { id: 'r1', region: 'r', title: '示范路线', source: '原创', stops: [
  { id: 's3', order: 8, place: { id: 'p3', name: '第三站' } },
  { id: 's1', order: 1, place: { id: 'p1', name: '第一站' } },
  { id: 's2', order: 4, place: { id: 'p2', name: '第二站' } },
] };
test('route browsing uses ordered public stops without inventing visits or displaying holes as missing destinations', () => {
  const selection = routeView({ stops: [...route.stops, { id: 'removed', order: 2, place: null }, route.stops[0]] }, 's2');
  assert.deepEqual(selection.routeStops.map((item) => [item.id, item.position]), [['s1', 1], ['s2', 2], ['s3', 3]]);
  assert.equal(selection.stopIndex, 1); assert.equal(selection.activeStop.id, 's2');
  assert.equal(routeView({ stops: [] }).activeStop, null);
});
test('route previous/next, selected-place link and return-to-region list preserve the public route context', async () => {
  const { page, calls, navigation, application } = fixture(async (path) => path === 'routes/r1/' ? { data: route } : null);
  await page.onLoad({ kind: 'route', id: 'r1' });
  assert.equal(page.data.activeStop.id, 's1');
  page.stepRoute({ currentTarget: { dataset: { direction: 'previous' } } });
  assert.equal(page.data.stopIndex, 0);
  page.stepRoute({ currentTarget: { dataset: { direction: 'next' } } });
  page.openRouteStop();
  assert.equal(navigation[0], '/pages/detail/index?kind=place&id=p2');
  page.selectRouteStop({ currentTarget: { dataset: { id: 'unknown' } } });
  assert.equal(page.data.activeStop.id, 's2');
  page.openRouteList();
  assert.deepEqual(application.globalData.pendingKnowledgeFilter, { tab: 'routes', region: 'r' });
  assert.equal(navigation[1], '/pages/learn/index');
  assert.ok(calls.every((call) => !call.options || !call.options.method));
});
test('returning from a route place keeps selection, and a newly hidden stop is removed on refresh', async () => {
  let current = structuredClone(route);
  const { page } = fixture(async (path) => path === 'routes/r1/' ? { data: current } : null);
  await page.onLoad({ kind: 'route', id: 'r1' });
  page.selectRouteStop({ currentTarget: { dataset: { id: 's2' } } });
  page.onHide(); await page.onShow(); assert.equal(page.data.activeStop.id, 's2');
  current = { ...current, stops: current.stops.filter((stop) => stop.id !== 's2') };
  page.onHide(); await page.onShow();
  assert.equal(page.data.activeStop.id, 's1'); assert.equal(page.data.routeStops.length, 2);
});
test('empty routes cannot navigate to stale stops, and hidden route interactions do nothing', async () => {
  const { page, navigation } = fixture(async (path) => path === 'routes/r1/' ? { data: { ...route, stops: [] } } : null);
  await page.onLoad({ kind: 'route', id: 'r1' });
  page.openRouteStop(); page.stepRoute({ currentTarget: { dataset: { direction: 'next' } } });
  assert.equal(page.data.activeStop, null); assert.deepEqual(navigation, []);
  page.onHide(); page.setData = () => { throw new Error('hidden write'); };
  page.openRouteList(); page.openRouteStop();
  page.selectRouteStop({ currentTarget: { dataset: { id: 's1' } } });
  page.stepRoute({ currentTarget: { dataset: { direction: 'next' } } });
  assert.deepEqual(navigation, []);
});
