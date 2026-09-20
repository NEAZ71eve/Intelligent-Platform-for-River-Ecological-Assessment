const { time, message } = require('./format');
const { loadAll, loadRegions, selectRegion } = require('./region');

const WATER_METRICS = ['water_temperature', 'ph', 'turbidity', 'dissolved_oxygen'];
const KINDS = [{ code: 'water', name: '河湖水环境' }, { code: 'air', name: '空气指标' }, { code: 'weather', name: '温湿度' }];
const RANGES = [{ hours: 6, name: '6 小时窗口' }, { hours: 24, name: '24 小时窗口' }, { hours: 48, name: '48 小时窗口' }, { hours: 168, name: '7 天窗口' }];
const SOURCE_NAMES = { simulation: '模拟数据', dataset: '历史数据', api: '接口数据', manual: '管理员整理' };
function finite(value) { return typeof value === 'number' && Number.isFinite(value); }
function number(value) { return finite(value) ? String(Number(value.toFixed(3))) : '—'; }
function count(value) { return Number.isSafeInteger(value) && value >= 0 ? value : 0; }
function validPoint(point) { return Boolean(point && point.quality_status === 'valid' && finite(point.value) && Number.isFinite(Date.parse(point.at))); }
function pointView(point) {
  const valid = validPoint(point);
  return Object.assign({}, point, {
    value: valid ? point.value : null,
    value_label: valid ? number(point.value) : '—',
    time_label: time(point.at),
    range_label: valid && finite(point.min) && finite(point.max) ? `${number(point.min)}–${number(point.max)}` : '—',
    quality_label: point.quality_status === 'suspect' ? '存疑，未连线' : valid ? '有效' : '缺测，未连线',
    valid_count: count(point.valid_count), missing_count: count(point.missing_count), suspect_count: count(point.suspect_count),
  });
}
function seriesView(payload) {
  const input = payload || {};
  const window = input.window || {};
  const source = input.source || null;
  return {
    status: input.status || 'unavailable',
    source, source_type: input.source_type || '',
    source_label: SOURCE_NAMES[input.source_type] || '来源待确认',
    source_name: source && source.name || '该范围暂无来源记录',
    simulation_run_id: input.simulation_run_id || '',
    start: window.start || '', end: window.end || '',
    window_label: `${time(window.start)} 至 ${time(window.end)}`,
    bucket_label: finite(input.bucket_seconds) ? `${number(input.bucket_seconds / 60)} 分钟 / 桶` : '时间桶未提供',
    notice: input.notice || '',
    series: (Array.isArray(input.series) ? input.series : []).map((entry) => {
      const latest = entry.latest || {};
      const summary = entry.summary || {};
      // The endpoint limits buckets to 240. Reject overflow instead of silently dropping gaps.
      const points = Array.isArray(entry.points) && entry.points.length <= 240 ? entry.points.map(pointView) : [];
      return {
        metric: entry.metric || {}, metric_name: entry.metric && entry.metric.name || '未命名指标', points,
        latest_label: latest.quality_status === 'valid' ? number(latest.value) : '—',
        latest_time: latest.observed_at ? time(latest.observed_at) : '暂无观测',
        latest_quality: latest.quality_status === 'suspect' ? '存疑' : latest.quality_status === 'missing' ? '缺测' : latest.quality_status === 'valid' ? '有效' : '暂无观测',
        minimum_label: number(summary.min), maximum_label: number(summary.max), mean_label: number(summary.mean),
        valid_count: count(summary.valid_count), missing_count: count(summary.missing_count), suspect_count: count(summary.suspect_count),
        has_values: points.some(validPoint),
      };
    }),
  };
}

/** Every null/suspect bucket terminates a segment; zero is a real numeric observation. */
function chartGeometry(points, width, height, window) {
  const source = Array.isArray(points) && points.length <= 240 ? points : [];
  const usable = source.filter(validPoint);
  if (!usable.length || !finite(width) || !finite(height) || width < 100 || height < 80) return null;
  const times = source.map((point) => Date.parse(point.at)).filter(Number.isFinite);
  let start = Date.parse(window && window.start), end = Date.parse(window && window.end);
  if (!Number.isFinite(start)) start = Math.min(...times);
  if (!Number.isFinite(end)) end = Math.max(...times);
  if (end <= start) end = start + 3600000;
  const values = usable.map((point) => point.value);
  let minimum = Math.min(...values), maximum = Math.max(...values);
  const padding = maximum === minimum ? Math.max(Math.abs(maximum) * 0.05, 0.1) : (maximum - minimum) * 0.1;
  minimum -= padding; maximum += padding;
  const plot = { left: 48, right: width - 12, top: 16, bottom: height - 30 };
  const segments = [];
  let segment = [];
  for (const point of source) {
    const at = Date.parse(point.at);
    if (!validPoint(point) || at < start || at > end) {
      if (segment.length) segments.push(segment);
      segment = [];
      continue;
    }
    segment.push({ x: plot.left + (at - start) / (end - start) * (plot.right - plot.left), y: plot.bottom - (point.value - minimum) / (maximum - minimum) * (plot.bottom - plot.top) });
  }
  if (segment.length) segments.push(segment);
  return { segments, minimum, maximum, start, end, plot };
}
function selectedIndex(items, id) { const index = items.findIndex((item) => item.id === id); return index < 0 ? 0 : index; }
function selected(items, index) { return items[index] || null; }
function runLabel(run) { return `${time(run.created_at || run.end)} · ${(run.id || '').slice(0, 8)}`; }
function rangeQuery(run, hours) {
  const end = run ? Date.parse(run.end) : Date.now();
  if (!Number.isFinite(end)) throw new Error('批次时间无效，请重新选择。');
  if (!finite(hours) || hours <= 0 || hours > 744) throw new Error('时间范围无效，请重新选择。');
  const runStart = run ? Date.parse(run.start) : NaN;
  const start = Math.max(end - hours * 3600000, Number.isFinite(runStart) ? runStart : -Infinity);
  if (start >= end) throw new Error('批次时间无效，请重新选择。');
  // Simulation windows are [start, end): the final generated sample is before run.end.
  return { start: new Date(start).toISOString(), end: new Date(end).toISOString() };
}

/** Shared lifecycle for the two public measurement screens. No login or GPS is requested. */
function createSeriesPage(mode) {
  const waterMode = mode === 'water';
  return {
    data: {
      waterMode, loading: true, error: '', regions: [], regionIndex: 0, region: null,
      kinds: KINDS, kindIndex: 0, waterBodies: [], waterIndex: 0,
      stations: [], stationIndex: 0, sources: [], sourceIndex: 0,
      scenarios: [], scenarioIndex: 0, runs: [], runIndex: 0,
      ranges: RANGES, rangeIndex: 2, selectionNotice: '', view: null, metricIndex: 0, activeMetric: null, selectedRun: null,
    },
    onLoad(options) { this._options = options || {}; this._alive = true; this._hidden = false; return this.load(); },
    onShow() {
      if (!this._alive) return;
      const region = getApp().globalData.region;
      if (this._hidden || (this._loaded && region && this.data.region && region.id !== this.data.region.id)) {
        this._hidden = false;
        return this.load();
      }
    },
    onHide() { this._hidden = true; this._generation = (this._generation || 0) + 1; },
    onUnload() { this._alive = false; this._generation = (this._generation || 0) + 1; },
    onPullDownRefresh() { return this.load(); },
    _interactive() { return this._alive !== false && !this._hidden; },
    _current(generation) { return this._interactive() && generation === this._generation; },
    async _perform(task) {
      // Native taps, picker events and refresh callbacks may arrive after hide/unload.
      if (!this._interactive()) return;
      const generation = this._generation = (this._generation || 0) + 1;
      this.setData({ loading: true, error: '', view: null, activeMetric: null, selectionNotice: '' });
      try { await task.call(this, generation); }
      catch (error) { if (this._current(generation)) this.setData({ error: message(error), view: null }); }
      finally {
        if (this._current(generation)) { this.setData({ loading: false }); wx.stopPullDownRefresh(); }
      }
    },
    load() {
      return this._perform(async function (generation) {
        const application = getApp();
        const result = await Promise.all([loadRegions(application), loadAll(application.api, 'data-sources/')]);
        if (!this._current(generation)) return;
        const catalogue = result[0], sources = result[1];
        let regionIndex = catalogue.regionIndex;
        if (!this._loaded && this._options && this._options.region) {
          const routeIndex = catalogue.regions.findIndex((item) => item.id === this._options.region || item.slug === this._options.region);
          if (routeIndex >= 0) regionIndex = routeIndex;
        }
        const region = catalogue.regions[regionIndex] || null;
        const previousSource = selected(this.data.sources, this.data.sourceIndex);
        let sourceIndex = previousSource ? sources.findIndex((item) => item.id === previousSource.id) : -1;
        if (sourceIndex < 0) sourceIndex = sources.findIndex((item) => item.kind === 'simulation' && item.code === 'demo-normal');
        if (sourceIndex < 0) sourceIndex = sources.findIndex((item) => item.kind === 'simulation');
        if (sourceIndex < 0) sourceIndex = 0;
        this.setData({ regions: catalogue.regions, regionIndex, region, sources: sources.map((item) => Object.assign({}, item, { label: `${item.name} · ${SOURCE_NAMES[item.kind] || '未知来源'}` })), sourceIndex });
        selectRegion(application, region);
        await this._catalogue(generation);
        if (this._current(generation)) this._loaded = true;
      });
    },
    async _catalogue(generation) {
      const oldWater = selected(this.data.waterBodies, this.data.waterIndex);
      if (!this.data.region) { this.setData({ waterBodies: [], waterIndex: 0 }); this._clearCatalogue('暂无示范区域，请管理员初始化数据。'); return; }
      if (waterMode) {
        const waterBodies = await loadAll(getApp().api, 'water-bodies/', { region: this.data.region.id });
        if (!this._current(generation)) return;
        const preferred = !this._loaded && this._options && this._options.waterBodyId || oldWater && oldWater.id;
        this.setData({ waterBodies, waterIndex: selectedIndex(waterBodies, preferred) });
      }
      if (!waterMode && !this._loaded && this._options && this._options.stationId) {
        const catalogue = await loadAll(getApp().api, 'stations/', { region: this.data.region.id });
        if (!this._current(generation)) return;
        const preferred = catalogue.find((item) => item.id === this._options.stationId);
        const kindIndex = preferred ? this.data.kinds.findIndex((item) => item.code === preferred.kind) : -1;
        if (kindIndex >= 0) this.setData({ kindIndex });
      }
      await this._stations(generation);
    },
    _clearCatalogue(notice) {
      this._allRuns = [];
      this.setData({ stations: [], stationIndex: 0, runs: [], runIndex: 0, scenarios: [], scenarioIndex: 0, selectedRun: null, selectionNotice: notice });
    },
    async _stations(generation) {
      const oldStation = selected(this.data.stations, this.data.stationIndex);
      const region = this.data.region;
      if (!region) return;
      const query = { region: region.id, kind: waterMode ? 'water' : this.data.kinds[this.data.kindIndex].code };
      if (waterMode) {
        const water = selected(this.data.waterBodies, this.data.waterIndex);
        if (!water) { this._clearCatalogue('该区域暂无已公开水体。'); return; }
        query.water_body = water.id;
      }
      const stations = await loadAll(getApp().api, 'stations/', query);
      if (!this._current(generation)) return;
      const preferred = !this._loaded && this._options && this._options.stationId || oldStation && oldStation.id;
      this.setData({ stations, stationIndex: selectedIndex(stations, preferred) });
      await this._runs(generation);
    },
    async _runs(generation) {
      const station = selected(this.data.stations, this.data.stationIndex);
      const source = selected(this.data.sources, this.data.sourceIndex);
      const oldScenario = selected(this.data.scenarios, this.data.scenarioIndex);
      const oldRun = selected(this.data.runs, this.data.runIndex);
      this._allRuns = [];
      this.setData({ runs: [], runIndex: 0, scenarios: [], scenarioIndex: 0, selectedRun: null });
      if (!station) { this.setData({ selectionNotice: '当前选择暂无公开监测站。' }); return; }
      if (!source) { this.setData({ selectionNotice: '暂无已启用数据源。' }); return; }
      if (source.kind === 'simulation') {
        const runs = await loadAll(getApp().api, 'simulation-runs/', { region: this.data.region.id, station: station.id, source: source.id });
        if (!this._current(generation)) return;
        this._allRuns = runs.map((item) => Object.assign({}, item, { label: runLabel(item) }));
        const scenarios = [];
        this._allRuns.forEach((run) => { if (run.scenario && !scenarios.some((item) => item.code === run.scenario.code)) scenarios.push(run.scenario); });
        let scenarioIndex = scenarios.findIndex((item) => item.code === (oldScenario && oldScenario.code || 'normal'));
        if (scenarioIndex < 0) scenarioIndex = 0;
        const scenario = scenarios[scenarioIndex];
        const available = scenario ? this._allRuns.filter((item) => item.scenario.code === scenario.code) : [];
        this.setData({ scenarios, scenarioIndex, runs: available, runIndex: selectedIndex(available, oldRun && oldRun.id) });
        if (!available.length) { this.setData({ selectionNotice: '该监测站与来源暂无成功模拟批次，请管理员生成后刷新。' }); return; }
      }
      await this._series(generation);
    },
    async _series(generation) {
      const station = selected(this.data.stations, this.data.stationIndex);
      const source = selected(this.data.sources, this.data.sourceIndex);
      if (!station || !source || !this.data.region) return;
      const run = source.kind === 'simulation' ? selected(this.data.runs, this.data.runIndex) : null;
      if (source.kind === 'simulation' && !run) { this.setData({ selectionNotice: '暂无可选模拟批次。' }); return; }
      const window = rangeQuery(run, this.data.ranges[this.data.rangeIndex].hours);
      // Demo samples are hourly. Hour-sized buckets keep consecutive samples together;
      // any genuinely missing/suspect bucket still breaks the line.
      const maxPoints = Math.min(240, Math.max(1, Math.ceil((Date.parse(window.end) - Date.parse(window.start)) / 3600000)));
      const query = Object.assign({ region: this.data.region.id, station: station.id, source_type: source.kind, source: source.id, max_points: maxPoints }, window);
      if (run) query.simulation_run = run.id;
      if (waterMode) query.metrics = WATER_METRICS.join(',');
      const response = await getApp().api.request('observation-series/', { data: query });
      if (!this._current(generation)) return;
      const view = seriesView(response.data);
      const previousMetric = this._metricCode;
      let metricIndex = view.series.findIndex((entry) => entry.metric.code === previousMetric);
      if (metricIndex < 0) metricIndex = 0;
      const activeMetric = view.series[metricIndex] || null;
      this._metricCode = activeMetric && activeMetric.metric.code;
      this.setData({ view, metricIndex, activeMetric, selectedRun: run ? Object.assign({}, run, { created_label: time(run.created_at), window_label: `${time(run.start)} 至 ${time(run.end)}` }) : null });
    },
    changeMetric(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value);
      const activeMetric = this.data.view && this.data.view.series[index];
      if (!activeMetric) return;
      this._metricCode = activeMetric.metric.code;
      this.setData({ metricIndex: index, activeMetric });
    },
    changeRegion(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value), region = this.data.regions[index];
      if (!region) return;
      this.setData({ regionIndex: index, region }); selectRegion(getApp(), region);
      return this._perform(function (generation) { return this._catalogue(generation); });
    },
    changeKind(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value); if (!this.data.kinds[index]) return;
      this.setData({ kindIndex: index }); return this._perform(function (generation) { return this._stations(generation); });
    },
    changeWater(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value); if (!this.data.waterBodies[index]) return;
      this.setData({ waterIndex: index }); return this._perform(function (generation) { return this._stations(generation); });
    },
    changeStation(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value); if (!this.data.stations[index]) return;
      this.setData({ stationIndex: index }); return this._perform(function (generation) { return this._runs(generation); });
    },
    changeSource(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value); if (!this.data.sources[index]) return;
      this.setData({ sourceIndex: index }); return this._perform(function (generation) { return this._runs(generation); });
    },
    changeScenario(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value), scenario = this.data.scenarios[index];
      if (!scenario) return;
      const runs = (this._allRuns || []).filter((item) => item.scenario.code === scenario.code);
      this.setData({ scenarioIndex: index, runs, runIndex: 0 });
      return this._perform(function (generation) { return this._series(generation); });
    },
    changeRun(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value); if (!this.data.runs[index]) return;
      this.setData({ runIndex: index }); return this._perform(function (generation) { return this._series(generation); });
    },
    changeRange(event) {
      if (!this._interactive()) return;
      const index = Number(event.detail.value); if (!this.data.ranges[index]) return;
      this.setData({ rangeIndex: index }); return this._perform(function (generation) { return this._series(generation); });
    },
  };
}
module.exports = { WATER_METRICS, KINDS, RANGES, number, validPoint, seriesView, chartGeometry, rangeQuery, createSeriesPage };
