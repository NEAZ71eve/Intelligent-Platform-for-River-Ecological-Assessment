const { app, requireLogin, detail, toast } = require('../../lib/page');
const { time, task, message } = require('../../lib/format');
const { assessmentTask } = require('../../lib/assessment');
const titles = { favorites: '我的收藏', histories: '浏览记录', 'recognition-jobs': '识别记录', 'assessment-jobs': '河道观察记录', visits: '游览记录' };

function pageKey(path, kind) {
  if (typeof path !== 'string' || /[\s\\#]/.test(path)) throw new Error('个人记录分页地址无效，请刷新重试');
  const match = path.match(/^(?:https?:\/\/[^/?#]+)?(?:\/api\/v1\/)?([^/?]+)\/(\?[^#]*)?$/);
  if (!match || match[1] !== kind) throw new Error('个人记录分页地址无效，请刷新重试');
  return match[1] + '/' + (match[2] || '');
}
function present(record, kind) {
  if (!record || typeof record.id !== 'string' || !record.id) throw new Error('个人记录返回格式不正确，请重试');
  if (kind === 'recognition-jobs') return Object.assign(task(record), { title: '植物识别任务' });
  if (kind === 'assessment-jobs') return assessmentTask(record);
  const targetKind = record.content || record.content_id ? 'content' : 'place';
  const item = record[targetKind];
  const unavailable = item === null || (!item && !record[targetKind + '_id']);
  return Object.assign({}, record, {
    target_kind: targetKind,
    unavailable,
    target_id: typeof item === 'string' ? item : item && item.id || record[targetKind + '_id'],
    title: unavailable ? '原资料已删除或下架' : item && (item.title || item.name) || '已保存的资料',
    created_label: time(record.visited_at || record.viewed_at || record.created_at),
  });
}
Page({
  data: { loading: true, loadingMore: false, error: '', kind: '', title: '', records: [], next: null, busy: false },
  onLoad(options) {
    if (!titles[options.kind]) { this.setData({ loading: false, error: '记录类型无效' }); return; }
    this.setData({ kind: options.kind, title: titles[options.kind] });
    wx.setNavigationBarTitle({ title: titles[options.kind] });
  },
  async onShow() {
    this._visible = true;
    const shown = this._showVersion = (this._showVersion || 0) + 1;
    if (this._pendingDelete && this._pendingDelete.token === app().session.token()) {
      this.setData({ loading: true });
      await this._pendingDelete.promise;
      if (!this._active() || shown !== this._showVersion) return;
    }
    return this.load();
  },
  onHide() {
    this._visible = false;
    this._invalidate();
    this.setData({ records: [], next: null, loading: false, loadingMore: false, busy: false });
  },
  onUnload() { this._destroyed = true; this._invalidate(); },
  _invalidate() {
    this._showVersion = (this._showVersion || 0) + 1;
    this._requestVersion = (this._requestVersion || 0) + 1;
    this._actionVersion = (this._actionVersion || 0) + 1;
    this._loading = false;
    this._confirming = false;
    this._recordsToken = '';
  },
  _active() { return !this._destroyed && this._visible !== false; },
  _clearPrivate() {
    this._recordsToken = '';
    this._confirming = false;
    this.setData({ records: [], next: null, error: '登录状态已变化，请重新登录或刷新' });
  },
  _current(version, token) {
    if (!this._active() || version !== this._requestVersion) return false;
    if (app().session.token() !== token) { this._clearPrivate(); return false; }
    return true;
  },
  _hasPendingDelete() { return !!(this._pendingDelete && !this._pendingDelete.settled && this._pendingDelete.token === app().session.token()); },
  _canAct() {
    if (!this._active() || this.data.busy || this._hasPendingDelete()) return false;
    if (this._recordsToken && this._recordsToken !== app().session.token()) { this._clearPrivate(); return false; }
    if (!requireLogin()) { this._clearPrivate(); return false; }
    return true;
  },
  onPullDownRefresh() { return this.load(); },
  onReachBottom() { if (this.data.next && !this.data.loadingMore && !this.data.loading) return this.load(true); },
  async load(more) {
    if (!this._active()) return;
    if (this._hasPendingDelete()) { wx.stopPullDownRefresh(); return; }
    more = more === true;
    if (!this.data.kind) { this.setData({ loading: false }); wx.stopPullDownRefresh(); return; }
    if (!requireLogin()) {
      this._invalidate();
      this.setData({ records: [], next: null, error: '请登录后查看个人记录', loading: false, loadingMore: false });
      wx.stopPullDownRefresh();
      return;
    }
    if (more && (!this.data.next || this._loading || this.data.busy)) return;
    const sentToken = app().session.token();
    if (more && this._recordsToken && this._recordsToken !== sentToken) { this._clearPrivate(); return this.load(); }
    if (this._recordsToken && this._recordsToken !== sentToken) this._clearPrivate();
    const version = this._requestVersion = (this._requestVersion || 0) + 1;
    const path = more ? this.data.next : this.data.kind + '/';
    this._loading = true;
    this.setData({ loading: !more, loadingMore: more, error: '' });
    try {
      const key = pageKey(path, this.data.kind);
      const seen = more ? new Set(this._seenPages || []) : new Set();
      if (seen.has(key)) throw new Error('个人记录分页重复，请刷新重试');
      const response = await app().api.request(path);
      if (!this._current(version, sentToken)) return;
      if (!response || !Array.isArray(response.data)) throw new Error('个人记录返回格式不正确，请重试');
      const next = response.meta && response.meta.next;
      if (next !== undefined && next !== null && typeof next !== 'string') throw new Error('个人记录分页格式不正确，请重试');
      seen.add(key);
      if (next && seen.has(pageKey(next, this.data.kind))) throw new Error('个人记录分页重复，请刷新重试');
      const incoming = response.data.map((record) => present(record, this.data.kind));
      const merged = new Map((more ? this.data.records : []).map((record) => [record.id, record]));
      incoming.forEach((record) => merged.set(record.id, record));
      this._seenPages = seen;
      this._recordsToken = sentToken;
      this.setData({ records: Array.from(merged.values()), next: next || null });
    } catch (error) {
      if (!this._current(version, sentToken)) return;
      this.setData({ error: message(error) });
    } finally {
      if (this._active() && version === this._requestVersion) {
        this._loading = false;
        this.setData({ loading: false, loadingMore: false });
        wx.stopPullDownRefresh();
      }
    }
  },
  more() { return this.load(true); },
  open(event) {
    if (!this._canAct() || this.data.loading) return;
    const record = this.data.records.find((item) => item.id === event.currentTarget.dataset.id);
    if (!record) return;
    if (this.data.kind === 'assessment-jobs') { wx.navigateTo({ url: '/pages/assessment/index?jobId=' + encodeURIComponent(record.id) }); return; }
    if (this.data.kind === 'recognition-jobs') { app().globalData.recognitionJobId = record.id; wx.switchTab({ url: '/pages/recognize/index' }); return; }
    if (record.target_id && !record.unavailable) detail(record.target_kind, record.target_id);
    else toast(new Error('原资料可能已经删除或暂不可用'));
  },
  remove(event) {
    if (!this._canAct() || this._confirming) return;
    const id = event.currentTarget.dataset.id;
    if (typeof id !== 'string' || !id) return;
    const sentToken = app().session.token();
    const action = this._actionVersion = (this._actionVersion || 0) + 1;
    const current = () => this._active() && action === this._actionVersion && app().session.token() === sentToken;
    let handled = false;
    this._confirming = true;
    wx.showModal({ title: '删除这条记录', content: ['recognition-jobs', 'assessment-jobs'].includes(this.data.kind) ? '删除任务、关联图片、可选位置及关联的 AI 解读会话，无法恢复。' : '删除后，这条个人记录将不再显示。', confirmText: '删除', confirmColor: '#a25e4a', success: async (result) => {
      if (handled) return;
      handled = true;
      if (!current()) { if (this._active() && app().session.token() !== sentToken) this._clearPrivate(); return; }
      this._confirming = false;
      if (!result.confirm) return;
      // A pending page may contain the soon-to-be-deleted item. Never merge it later.
      this._requestVersion = (this._requestVersion || 0) + 1;
      this._loading = false;
      this.setData({ busy: true, loading: false, loadingMore: false, error: '' });
      const pending = { token: sentToken };
      pending.promise = new Promise((resolve) => { pending.resolve = resolve; });
      this._pendingDelete = pending;
      try {
        try { await app().api.request(this.data.kind + '/' + encodeURIComponent(id) + '/', { method: 'DELETE' }); }
        catch (error) { if (error.status !== 404) throw error; }
        pending.settled = true;
        if (!current()) { if (this._active() && app().session.token() !== sentToken) this._clearPrivate(); return; }
        this.setData({ records: this.data.records.filter((record) => record.id !== id), next: null });
        wx.showToast({ title: '记录已删除', icon: 'success' });
        await this.load();
      } catch (error) {
        if (!current()) { if (this._active() && app().session.token() !== sentToken) this._clearPrivate(); return; }
        this.setData({ error: message(error) });
        toast(error);
      } finally {
        if (this._pendingDelete === pending) this._pendingDelete = null;
        pending.resolve();
        if (this._active() && action === this._actionVersion) this.setData({ busy: false });
      }
    }, fail: () => { if (current()) this._confirming = false; } });
  },
});
