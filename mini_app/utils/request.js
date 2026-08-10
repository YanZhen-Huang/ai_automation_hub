const DEFAULTS = {
  baseUrl: 'http://127.0.0.1:8780',
  token: ''
};

function getConfig() {
  return {
    baseUrl: wx.getStorageSync('mini_base_url') || DEFAULTS.baseUrl,
    token: wx.getStorageSync('mini_token') || DEFAULTS.token
  };
}

function saveConfig(baseUrl, token) {
  if (baseUrl !== undefined) wx.setStorageSync('mini_base_url', baseUrl);
  if (token !== undefined) wx.setStorageSync('mini_token', token);
}

function request(path, method, data) {
  const cfg = getConfig();
  return new Promise((resolve, reject) => {
    wx.request({
      url: cfg.baseUrl + path,
      method: method || 'GET',
      data: data || {},
      timeout: 10000,
      header: {
        'Content-Type': 'application/json',
        'X-API-Token': cfg.token
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          const msg = (res.data && res.data.detail) || ('HTTP ' + res.statusCode);
          reject({ statusCode: res.statusCode, message: msg });
        }
      },
      fail(err) {
        reject({ statusCode: 0, message: '无法连接服务器，请到「我的」页检查地址' });
      }
    });
  });
}

module.exports = { request, getConfig, saveConfig };
