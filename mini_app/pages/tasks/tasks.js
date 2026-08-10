const { request } = require('../../utils/request');

Page({
  data: {
    filter: 'active',
    tasks: []
  },

  onShow() {
    this.load();
  },

  load() {
    const status = this.data.filter === 'all' ? '' : this.data.filter;
    request('/api/tasks' + (status ? '?status=' + status : ''))
      .then(res => {
        this.setData({ tasks: res || [] });
      })
      .catch(err => wx.showToast({ title: err.message, icon: 'none' }));
  },

  switchFilter(e) {
    this.setData({ filter: e.currentTarget.dataset.f }, () => this.load());
  },

  doAction(e) {
    const { id, action } = e.currentTarget.dataset;
    const path = '/api/tasks/' + id + (action === 'done' ? '/done' : action === 'dismiss' ? '/dismiss' : '/reactivate');
    request(path, 'POST')
      .then(() => {
        wx.showToast({ title: '已操作', icon: 'success' });
        this.load();
      })
      .catch(err => wx.showToast({ title: err.message, icon: 'none' }));
  },

  onPullDownRefresh() {
    this.load();
    wx.stopPullDownRefresh();
  }
});
