const { app, detail, finish } = require('../../lib/page');
const { list, message } = require('../../lib/format');
Page({
  data: { loading: true, error: '', contents: [], routes: [], tab: 'contents' },
  onLoad() { this.load(); },
  onPullDownRefresh() { this.load(); },
  async load() {
    if (this._loading) return;
    this._loading = true;
    this.setData({ loading: true, error: '' });
    try {
      const result = await Promise.all([app().api.request('contents/'), app().api.request('routes/')]);
      this.setData({ contents: list(result[0]), routes: list(result[1]) });
    } catch (error) { this.setData({ error: message(error) }); }
    finally { this._loading = false; finish(this); }
  },
  changeTab(event) { this.setData({ tab: event.currentTarget.dataset.tab }); },
  open(event) { detail(event.currentTarget.dataset.kind, event.currentTarget.dataset.id); },
});
