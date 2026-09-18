const { app, finish } = require('../../lib/page');
const { list, message } = require('../../lib/format');
const { assessmentTask, resultView, metricView } = require('../../lib/assessment');
Page({
  data: { loading: true, error: '', jobId: '', job: null, result: null, imagePath: '', imageUnavailable: '', metrics: [], metricNotice: '', pollNotice: '' },
  onLoad(options) {
    this._destroyed = false;
    this._pollCount = 0;
    this._pollGeneration = 0;
    this.setData({ jobId: (options && options.jobId) || '' });
    this.poll();
  },
  onUnload() {
    this._destroyed = true;
    this.stopPolling();
  },
  onPullDownRefresh() { this.retry(); },
  stopPolling() {
    this._pollGeneration = (this._pollGeneration || 0) + 1;
    if (this._timer) clearTimeout(this._timer);
    this._timer = null;
  },
  async poll() {
    this.stopPolling();
    const generation = this._pollGeneration;
    if (this._destroyed) return;
    if (!this.data.jobId) { this.setData({ loading: false, error: '缺少任务编号，无法查看评估结果。' }); return; }
    try {
      const job = (await app().api.request('assessment-jobs/' + encodeURIComponent(this.data.jobId) + '/')).data;
      if (this._destroyed || generation !== this._pollGeneration) return;
      if (job.status === 'queued' || job.status === 'running') {
        this.setData({ loading: false, job: assessmentTask(job) });
        this._pollCount += 1;
        if (this._pollCount <= 10) this._timer = setTimeout(() => this.poll(), 3000);
        else this.setData({ pollNotice: '任务尚未结束。请确认服务端评估工作进程已启动，稍后点击刷新重试。' });
        return;
      }
      this.setData({ loading: false, job: assessmentTask(job) });
      if (job.status === 'succeeded') {
        this.setData({ result: resultView(job) });
        await this.loadImage(job);
        await this.loadMetrics(job);
      }
    } catch (error) {
      if (!this._destroyed && generation === this._pollGeneration) this.setData({ loading: false, error: message(error) });
    }
    finally { if (!this._destroyed) wx.stopPullDownRefresh && wx.stopPullDownRefresh(); }
  },
  async loadImage(job) {
    if (!job.asset_id) return;
    try {
      const localPath = await app().api.download('uploads/' + encodeURIComponent(job.asset_id) + '/content/?variant=thumbnail');
      if (this._destroyed) return;
      this.setData({ imagePath: localPath });
      this.prepareCanvas(localPath, job.detections);
    } catch (error) {
      if (!this._destroyed) this.setData({ imageUnavailable: '照片已过期或暂不可访问，评估结论仍可查看。' });
    }
  },
  prepareCanvas(localPath, detections) {
    if (!Array.isArray(detections) || !detections.length || !this.data.result || !this.data.result.boxes.length) return;
    wx.getImageInfo({ src: localPath,
      success: (info) => {
        if (this._destroyed) return;
        this.drawBoxes(localPath, detections, info.width, info.height);
      },
      fail: () => { /* 图片信息不可用时跳过检测框绘制，结论仍可查看 */ },
    });
  },
  drawBoxes(localPath, detections, imgWidth, imgHeight) {
    try {
      const query = this.createSelectorQuery ? this.createSelectorQuery() : wx.createSelectorQuery();
      query.select('#box-canvas').fields({ node: true, size: true }).exec((entries) => {
        const entry = entries && entries[0];
        if (!entry || !entry.node || !entry.width) return;
        const canvas = entry.node;
        const displayWidth = entry.width;
        const scale = displayWidth / imgWidth;
        const displayHeight = imgHeight * scale;
        const info = wx.getSystemInfoSync ? wx.getSystemInfoSync() : {};
        const dpr = info.pixelRatio || 2;
        canvas.width = Math.round(displayWidth * dpr);
        canvas.height = Math.round(displayHeight * dpr);
        const ctx = canvas.getContext('2d');
        ctx.scale(dpr, dpr);
        const image = canvas.createImage();
        image.onload = () => {
          ctx.drawImage(image, 0, 0, displayWidth, displayHeight);
          ctx.lineWidth = 2;
          ctx.font = '12px sans-serif';
          this.data.result.boxes.forEach((box) => {
            const x = box.x1 * scale, y = box.y1 * scale;
            const w = Math.max(1, (box.x2 - box.x1) * scale);
            const h = Math.max(1, (box.y2 - box.y1) * scale);
            ctx.strokeStyle = box.color;
            ctx.strokeRect(x, y, w, h);
            const text = box.label + ' ' + box.conf_label;
            const textWidth = ctx.measureText(text).width;
            ctx.fillStyle = box.color;
            const labelY = y > 18 ? y - 4 : y + 14;
            ctx.fillRect(x, labelY - 13, textWidth + 8, 17);
            ctx.fillStyle = '#ffffff';
            ctx.fillText(text, x + 4, labelY);
          });
        };
        image.src = localPath;
      });
    } catch (error) { /* canvas 不可用时静默：结论仍可查看 */ }
  },
  async loadMetrics(job) {
    if (!job.station_id) return;
    try {
      const response = await app().api.request('observations/', { data: { station: job.station_id, limit: 4 } });
      if (this._destroyed) return;
      const metrics = list(response).map(metricView).filter(Boolean).slice(0, 4);
      this.setData({ metrics });
    } catch (error) {
      if (!this._destroyed) this.setData({ metricNotice: '该河段近期指标暂不可用。' });
    }
  },
  retry() {
    if (this._destroyed) return;
    this._pollCount = 0;
    this.stopPolling();
    this.setData({ error: '', pollNotice: '' });
    this.poll();
  },
});
