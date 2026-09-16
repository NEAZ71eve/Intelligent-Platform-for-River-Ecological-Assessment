const { app, requireLogin, toast, finish, detail } = require('../../lib/page');
const { list, time, value, message } = require('../../lib/format');
Page({
  data: { loading: true, error: '', item: null, kind: '', busy: false, favoriteId: '', stations: [], stationIndex: 0, observations: [], observationError: '', observationLoading: false, recordError: '' },
  onLoad(options) {
    const paths = { place: 'places/', content: 'contents/', route: 'routes/' };
    if (!paths[options.kind] || !options.id) { this.setData({ loading: false, error: '此资料链接无效' }); return; }
    this._id = options.id;
    this._path = paths[options.kind] + encodeURIComponent(options.id) + '/';
    this.setData({ kind: options.kind });
    this.load();
  },
  onPullDownRefresh() { this.load(); },
  async load() {
    if (!this._path || this._loading) { wx.stopPullDownRefresh(); return; }
    this._loading = true;
    this.setData({ loading: true, error: '', recordError: '' });
    try {
      const item = (await app().api.request(this._path)).data;
      this.setData({ item: Object.assign({}, item, { updated_label: time(item.updated_at || item.published_at) }) });
      wx.setNavigationBarTitle({ title: item.name || item.title || '生态资料' });
      if (this.data.kind === 'place') await this.loadStations();
      if (this.data.kind !== 'route' && app().session.token()) {
        try {
          const target = this.target();
          const favorites = list(await app().api.request('favorites/', { data: Object.assign({ page_size: 100 }, target) }));
          const found = favorites.find((favorite) => this.matches(favorite));
          this.setData({ favoriteId: found ? found.id : '' });
          if ((app().session.get().user || {}).record_history) await app().api.request('histories/', { method: 'POST', data: target });
        } catch (error) { this.setData({ recordError: message(error) }); }
      }
    } catch (error) { this.setData({ error: message(error) }); }
    finally { this._loading = false; finish(this); }
  },
  target() { return this.data.kind === 'place' ? { place_id: this._id } : { content_id: this._id }; },
  matches(record) {
    const target = record[this.data.kind];
    return record[this.data.kind + '_id'] === this._id || (typeof target === 'string' ? target === this._id : target && target.id === this._id);
  },
  async loadStations() {
    try {
      const stations = list(await app().api.request('stations/', { data: { place: this._id } }));
      this.setData({ stations, stationIndex: 0, observations: [], observationError: '' });
      if (stations.length) await this.loadObservations();
    } catch (error) { this.setData({ observationError: message(error) }); }
  },
  async loadObservations() {
    const station = this.data.stations[this.data.stationIndex];
    if (!station) { this.loadStations(); return; }
    this.setData({ observationLoading: true, observationError: '' });
    try {
      const result = await app().api.request('observations/', { data: { station: station.id, source_type: 'simulation', page_size: 12 } });
      this.setData({ observations: list(result).map((item) => Object.assign({}, item, { value_label: value(item.value), time_label: time(item.observed_at), quality_label: item.quality_status === 'missing' ? '缺失' : item.quality_status })) });
    } catch (error) { this.setData({ observationError: message(error) }); }
    finally { this.setData({ observationLoading: false }); }
  },
  changeStation(event) { this.setData({ stationIndex: Number(event.detail.value) }); this.loadObservations(); },
  async toggleFavorite() {
    if (this.data.busy || !requireLogin()) return;
    this.setData({ busy: true });
    try {
      if (this.data.favoriteId) {
        await app().api.request('favorites/' + this.data.favoriteId + '/', { method: 'DELETE' });
        this.setData({ favoriteId: '' });
      } else {
        const result = (await app().api.request('favorites/', { method: 'POST', data: this.target() })).data;
        this.setData({ favoriteId: result.id });
      }
      wx.showToast({ title: this.data.favoriteId ? '已收藏' : '已取消收藏', icon: 'success' });
    } catch (error) { toast(error); }
    finally { this.setData({ busy: false }); }
  },
  visit() {
    if (this.data.busy || !requireLogin()) return;
    wx.showModal({ title: '记录这次游览', content: '这是一条由你自行添加的游览记录，不使用定位，也不证明真实到访。', confirmText: '添加记录', success: async (result) => {
      if (!result.confirm) return;
      this.setData({ busy: true });
      try { await app().api.request('visits/', { method: 'POST', data: { place_id: this._id } }); wx.showToast({ title: '已记录游览', icon: 'success' }); }
      catch (error) { toast(error); }
      finally { this.setData({ busy: false }); }
    } });
  },
  openPlace(event) { detail('place', event.currentTarget.dataset.id); },
});
