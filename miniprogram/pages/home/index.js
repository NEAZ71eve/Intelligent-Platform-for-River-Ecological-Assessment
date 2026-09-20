const { app, finish } = require('../../lib/page');
const { list, time, value, message } = require('../../lib/format');
Page({
  data: { loading: true, error: '', regions: [], regionIndex: 0, region: null, weather: null, air: null, alerts: [], alertNotice: '', sections: [], health: null },
  onLoad() { this.load(); },
  onPullDownRefresh() { this.load(); },
  async load() {
    if (this._loading) return;
    this._loading = true;
    this.setData({ loading: true, error: '' });
    try {
      const results = await Promise.all([app().api.request('health/'), app().api.request('regions/')]);
      app().globalData.health = results[0].data;
      const regions = list(results[1]);
      const selected = app().globalData.region;
      const index = selected ? Math.max(regions.findIndex((item) => item.id === selected.id), 0) : 0;
      const region = regions[index] || null;
      this.setData({ health: results[0].data, regions, regionIndex: index, region });
      app().globalData.region = region;
      if (region) await this.loadEnvironment(region.id);
    } catch (error) { this.setData({ error: message(error) }); }
    finally { this._loading = false; finish(this); }
  },
  async loadEnvironment(id) {
    this.setData({ weather: null, air: null, alerts: [], alertNotice: '', sections: [] });
    const definitions = [
      { key: 'weather', title: '天气', path: 'weather/' },
      { key: 'air', title: '空气质量', path: 'air-quality/' },
      { key: 'alerts', title: '气象提示', path: 'weather-alerts/' },
    ];
    const settled = await Promise.all(definitions.map(async (definition) => {
      try { return { key: definition.key, data: (await app().api.request(definition.path, { data: { region: id } })).data }; }
      catch (error) { return { key: definition.key, title: definition.title, error: message(error) }; }
    }));
    const patch = { sections: settled.filter((item) => item.error) };
    settled.forEach((result) => {
      if (result.error) return;
      if (result.key === 'alerts') {
        patch.alerts = (Array.isArray(result.data) ? result.data : result.data.alerts || []).map((item) => Object.assign({}, item, { time_label: time(item.issued_at || item.published_at) }));
        patch.alertNotice = result.data.notice || '当前仅查询模拟气象提示，不提供真实气象预警。';
      } else {
        const data = result.data || {};
        patch[result.key] = Object.assign({}, data, {
          temp_label: value(data.temperature, '°'), humidity_label: value(data.humidity, '%'),
          pm10_label: value(data.pm10), pm25_label: value(data.pm25 !== undefined ? data.pm25 : data.pm2_5),
          updated_label: time(data.observed_at || data.updated_at),
        });
      }
    });
    this.setData(patch);
  },
  async changeRegion(event) {
    const index = Number(event.detail.value);
    const region = this.data.regions[index];
    if (!region || this._loading) return;
    this._loading = true;
    app().globalData.region = region;
    this.setData({ regionIndex: index, region, loading: true });
    try { await this.loadEnvironment(region.id); }
    finally { this._loading = false; finish(this); }
  },
  navigate(event) { wx.switchTab({ url: '/pages/' + event.currentTarget.dataset.page + '/index' }); },
  assessment() { wx.navigateTo({ url: '/pages/assessment/index' }); },
});
