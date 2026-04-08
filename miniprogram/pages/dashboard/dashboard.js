const { request } = require("../../utils/request");

Page({
  data: {
    snapshot: null,
    loading: false,
    error: ""
  },
  onShow() {
    this.loadSnapshot();
  },
  async loadSnapshot() {
    this.setData({ loading: true, error: "" });
    try {
      const res = await request("/api/snapshot/system");
      this.setData({ snapshot: res.data || null });
    } catch (e) {
      this.setData({ error: "加载失败，请检查 API 服务" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
