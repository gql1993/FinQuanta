const { request } = require("../../utils/request");

Page({
  data: {
    summary: null,
    positions: null,
    recommendations: [],
    analysis: "",
    loading: false,
    error: "",
    approve: {
      mode: "auto",
      action: "BUY",
      code: "",
      name: "",
      price: "",
      shares: ""
    }
  },
  onShow() {
    this.loadData();
  },
  async loadData() {
    this.setData({ loading: true, error: "" });
    try {
      const [s, p, r] = await Promise.all([
        request("/api/portfolio/summary"),
        request("/api/portfolio/positions"),
        request("/api/portfolio/recommendations")
      ]);
      this.setData({
        summary: s.data || null,
        positions: p.data || null,
        recommendations: (r.data && r.data.items) || [],
        analysis: (r.data && r.data.analysis) || ""
      });
    } catch (e) {
      this.setData({ error: "加载仓位失败" });
    } finally {
      this.setData({ loading: false });
    }
  },
  useRecommendation(e) {
    const idx = e.currentTarget.dataset.index;
    const item = (this.data.recommendations || [])[idx];
    if (!item) return;
    const approve = this.data.approve;
    approve.mode = "auto";
    approve.action = (item.action || "buy").toUpperCase();
    approve.code = item.code || "";
    approve.name = item.name || "";
    approve.price = item.price || "";
    approve.shares = item.shares || "";
    this.setData({ approve });
  },
  onApproveField(e) {
    const field = e.currentTarget.dataset.field;
    const approve = this.data.approve;
    approve[field] = e.detail.value;
    this.setData({ approve });
  },
  async submitApproval() {
    this.setData({ loading: true, error: "" });
    try {
      const payload = {
        mode: this.data.approve.mode || "auto",
        action: this.data.approve.action || "BUY",
        code: this.data.approve.code,
        name: this.data.approve.name,
        price: Number(this.data.approve.price),
        shares: Number(this.data.approve.shares),
        reason: "小程序审批"
      };
      const res = await request("/api/approval/trade", "POST", payload);
      wx.showToast({ title: res.data && res.data.approved ? "审批执行成功" : "已提交", icon: "none" });
      await this.loadData();
    } catch (e) {
      this.setData({ error: "审批执行失败" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
