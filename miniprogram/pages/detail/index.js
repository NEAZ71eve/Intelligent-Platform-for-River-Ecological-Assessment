const { app, requireLogin, toast, detail } = require('../../lib/page');
const { list, time, value, message } = require('../../lib/format');
const { loadAll } = require('../../lib/region');
Page({
  data: { loading: true, error: '', item: null, kind: '', busy: false, favoriteId: '', stations: [], stationIndex: 0, observations: [], observationError: '', observationLoading: false, recordError: '' },
  onLoad(options) {
    this._alive = true;
    const paths = { place: 'places/', content: 'contents/', route: 'routes/' };
    if (!paths[options.kind] || !options.id) { this.setData({ loading: false, error: '此资料链接无效' }); return; }
    this._id = options.id;
    this._path = paths[options.kind] + encodeURIComponent(options.id) + '/';
    this.setData({ kind: options.kind });
    return this.load();
  },
  onShow() {
    if (this._alive === false) return;
    if (this._path && (this._hidden || this._identity !== app().session.token())) { this._hidden = false; return this.load(); }
  },
  onHide() { this._hidden = true; this._generation = (this._generation || 0) + 1; this._observationsGeneration = (this._observationsGeneration || 0) + 1; },
  onUnload() { this._alive = false; this.onHide(); },
  onPullDownRefresh() { return this.load(); },
  current(generation) { return this._alive !== false && !this._hidden && generation === this._generation; },
  sameSession(generation, token) { return this.current(generation) && token === app().session.token(); },
  async load() {
    if (this._alive === false || this._hidden) return;
    if (!this._path) { wx.stopPullDownRefresh(); return; }
    this._hidden = false;
    const generation = this._generation = (this._generation || 0) + 1;
    const token = this._identity = app().session.token();
    this.setData({ loading: true, error: '', recordError: '', favoriteId: '', busy: false, stations: [], observations: [], observationError: '', observationLoading: false });
    try {
      const item = (await app().api.request(this._path)).data;
      if (!this.current(generation)) return;
      this.setData({ item: Object.assign({}, item, { updated_label: time(item.updated_at || item.published_at) }) });
      wx.setNavigationBarTitle({ title: item.name || item.title || '生态资料' });
      if (this.data.kind === 'place') await this.loadStations(generation);
      if (this.data.kind !== 'route' && token && this.sameSession(generation, token)) {
        try {
          const target = this.target();
          const favorites = await loadAll(app().api, 'favorites/', target);
          if (!this.sameSession(generation, token)) return;
          const found = favorites.find((favorite) => this.matches(favorite));
          this.setData({ favoriteId: found ? found.id : '' });
          if ((app().session.get().user || {}).record_history) await app().api.request('histories/', { method: 'POST', data: target });
        } catch (error) {
          if (this.sameSession(generation, token)) this.setData({ recordError: message(error) });
        }
      }
    } catch (error) { if (this.current(generation)) this.setData({ error: message(error), item: null }); }
    finally {
      if (this.current(generation)) {
        if (!this.sameSession(generation, token)) this.setData({ favoriteId: '', recordError: '登录状态已变化，请刷新个人记录。' });
        this.setData({ loading: false }); wx.stopPullDownRefresh();
      }
    }
  },
  target() { return this.data.kind === 'place' ? { place_id: this._id } : { content_id: this._id }; },
  matches(record) {
    const target = record[this.data.kind];
    return record[this.data.kind + '_id'] === this._id || (typeof target === 'string' ? target === this._id : target && target.id === this._id);
  },
  async loadStations(generation = this._generation) {
    try {
      const stations = await loadAll(app().api, 'stations/', { place: this._id });
      if (!this.current(generation)) return;
      this.setData({ stations, stationIndex: 0, observations: [], observationError: '' });
      if (stations.length) await this.loadObservations();
    } catch (error) { if (this.current(generation)) this.setData({ observationError: message(error) }); }
  },
  async loadObservations() {
    const generation = this._generation;
    if (!this.current(generation)) return;
    const station = this.data.stations[this.data.stationIndex];
    if (!station) return this.loadStations(generation);
    const request = this._observationsGeneration = (this._observationsGeneration || 0) + 1;
    const current = () => this.current(generation) && request === this._observationsGeneration;
    this.setData({ observations: [], observationLoading: true, observationError: '' });
    try {
      const result = await app().api.request('observations/', { data: { station: station.id, source_type: 'simulation', page_size: 12 } });
      if (!current()) return;
      this.setData({ observations: list(result).map((item) => Object.assign({}, item, {
        value_label: item.quality_status === 'valid' ? value(item.value) : '—', time_label: time(item.observed_at),
        quality_label: { missing: '缺失', suspect: '存疑', valid: '有效' }[item.quality_status] || '状态未知',
      })) });
    } catch (error) { if (current()) this.setData({ observationError: message(error) }); }
    finally { if (current()) this.setData({ observationLoading: false }); }
  },
  changeStation(event) {
    if (!this.current(this._generation)) return;
    const index = Number(event.detail.value);
    if (!this.data.stations[index]) return;
    this.setData({ stationIndex: index }); return this.loadObservations();
  },
  async toggleFavorite() {
    const generation = this._generation;
    if (!this.current(generation) || this.data.busy || !requireLogin()) return;
    const token = app().session.token();
    this.setData({ busy: true });
    try {
      let favoriteId = '';
      if (this.data.favoriteId) await app().api.request('favorites/' + this.data.favoriteId + '/', { method: 'DELETE' });
      else favoriteId = (await app().api.request('favorites/', { method: 'POST', data: this.target() })).data.id;
      if (!this.sameSession(generation, token)) return;
      this.setData({ favoriteId });
      wx.showToast({ title: favoriteId ? '已收藏' : '已取消收藏', icon: 'success' });
    } catch (error) { if (this.sameSession(generation, token)) toast(error); }
    finally {
      if (this.current(generation)) {
        if (!this.sameSession(generation, token)) this.setData({ favoriteId: '', recordError: '登录状态已变化，请刷新个人记录。' });
        this.setData({ busy: false });
      }
    }
  },
  visit() {
    const generation = this._generation;
    if (!this.current(generation) || this.data.busy || !requireLogin()) return;
    const token = app().session.token();
    wx.showModal({ title: '记录这次游览', content: '这是一条由你自行添加的游览记录，不使用定位，也不证明真实到访。', confirmText: '添加记录', success: async (result) => {
      if (!result.confirm || this.data.busy || !this.sameSession(generation, token)) return;
      this.setData({ busy: true });
      try {
        await app().api.request('visits/', { method: 'POST', data: { place_id: this._id } });
        if (this.sameSession(generation, token)) wx.showToast({ title: '已记录游览', icon: 'success' });
      } catch (error) { if (this.sameSession(generation, token)) toast(error); }
      finally { if (this.current(generation)) this.setData({ busy: false }); }
    } });
  },
  openWater() {
    if (!this.current(this._generation)) return;
    const item = this.data.item;
    if (item && item.water_body_id) wx.navigateTo({ url: '/pages/water/index?region=' + encodeURIComponent(item.region) + '&waterBodyId=' + encodeURIComponent(item.water_body_id) });
  },
  openDataCenter() {
    if (!this.current(this._generation)) return;
    const item = this.data.item, station = this.data.stations[this.data.stationIndex];
    if (!item || !station) return;
    wx.navigateTo({ url: '/pages/data-center/index?region=' + encodeURIComponent(item.region) + '&stationId=' + encodeURIComponent(station.id) + '&kind=' + encodeURIComponent(station.kind) });
  },
  openPlace(event) { if (this.current(this._generation)) detail('place', event.currentTarget.dataset.id); },
});
