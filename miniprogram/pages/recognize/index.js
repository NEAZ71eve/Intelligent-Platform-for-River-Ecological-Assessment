const { app, requireLogin, toast, finish } = require('../../lib/page');
const { list, message } = require('../../lib/format');
const { assessmentTask } = require('../../lib/assessment');
Page({
  data: { loading: false, error: '', busy: false, imagePath: '', location: null, locationError: '', jobs: [], loggedIn: false, consent: false },
  onShow() {
    this._destroyed = false;
    const current = app().session.get();
    const userId = current && current.user && current.user.id;
    if (this._userId !== userId) this.clearPrivate();
    this._userId = userId;
    return this.load();
  },
  onUnload() { this._destroyed = true; },
  onPullDownRefresh() { this.load(); },
  clearPrivate() {
    this.setData({ jobs: [], imagePath: '', consent: false, busy: false, location: null, locationError: '' });
  },
  async load() {
    if (this._destroyed) return;
    const loggedIn = Boolean(app().session.token());
    this.setData({ loggedIn, error: '', loading: true });
    if (!loggedIn) { this.clearPrivate(); finish(this); return; }
    try {
      const response = await app().api.request('assessment-jobs/', { data: { page_size: 5 } });
      if (this._destroyed) return;
      this.setData({ jobs: list(response).map(assessmentTask) });
    } catch (error) { if (!this._destroyed) this.authError(error); }
    finally { if (!this._destroyed) finish(this); }
  },
  consentChange(event) { this.setData({ consent: event.detail.value.includes('agree') }); },
  choose() {
    if (this._destroyed || this.data.busy || !requireLogin()) return;
    wx.chooseMedia({ count: 1, mediaType: ['image'], sourceType: ['album', 'camera'], sizeType: ['compressed'], success: (result) => {
      if (this._destroyed) return;
      const file = result.tempFiles[0];
      if (!file) return;
      if (file.size > app().config.maxUploadBytes) { toast(new Error('图片不能超过 5MB，请压缩后重试')); return; }
      this.setData({ imagePath: file.tempFilePath, error: '' });
    }, fail: (error) => { if (!this._destroyed && !/cancel/i.test(error.errMsg || '')) toast(new Error('未能选择图片，请检查相机与相册权限')); } });
  },
  locate() {
    if (this._destroyed || this.data.busy) return;
    wx.getLocation({ type: 'gcj02', isHighAccuracy: true,
      success: (result) => {
        if (this._destroyed) return;
        this.setData({ location: { latitude: result.latitude, longitude: result.longitude }, locationError: '' });
      },
      fail: () => {
        if (this._destroyed) return;
        this.setData({ location: null, locationError: '未能获取定位。请检查小程序定位权限后重试；未定位无法提交巡查。' });
      },
    });
  },
  async submit() {
    if (this._destroyed || this.data.busy || !this.data.imagePath || !this.data.consent || !requireLogin()) return;
    if (!this.data.location) { toast(new Error('请先获取定位，再提交巡查')); return; }
    const sentToken = app().session.token();
    this.setData({ busy: true, error: '' });
    try {
      const asset = await app().api.upload(this.data.imagePath, 'recognition');
      if (this._destroyed) return;
      if (app().session.token() !== sentToken) { if (!app().session.token()) this.authError(new Error('登录已失效，请重新登录')); return; }
      const job = (await app().api.request('assessment-jobs/', { method: 'POST', data: {
        asset_id: asset.id,
        latitude: this.data.location.latitude,
        longitude: this.data.location.longitude,
        coordinate_system: 'GCJ02',
      } })).data;
      if (this._destroyed) return;
      if (app().session.token() !== sentToken) { if (!app().session.token()) this.authError(new Error('登录已失效，请重新登录')); return; }
      wx.navigateTo({ url: '/pages/assessment/index?jobId=' + encodeURIComponent(job.id) });
    } catch (error) { if (!this._destroyed && (!app().session.token() || app().session.token() === sentToken)) this.authError(error); }
    finally { if (!this._destroyed) this.setData({ busy: false }); }
  },
  openJob(event) {
    const id = event.currentTarget.dataset.id;
    if (id) wx.navigateTo({ url: '/pages/assessment/index?jobId=' + encodeURIComponent(id) });
  },
  authError(error) {
    if (this._destroyed) return;
    const loggedIn = Boolean(app().session.token());
    this.setData({ error: message(error), loggedIn });
    if (!loggedIn) this.clearPrivate();
  },
  login() { wx.switchTab({ url: '/pages/profile/index' }); },
  privacy() { wx.navigateTo({ url: '/pages/legal/index?kind=privacy' }); },
});
