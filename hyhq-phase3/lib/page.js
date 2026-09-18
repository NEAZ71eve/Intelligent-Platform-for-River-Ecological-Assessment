const format = require('./format');
function app() { return getApp(); }
function toast(error) { wx.showToast({ title: format.message(error), icon: 'none', duration: 3000 }); }
function requireLogin() {
  if (app().session.token()) return true;
  wx.showModal({ title: '需要登录', content: '登录后可保存个人记录、上传图片。', confirmText: '去登录', success(result) { if (result.confirm) wx.switchTab({ url: '/pages/profile/index' }); } });
  return false;
}
function detail(kind, id) { wx.navigateTo({ url: '/pages/detail/index?kind=' + encodeURIComponent(kind) + '&id=' + encodeURIComponent(id) }); }
function finish(page) { page.setData({ loading: false }); wx.stopPullDownRefresh(); }
module.exports = { app, toast, requireLogin, detail, finish };
