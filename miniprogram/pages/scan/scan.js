const { request } = require("../../utils/request");

Page({
  data: {
    items: [],
    updatedAt: "",
    loading: false,
    error: ""
  },
  onShow() {
    this.loadScan();
  },
  async loadScan() {
    this.setData({ loading: true, error: "" });
    try {
      const res = await request("/api/scan/latest");
      const data = res.data || {};
      this.setData({
        items: data.items || [],
        updatedAt: data.updated_at || ""
      });
    } catch (e) {
      this.setData({ error: "加载扫描结果失败" });
    } finally {
      this.setData({ loading: false });
    }
  },
  async runScan() {
    this.setData({ loading: true, error: "" });
    try {
      await request("/api/scan/run", "POST", { dry_run: false });
      await this.loadScan();
    } catch (e) {
      this.setData({ error: "触发扫描失败" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
