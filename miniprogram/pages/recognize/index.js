const { app, requireLogin, toast, finish, detail } = require('../../lib/page');
const { list, task, message } = require('../../lib/format');
const { capability } = require('../../lib/recognition');
Page({
  data: { loading: false, error: '', busy: false, imagePath: '', imageOrigin: '', imageUnavailable: '', task: null, jobs: [], loggedIn: false, consent: false, capability: capability(null), capabilityKnown: false, capabilityError: '' },
  onShow() {
    this._destroyed = false;
    this._visible = true;
    this._pollCount = 0;
    const current = app().session.get();
    const userId = current && current.user && current.user.id;
    if (this._userId !== userId) this.clearPrivate();
    this._userId = userId;
    return this.load();
  },
  onHide() { this._visible = false; this.stopPolling(); },
  onUnload() {
    this._visible = false;
    this._destroyed = true;
    this._loadGeneration = (this._loadGeneration || 0) + 1;
    this._selectionVersion = (this._selectionVersion || 0) + 1;
    this.stopPolling();
  },
  onPullDownRefresh() { this.load(); },
  stopPolling() {
    this._pollGeneration = (this._pollGeneration || 0) + 1;
    if (this._timer) clearTimeout(this._timer);
    this._timer = null;
  },
  clearPrivate() {
    this.stopPolling();
    this._selectionVersion = (this._selectionVersion || 0) + 1;
    this.setData({ jobs: [], task: null, imagePath: '', imageOrigin: '', imageUnavailable: '', consent: false, busy: false });
  },
  async load() {
    if (this._destroyed) return;
    const generation = this._loadGeneration = (this._loadGeneration || 0) + 1;
    const sentToken = app().session.token();
    const loggedIn = Boolean(app().session.token());
    this.setData({ loggedIn, error: '', loading: true });
    if (!loggedIn) this.clearPrivate();
    try {
      const results = await Promise.all([
        app().api.request('health/').then((response) => ({ response })).catch((error) => ({ error })),
        loggedIn ? app().api.request('recognition-jobs/', { data: { page_size: 5 } }).then((response) => ({ response })).catch((error) => ({ error })) : Promise.resolve({ response: { data: [] } }),
      ]);
      if (this._destroyed || generation !== this._loadGeneration) return;
      if (results[0].error) this.setData({ capabilityKnown: false, capabilityError: '暂时无法确认模型状态：' + message(results[0].error) });
      else {
        const health = results[0].response.data;
        app().globalData.health = health;
        this.setData({ capability: capability(health), capabilityKnown: true, capabilityError: '' });
      }
      if (results[1].error) throw results[1].error;
      if (loggedIn && app().session.token() !== sentToken) {
        this.clearPrivate();
        this.setData({ loggedIn: Boolean(app().session.token()) });
        return;
      }
      const jobs = list(results[1].response).map(task);
      const current = this.data.task && jobs.find((item) => item.id === this.data.task.id);
      this.setData({ jobs, task: current || this.data.task });
      if (this.data.task && !current && !this.data.busy) {
        const selectedId = this.data.task.id;
        try {
          const selected = (await app().api.request('recognition-jobs/' + encodeURIComponent(selectedId) + '/')).data;
          if (this._destroyed || generation !== this._loadGeneration || app().session.token() !== sentToken) return;
          if (this.data.task && this.data.task.id === selectedId) this.setData({ task: task(selected) });
        } catch (error) {
          if (this._destroyed || generation !== this._loadGeneration) return;
          if (error.status === 404 && this.data.task && this.data.task.id === selectedId) {
            this.stopPolling();
            this._selectionVersion = (this._selectionVersion || 0) + 1;
            this.setData({ task: null, imagePath: '', imageOrigin: '', imageUnavailable: '', error: '这条识别记录已删除或已到保留期限。' });
          } else throw error;
        }
      }
      const pendingJob = app().globalData.recognitionJobId;
      if (pendingJob && loggedIn) {
        app().globalData.recognitionJobId = null;
        await this.selectJob(pendingJob);
      } else if (this._visible && this.data.task && ['queued', 'running'].includes(this.data.task.status)) {
        this.poll(this.data.task.id);
      }
    } catch (error) { if (!this._destroyed && generation === this._loadGeneration) this.authError(error); }
    finally { if (!this._destroyed && generation === this._loadGeneration) finish(this); }
  },
  consentChange(event) { this.setData({ consent: event.detail.value.includes('agree') }); },
  choose() {
    if (this._destroyed || this.data.busy || !requireLogin()) return;
    wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album', 'camera'], sizeType: ['compressed'], success: (result) => {
      if (this._destroyed) return;
      const file = result.tempFiles[0];
      if (!file) return;
      if (file.size > app().config.maxUploadBytes) { toast(new Error('图片不能超过 5MB，请压缩后重试')); return; }
      this.stopPolling();
      this._selectionVersion = (this._selectionVersion || 0) + 1;
      this.setData({ imagePath: file.tempFilePath, imageOrigin: 'selected', imageUnavailable: '', task: null, error: '' });
    }, fail: (error) => { if (!this._destroyed && !/cancel/i.test(error.errMsg || '')) toast(new Error('未能选择图片，请检查相机与相册权限')); } });
  },
  async submit() {
    if (this._destroyed || this.data.busy || this.data.imageOrigin === 'history' || (this.data.task && ['queued', 'running'].includes(this.data.task.status)) || !this.data.imagePath || !this.data.consent || !requireLogin()) return;
    const sentToken = app().session.token();
    this.setData({ busy: true, error: '' });
    try {
      const asset = await app().api.upload(this.data.imagePath, 'recognition');
      if (this._destroyed) return;
      if (app().session.token() !== sentToken) { if (!app().session.token()) this.authError(new Error('登录已失效，请重新登录')); return; }
      const result = (await app().api.request('recognition-jobs/', { method: 'POST', data: { asset_id: asset.id } })).data;
      if (this._destroyed) return;
      if (app().session.token() !== sentToken) { if (!app().session.token()) this.authError(new Error('登录已失效，请重新登录')); return; }
      this.setData({ task: task(result) });
      this._pollCount = 0;
      this.poll(result.id);
    } catch (error) { if (!this._destroyed && (!app().session.token() || app().session.token() === sentToken)) this.authError(error); }
    finally { if (!this._destroyed && (!app().session.token() || app().session.token() === sentToken)) this.setData({ busy: false }); }
  },
  async poll(id) {
    this.stopPolling();
    if (this._destroyed || !this._visible) return;
    const generation = this._pollGeneration;
    const sentToken = app().session.token();
    try {
      const result = (await app().api.request('recognition-jobs/' + encodeURIComponent(id) + '/')).data;
      if (this._destroyed || generation !== this._pollGeneration || app().session.token() !== sentToken || !this._visible || !this.data.task || this.data.task.id !== id) return;
      this.setData({ task: task(result) });
      if (['queued', 'running'].includes(result.status)) {
        this._pollCount = (this._pollCount || 0) + 1;
        if (this._pollCount < 10) this._timer = setTimeout(() => this.poll(id), 3000);
        else this.setData({ error: '任务尚未结束，可手动刷新。请确认服务端任务工作进程已经启动。' });
      } else await this.load();
    } catch (error) {
      if (!this._destroyed && generation === this._pollGeneration && this._visible && (!app().session.token() || app().session.token() === sentToken)) {
        if (error.status === 404) this.setData({ task: null, imagePath: '', imageOrigin: '', imageUnavailable: '' });
        this.authError(error);
      }
    }
  },
  authError(error) {
    if (this._destroyed) return;
    const loggedIn = Boolean(app().session.token());
    this.setData({ error: message(error), loggedIn });
    if (!loggedIn) this.clearPrivate();
  },
  openJob(event) { this.selectJob(event.currentTarget.dataset.id); },
  async selectJob(id) {
    if (this._destroyed || this.data.busy || !requireLogin()) return;
    this.stopPolling();
    const version = this._selectionVersion = (this._selectionVersion || 0) + 1;
    const sentToken = app().session.token();
    this.setData({ busy: true, task: null, imagePath: '', imageOrigin: 'history', imageUnavailable: '', error: '' });
    try {
      const job = (await app().api.request('recognition-jobs/' + encodeURIComponent(id) + '/')).data;
      if (this._destroyed || version !== this._selectionVersion || app().session.token() !== sentToken) return;
      this.setData({ task: task(job) });
      if (job.asset_id) {
        try {
          const localPath = await app().api.download('uploads/' + encodeURIComponent(job.asset_id) + '/content/?variant=thumbnail');
          if (!this._destroyed && version === this._selectionVersion && app().session.token() === sentToken) this.setData({ imagePath: localPath });
        } catch (error) {
          if (!app().session.token()) throw error;
          if (!this._destroyed && version === this._selectionVersion) this.setData({ imageUnavailable: '历史图片已过期、删除或暂不可访问，识别记录仍可查看。' });
        }
      }
      if (!this._destroyed && version === this._selectionVersion && ['queued', 'running'].includes(job.status)) { this._pollCount = 0; this.poll(job.id); }
    } catch (error) { if (!this._destroyed && version === this._selectionVersion) this.authError(error); }
    finally { if (!this._destroyed && version === this._selectionVersion) this.setData({ busy: false }); }
  },
  openContent(event) { if (event.detail.id) detail('content', event.detail.id); },
  refreshTask() { if (this.data.task) { this._pollCount = 0; this.poll(this.data.task.id); } else this.load(); },
  login() { wx.switchTab({ url: '/pages/profile/index' }); },
  privacy() { wx.navigateTo({ url: '/pages/legal/index?kind=privacy' }); },
});
