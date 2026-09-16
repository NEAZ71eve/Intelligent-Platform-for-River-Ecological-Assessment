const { app, requireLogin, toast, finish } = require('../../lib/page');
const { list, task, message } = require('../../lib/format');
Page({
  data: { loading: false, error: '', busy: false, imagePath: '', task: null, jobs: [], loggedIn: false, consent: false },
  onShow() {
    this._visible = true;
    const current = app().session.get();
    const userId = current && current.user && current.user.id;
    if (this._userId !== userId) this.setData({ jobs: [], task: null, imagePath: '', consent: false });
    this._userId = userId;
    this.load();
  },
  onHide() { this._visible = false; this.stopPolling(); },
  onUnload() { this._visible = false; this.stopPolling(); },
  onPullDownRefresh() { this.load(); },
  stopPolling() { if (this._timer) clearTimeout(this._timer); this._timer = null; },
  async load() {
    const loggedIn = Boolean(app().session.token());
    this.setData({ loggedIn, error: '' });
    if (!loggedIn) { this.setData({ jobs: [], task: null, imagePath: '' }); finish(this); return; }
    this.setData({ loading: true });
    try {
      const jobs = list(await app().api.request('recognition-jobs/', { data: { page_size: 5 } })).map(task);
      const current = this.data.task && jobs.find((item) => item.id === this.data.task.id);
      this.setData({ jobs, task: current || this.data.task });
    } catch (error) { this.authError(error); }
    finally { finish(this); }
  },
  consentChange(event) { this.setData({ consent: event.detail.value.includes('agree') }); },
  choose() {
    if (this.data.busy || !requireLogin()) return;
    wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album', 'camera'], sizeType: ['compressed'], success: (result) => {
      const file = result.tempFiles[0];
      if (!file) return;
      if (file.size > app().config.maxUploadBytes) { toast(new Error('图片不能超过 5MB，请压缩后重试')); return; }
      this.stopPolling();
      this.setData({ imagePath: file.tempFilePath, task: null, error: '' });
    }, fail: (error) => { if (!/cancel/i.test(error.errMsg || '')) toast(new Error('未能选择图片，请检查相机与相册权限')); } });
  },
  async submit() {
    if (this.data.busy || (this.data.task && ['queued', 'running'].includes(this.data.task.status)) || !this.data.imagePath || !this.data.consent || !requireLogin()) return;
    this.setData({ busy: true, error: '' });
    try {
      const asset = await app().api.upload(this.data.imagePath, 'recognition');
      const result = (await app().api.request('recognition-jobs/', { method: 'POST', data: { asset_id: asset.id } })).data;
      this.setData({ task: task(result) });
      this._pollCount = 0;
      this.poll(result.id);
    } catch (error) { this.authError(error); }
    finally { this.setData({ busy: false }); }
  },
  async poll(id) {
    this.stopPolling();
    if (!this._visible) return;
    try {
      const result = (await app().api.request('recognition-jobs/' + encodeURIComponent(id) + '/')).data;
      if (!this._visible || !this.data.task || this.data.task.id !== id) return;
      this.setData({ task: task(result) });
      if (['queued', 'running'].includes(result.status)) {
        this._pollCount = (this._pollCount || 0) + 1;
        if (this._pollCount < 10) this._timer = setTimeout(() => this.poll(id), 3000);
        else this.setData({ error: '任务尚未结束，可手动刷新。请确认服务端任务工作进程已经启动。' });
      } else await this.load();
    } catch (error) { this.authError(error); }
  },
  authError(error) {
    const loggedIn = Boolean(app().session.token());
    this.setData({ error: message(error), loggedIn });
    if (!loggedIn) { this.stopPolling(); this.setData({ jobs: [], task: null, imagePath: '', consent: false }); }
  },
  refreshTask() { if (this.data.task) { this._pollCount = 0; this.poll(this.data.task.id); } else this.load(); },
  login() { wx.switchTab({ url: '/pages/profile/index' }); },
  privacy() { wx.navigateTo({ url: '/pages/legal/index?kind=privacy' }); },
});
