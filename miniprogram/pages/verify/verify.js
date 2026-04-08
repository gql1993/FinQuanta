const { request } = require("../../utils/request");

const { request } = require("../../utils/request");

Page({
  data: {
    summary: null,
    records: [],
    loading: false,
    error: "",
    strategy: "",
    selected: null
  },
  onShow() {
    this.loadData();
  },
  onStrategy(e) {
    this.setData({ strategy: e.detail.value });
  },
  async loadData() {
    this.setData({ loading: true, error: "" });
    try {
      const [sumRes, recRes] = await Promise.all([
        request("/api/verify/summary"),
        request(`/api/verify/records?limit=100${this.data.strategy ? `&strategy=${this.data.strategy}` : ""}`)
      ]);
      this.setData({
        summary: sumRes.data || null,
        records: recRes.data || [],
        selected: null,
        error: ""
      });
    } catch (e) {
      this.setData({ error: "加载走势验证失败" });
    } finally {
      this.setData({ loading: false });
    }
  },
  onSelectRecord(e) {
    const idx = e.currentTarget.dataset.index;
    const records = this.data.records || [];
    this.setData({ selected: records[idx] || null });
  }
});
