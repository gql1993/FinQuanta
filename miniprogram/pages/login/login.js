const { request } = require("../../utils/request");

Page({
  data: {
    username: "admin",
    password: "admin123",
    loading: false,
    error: ""
  },
  onUsername(e) {
    this.setData({ username: e.detail.value });
  },
  onPassword(e) {
    this.setData({ password: e.detail.value });
  },
  async onLogin() {
    this.setData({ loading: true, error: "" });
    try {
      const res = await request("/api/auth/login", "POST", {
        username: this.data.username,
        password: this.data.password
      });
      if (res.ok && res.token) {
        wx.setStorageSync("fq_token", res.token);
        wx.switchTab({ url: "/pages/dashboard/dashboard" });
      } else {
        this.setData({ error: res.message || "登录失败" });
      }
    } catch (e) {
      this.setData({ error: "接口不可用，请先启动 API 服务" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
