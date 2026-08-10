const { request } = require('../../utils/request');

Page({
  data: {
    meetings: [],
    activeTaskCount: 0,
    loaded: false
  },

  onShow() {
    this.load();
  },

  load() {
    request('/api/mini/overview')
      .then(res => {
        this.setData({
          meetings: res.meetings || [],
          activeTaskCount: res.active_task_count || 0,
          loaded: true
        });
      })
      .catch(err => {
        this.setData({ loaded: true });
        wx.showToast({ title: err.message || '加载失败', icon: 'none' });
      });
  },

  goMeeting(e) {
    wx.navigateTo({ url: '/pages/meeting/meeting?id=' + e.currentTarget.dataset.id });
  },

  onPullDownRefresh() {
    this.load();
    wx.stopPullDownRefresh();
  }
});
