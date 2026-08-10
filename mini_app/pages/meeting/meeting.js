const { request } = require('../../utils/request');

Page({
  data: {
    id: null,
    meeting: null,
    phase1: [],
    phase2: [],
    attendance: [],
    loading: true
  },

  onLoad(options) {
    this.setData({ id: options.id });
  },

  onShow() {
    if (this.data.id) this.load();
  },

  load() {
    request('/api/meetings/' + this.data.id)
      .then(res => {
        this.setData({
          meeting: res.meeting,
          phase1: res.phase1 || [],
          phase2: res.phase2 || [],
          loading: false
        });
        this.loadAttendance();
      })
      .catch(err => {
        this.setData({ loading: false });
        wx.showToast({ title: err.message || '加载失败', icon: 'none' });
      });
  },

  loadAttendance() {
    request('/api/meetings/' + this.data.id + '/attendance')
      .then(res => this.setData({ attendance: res || [] }))
      .catch(() => {});
  },

  scanCheckIn() {
    wx.scanCode({
      scanType: ['qrCode', 'barCode'],
      success: res => {
        const name = ((res.result || '').trim().slice(0, 50)) || '扫码人员';
        request('/api/meetings/' + this.data.id + '/attendance', 'POST', { name })
          .then(data => {
            wx.showToast({
              title: data.is_new ? '签到成功' : '已签过到',
              icon: 'success'
            });
            this.setData({ attendance: data.attendance || [] });
          })
          .catch(err => wx.showToast({ title: err.message, icon: 'none' }));
      },
      fail: () => wx.showToast({ title: '未扫到内容', icon: 'none' })
    });
  },

  confirmItem(e) {
    const { meetingId, itemId } = e.currentTarget.dataset;
    wx.showModal({
      title: '人工确认',
      content: '确认该项已完成？',
      success: res => {
        if (!res.confirm) return;
        request('/api/meetings/' + meetingId + '/prep/' + itemId + '/done', 'POST', { result: '' })
          .then(() => {
            wx.showToast({ title: '已确认', icon: 'success' });
            this.load();
          })
          .catch(err => wx.showToast({ title: err.message, icon: 'none' }));
      }
    });
  },

  runPhase1() {
    wx.showModal({
      title: '提示',
      content: '重新运行一阶段（并行动作将重新提交）？',
      success: res => {
        if (!res.confirm) return;
        request('/api/meetings/' + this.data.id + '/run-phase1', 'POST')
          .then(() => {
            wx.showToast({ title: '已触发', icon: 'success' });
            this.load();
          })
          .catch(err => wx.showToast({ title: err.message, icon: 'none' }));
      }
    });
  },

  onPullDownRefresh() {
    this.load();
    wx.stopPullDownRefresh();
  }
});
