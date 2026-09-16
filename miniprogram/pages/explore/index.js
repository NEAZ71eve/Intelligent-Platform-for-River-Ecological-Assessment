const { app, detail, finish } = require('../../lib/page');
const { list, message } = require('../../lib/format');
Page({
  data: { loading: true, error: '', places: [], filtered: [], region: null, activeType: '', types: [{ value: '', label: '全部地点' }, { value: 'water', label: '河湖' }, { value: 'park', label: '公园' }, { value: 'campus', label: '校园' }] },
  onShow() { this.load(); },
  onPullDownRefresh() { this.load(); },
  async load() {
    if (this._loading) return;
    this._loading = true;
    this.setData({ loading: true, error: '' });
    try {
      const region = app().globalData.region;
      const result = await app().api.request('places/', { data: Object.assign({ page_size: 50 }, region ? { region: region.id } : {}) });
      const places = list(result).map((item, index) => Object.assign({}, item, { order: String(index + 1).padStart(2, '0') }));
      this.setData({ places, region });
      this.filter();
    } catch (error) { this.setData({ error: message(error) }); }
    finally { this._loading = false; finish(this); }
  },
  chooseType(event) { this.setData({ activeType: event.currentTarget.dataset.type }); this.filter(); },
  filter() {
    const key = this.data.activeType;
    const matches = { water: ['river', 'lake', 'water', 'waterbody'], park: ['park', 'scenic'], campus: ['campus', 'plant', 'recycling', 'waste', 'trail'] };
    this.setData({ filtered: this.data.places.filter((item) => !key || (matches[key] || []).includes(item.kind || item.type || item.category)) });
  },
  open(event) { detail('place', event.currentTarget.dataset.id); },
});
