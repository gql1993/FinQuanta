App({
  globalData: {
    token: wx.getStorageSync("fq_token") || "",
    profile: null,
    apiBase: "http://127.0.0.1:9000"
  },
  onLaunch() {
    const token = wx.getStorageSync("fq_token");
    if (token) {
      this.globalData.token = token;
    }
  }
});
