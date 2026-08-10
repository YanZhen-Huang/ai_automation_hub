const { request, getConfig, saveConfig } = require('../../utils/request');

Page({
  data: {
    baseUrl: '',
    token: '',
    testing: false,
    testResult: '',
    qrLoading: false,
    qrUrl: '',
    qrImage: ''
  },

  onLoad() {
    const cfg = getConfig();
    this.setData({ baseUrl: cfg.baseUrl, token: cfg.token });
  },

  onBaseUrl(e) {
    this.setData({ baseUrl: e.detail.value });
  },

  onToken(e) {
    this.setData({ token: e.detail.value });
  },

  save() {
    saveConfig(this.data.baseUrl.trim().replace(/\/+$/, ''), this.data.token.trim());
    wx.showToast({ title: '已保存', icon: 'success' });
  },

  test() {
    saveConfig(this.data.baseUrl.trim().replace(/\/+$/, ''), this.data.token.trim());
    this.setData({ testing: true, testResult: '' });
    request('/api/health')
      .then(res => {
        this.setData({
          testing: false,
          testResult: '连接成功！' + (res.mini_token_set ? '（服务端已开启口令校验）' : '')
        });
      })
      .catch(err => {
        this.setData({ testing: false, testResult: '连接失败：' + (err.message || '未知错误') });
      });
  },

  generateQr() {
    this.setData({ qrLoading: true, qrUrl: '', qrImage: '' });
    request('/api/mini/qr')
      .then(res => {
        this.setData({
          qrLoading: false,
          qrUrl: res.url || '',
          qrImage: res.qr_base64 ? 'data:image/png;base64,' + res.qr_base64 : ''
        });
      })
      .catch(err => {
        this.setData({ qrLoading: false });
        wx.showToast({ title: err.message, icon: 'none' });
      });
  },

  copyUrl() {
    if (!this.data.qrUrl) return;
    wx.setClipboardData({
      data: this.data.qrUrl,
      success: () => wx.showToast({ title: '已复制', icon: 'success' })
    });
  }
});
