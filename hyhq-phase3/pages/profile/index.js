const { app, finish, toast } = require('../../lib/page');
const { message } = require('../../lib/format');
Page({
  data: { loading: true, error: '', busy: false, user: null, nickname: '', avatar: '', devAvailable: false, agreed: false, authMode: '' },
  onShow() { this.load(); },
  onPullDownRefresh() { this.load(); },
  async load() {
    if (this._loading) return;
    this._loading = true;
    this.setData({ loading: true, error: '', user: null, avatar: '', devAvailable: false });
    try {
      const health = (await app().api.request('health/')).data;
      app().globalData.health = health;
      this.setData({ devAvailable: app().config.development && health.dev_auth_enabled === true });
      if (app().session.token()) await this.loadUser();
    } catch (error) {
      this.setData({ error: message(error), user: null });
    } finally { this._loading = false; finish(this); }
  },
  async loadUser() {
    const user = (await app().api.request('me/')).data;
    app().session.updateUser(user);
    this.setData({ user, nickname: user.nickname || '', authMode: (app().session.get() || {}).auth_mode || '' });
    if (user.avatar_url) {
      try { this.setData({ avatar: await app().api.download(user.avatar_url) }); }
      catch (error) { this.setData({ avatar: '' }); }
    }
  },
  consent(event) { this.setData({ agreed: event.detail.value.includes('agree') }); },
  async login(event) {
    if (this.data.busy || !this.data.agreed) return;
    const dev = event.currentTarget.dataset.mode === 'dev';
    if (dev && !this.data.devAvailable) return;
    this.setData({ busy: true, error: '' });
    try {
      let path, data;
      if (dev) {
        path = 'auth/dev/'; data = { device_id: app().session.deviceId() };
      } else {
        const result = await new Promise((resolve, reject) => wx.login({ success: resolve, fail: () => reject(new Error('微信登录暂不可用，请检查 AppID 与开发者权限')) }));
        if (!result.code) throw new Error('微信未返回登录 code，请重试');
        path = 'auth/wechat/'; data = { code: result.code };
      }
      const result = (await app().api.request(path, { method: 'POST', data })).data;
      app().session.save(Object.assign({}, result, { auth_mode: dev ? 'development' : 'wechat' }));
      await this.loadUser();
      wx.showToast({ title: dev ? '已进入开发账号' : '登录成功', icon: 'success' });
    } catch (error) { this.setData({ error: message(error) }); }
    finally { this.setData({ busy: false }); }
  },
  nicknameInput(event) { this.setData({ nickname: event.detail.value }); },
  async saveProfile() {
    const nickname = this.data.nickname.trim();
    if (!nickname) { toast(new Error('请输入昵称')); return; }
    await this.update({ nickname });
  },
  async privacyChange(event) { await this.update({ record_history: event.detail.value }); },
  async update(data) {
    if (this.data.busy) return;
    this.setData({ busy: true });
    try {
      const user = (await app().api.request('me/', { method: 'PATCH', data })).data;
      app().session.updateUser(user);
      this.setData({ user, nickname: user.nickname || '' });
      wx.showToast({ title: '已保存', icon: 'success' });
    } catch (error) {
      if (!app().session.token()) this.setData({ user: null, avatar: '' });
      else if (this.data.user) this.setData({ user: Object.assign({}, this.data.user) });
      toast(error);
    } finally { this.setData({ busy: false }); }
  },
  async chooseAvatar(event) {
    if (this.data.busy || !event.detail.avatarUrl) return;
    this.setData({ busy: true });
    try {
      const asset = await app().api.upload(event.detail.avatarUrl, 'avatar');
      const user = (await app().api.request('me/', { method: 'PATCH', data: { avatar_asset_id: asset.id } })).data;
      app().session.updateUser(user);
      this.setData({ user, avatar: '' });
      if (user.avatar_url || asset.thumbnail_url) this.setData({ avatar: await app().api.download(user.avatar_url || asset.thumbnail_url) });
      wx.showToast({ title: '头像已更新', icon: 'success' });
    } catch (error) { toast(error); if (!app().session.token()) this.setData({ user: null, avatar: '' }); }
    finally { this.setData({ busy: false }); }
  },
  records(event) { wx.navigateTo({ url: '/pages/records/index?kind=' + event.currentTarget.dataset.kind }); },
  legal(event) { wx.navigateTo({ url: '/pages/legal/index?kind=' + event.currentTarget.dataset.kind }); },
  logout() {
    if (this.data.busy) return;
    wx.showModal({ title: '退出登录', content: '退出后仍可浏览公开的生态与科普资料。', confirmText: '退出登录', success: async (result) => {
      if (!result.confirm) return;
      this.setData({ busy: true });
      try {
        await app().api.request('auth/logout/', { method: 'POST' });
        app().session.clear();
        this.setData({ user: null, avatar: '', nickname: '' });
      } catch (error) {
        if (!app().session.token()) this.setData({ user: null, avatar: '', nickname: '' });
        else toast(error);
      } finally { this.setData({ busy: false }); }
    } });
  },
  deleteAccount() {
    if (this.data.busy) return;
    wx.showModal({ title: '注销账号', content: '注销会使现有会话失效，并删除账号、个人记录和上传图片。此操作无法恢复。', confirmText: '确认注销', confirmColor: '#a25e4a', success: async (result) => {
      if (!result.confirm) return;
      this.setData({ busy: true });
      try {
        await app().api.request('me/', { method: 'DELETE' });
        app().session.clear();
        this.setData({ user: null, avatar: '', nickname: '', agreed: false });
        wx.showToast({ title: '账号已注销', icon: 'success' });
      } catch (error) { toast(error); }
      finally { this.setData({ busy: false }); }
    } });
  },
});
