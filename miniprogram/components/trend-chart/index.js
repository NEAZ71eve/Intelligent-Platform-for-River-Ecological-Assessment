const { chartGeometry, number } = require('../../lib/series');

Component({
  properties: { entry: Object, start: String, end: String },
  data: { showTable: false, chartError: '', canvasHeight: 210 },
  observers: {
    'entry, start, end': function () { if (this._attached && !this._hidden) this.render(); },
  },
  lifetimes: {
    attached() { this._attached = true; this._hidden = false; },
    ready() { this.render(); },
    detached() { this._attached = false; this._generation = (this._generation || 0) + 1; },
  },
  pageLifetimes: {
    hide() { this._hidden = true; this._generation = (this._generation || 0) + 1; },
    show() { this._hidden = false; if (this._attached) this.render(); },
    resize() { if (this._attached && !this._hidden) this.render(); },
  },
  methods: {
    toggleTable() { this.setData({ showTable: !this.data.showTable }); },
    canvasFailure() {
      this._generation = (this._generation || 0) + 1;
      this.setData({ chartError: '图表暂不可用，已展开数据表。', showTable: true });
    },
    render() {
      const generation = this._generation = (this._generation || 0) + 1;
      if (!this._attached || this._hidden) return;
      this.setData({ chartError: '' });
      const current = () => this._attached && !this._hidden && generation === this._generation;
      try {
        this.createSelectorQuery().select('.trend-canvas').boundingClientRect((bounds) => {
          if (!current()) return;
          try {
            if (!bounds || !bounds.width || !bounds.height) throw new Error('Canvas size unavailable');
            const context = wx.createCanvasContext('trend-canvas', this);
            const geometry = chartGeometry(this.data.entry && this.data.entry.points, bounds.width, bounds.height, { start: this.data.start, end: this.data.end });
            context.clearRect(0, 0, bounds.width, bounds.height);
            context.setFontSize(10);
            context.setFillStyle('#718364');
            if (!geometry) {
              context.fillText('该时间范围没有可连线的有效数据', 12, 36);
              context.draw();
              return;
            }
            const { plot } = geometry;
            context.setStrokeStyle('#dde5d4');
            context.setLineWidth(1);
            context.beginPath(); context.moveTo(plot.left, plot.top); context.lineTo(plot.left, plot.bottom); context.lineTo(plot.right, plot.bottom); context.stroke();
            context.fillText(number(geometry.maximum), 0, plot.top + 8);
            context.fillText(number(geometry.minimum), 0, plot.bottom);
            context.fillText('窗口起点', plot.left, bounds.height - 8);
            context.fillText('窗口终点', Math.max(plot.left + 64, plot.right - 42), bounds.height - 8);
            context.setStrokeStyle('#39734d'); context.setFillStyle('#39734d'); context.setLineWidth(2);
            geometry.segments.forEach((segment) => {
              context.beginPath();
              segment.forEach((point, index) => { if (index === 0) context.moveTo(point.x, point.y); else context.lineTo(point.x, point.y); });
              context.stroke();
              segment.forEach((point) => { context.beginPath(); context.arc(point.x, point.y, 2, 0, Math.PI * 2); context.fill(); });
            });
            context.draw();
          } catch (_) { if (current()) this.canvasFailure(); }
        }).exec();
      } catch (_) { if (current()) this.canvasFailure(); }
    },
  },
});
