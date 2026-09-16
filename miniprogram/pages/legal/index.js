Page({ data: { privacy: true }, onLoad(options) { const privacy = options.kind !== 'terms'; this.setData({ privacy }); wx.setNavigationBarTitle({ title: privacy ? '隐私说明' : '用户协议' }); } });
