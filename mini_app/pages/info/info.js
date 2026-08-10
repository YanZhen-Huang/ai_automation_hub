const { request } = require('../../utils/request');

Page({
  data: {
    text: '',
    items: [],
    submitting: false
  },

  onShow() {
    this.load();
  },

  load() {
    request('/api/info?limit=20')
      .then(res => {
        this.setData({ items: res || [] });
      })
      .catch(err => wx.showToast({ title: err.message, icon: 'none' }));
  },

  onInput(e) {
    this.setData({ text: e.detail.value });
  },

  submit(text) {
    const content = (text || this.data.text || '').trim();
    if (!content) {
      wx.showToast({ title: '请输入内容', icon: 'none' });
      return;
    }
    this.setData({ submitting: true });
    request('/api/info', 'POST', { text: content })
      .then(() => {
        wx.showToast({ title: '已提交，AI 提炼中', icon: 'success' });
        this.setData({ text: '', submitting: false });
        this.load();
      })
      .catch(err => {
        this.setData({ submitting: false });
        wx.showToast({ title: err.message, icon: 'none' });
      });
  },

  scan() {
    wx.scanCode({
      scanType: ['qrCode', 'barCode'],
      success: res => {
        const content = res.result || '';
        wx.showModal({
          title: '扫码结果',
          editable: true,
          placeholderText: '扫码内容，可修改',
          content,
          confirmText: '提交入库',
          success: modal => {
            if (!modal.confirm) return;
            this.submit(modal.content);
          }
        });
      },
      fail: () => wx.showToast({ title: '未扫到内容', icon: 'none' })
    });
  },

  onPullDownRefresh() {
    this.load();
    wx.stopPullDownRefresh();
  }
});
