const { app, requireLogin, detail, toast, finish } = require('../../lib/page');
const { list, time, task, message } = require('../../lib/format');
const { assessmentTask } = require('../../lib/assessment');
const titles = { favorites: '我的收藏', histories: '浏览记录', 'recognition-jobs': '识别记录', 'assessment-jobs': '河道观察记录', visits: '游览记录' };
Page({
  data: { loading: true, loadingMore: false, error: '', kind: '', title: '', records: [], next: null, busy: false },
  onLoad(options) {
    if (!titles[options.kind]) { this.setData({ loading: false, error: '记录类型无效' }); return; }
    this.setData({ kind: options.kind, title: titles[options.kind] });
    wx.setNavigationBarTitle({ title: titles[options.kind] });
    this.load();
  },
  onUnload() { this._destroyed = true; },
  onPullDownRefresh() { this.load(); },
  onReachBottom() { if (this.data.next && !this.data.loadingMore && !this.data.loading) this.load(true); },
  async load(more) {
    if (this._destroyed) return;
    more = more === true;
    if (!this.data.kind) { finish(this); return; }
    if (!requireLogin()) { this.setData({ records: [], next: null, error: '请登录后查看个人记录' }); finish(this); return; }
    if (this._loading) return;
    this._loading = true;
    const sentToken = app().session.token();
    this.setData({ loading: !more, loadingMore: more, error: '' });
    try {
      const response = await app().api.request(more ? this.data.next : this.data.kind + '/');
      if (this._destroyed) return;
      if (app().session.token() !== sentToken) {
        this.setData({ records: [], next: null, error: '登录状态已变化，请刷新后查看个人记录' });
        return;
      }
      const records = list(response).map((record) => {
        if (this.data.kind === 'recognition-jobs') return Object.assign(task(record), { title: '植物识别任务' });
        if (this.data.kind === 'assessment-jobs') return assessmentTask(record);
        const kind = record.content || record.content_id ? 'content' : 'place';
        const item = record[kind];
        const unavailable = item === null || (!item && !record[kind + '_id']);
        return Object.assign({}, record, {
          target_kind: kind,
          unavailable,
          target_id: typeof item === 'string' ? item : item && item.id || record[kind + '_id'],
          title: unavailable ? '原资料已删除或下架' : item && (item.title || item.name) || record.title || record.place_name || record.content_title || '已保存的资料',
          created_label: time(record.visited_at || record.viewed_at || record.created_at || record.last_viewed_at),
        });
      });
      this.setData({ records: more ? this.data.records.concat(records) : records, next: response.meta && response.meta.next || null });
    } catch (error) {
      if (this._destroyed) return;
      if (app().session.token() !== sentToken) this.setData({ records: [], next: null, error: '登录状态已变化，请重新登录或刷新' });
      else this.setData({ error: message(error) });
    }
    finally { this._loading = false; if (!this._destroyed) { this.setData({ loadingMore: false }); finish(this); } }
  },
  more() { this.load(true); },
  open(event) {
    if (this.data.kind === 'assessment-jobs') { wx.navigateTo({ url: '/pages/assessment/index?jobId=' + encodeURIComponent(event.currentTarget.dataset.id) }); return; }
    if (this.data.kind === 'recognition-jobs') { app().globalData.recognitionJobId = event.currentTarget.dataset.id; wx.switchTab({ url: '/pages/recognize/index' }); return; }
    const record = this.data.records.find((item) => item.id === event.currentTarget.dataset.id);
    if (record && record.target_id && !record.unavailable) detail(record.target_kind, record.target_id);
    else toast(new Error('原资料可能已经删除或暂不可用'));
  },
  remove(event) {
    if (this._destroyed || this.data.busy || !requireLogin()) return;
    const sentToken = app().session.token();
    const id = event.currentTarget.dataset.id;
    wx.showModal({ title: '删除这条记录', content: ['recognition-jobs', 'assessment-jobs'].includes(this.data.kind) ? '删除任务、关联图片及可选位置，无法恢复。' : '删除后，这条个人记录将不再显示。', confirmText: '删除', confirmColor: '#a25e4a', success: async (result) => {
      if (this._destroyed || !result.confirm || app().session.token() !== sentToken) return;
      this.setData({ busy: true });
      try { await app().api.request(this.data.kind + '/' + encodeURIComponent(id) + '/', { method: 'DELETE' }); await this.load(); }
      catch (error) { if (!this._destroyed) { toast(error); if (app().session.token() !== sentToken) this.setData({ records: [], next: null }); } }
      finally { if (!this._destroyed) this.setData({ busy: false }); }
    } });
  },
});
