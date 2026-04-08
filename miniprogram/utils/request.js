const API_BASE = "http://127.0.0.1:9000";

function request(path, method = "GET", data = null) {
  const token = wx.getStorageSync("fq_token") || "";
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE}${path}`,
      method,
      data,
      header: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {})
      },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          reject(res.data || res);
        }
      },
      fail(err) {
        reject(err);
      }
    });
  });
}

module.exports = {
  API_BASE,
  request
};
