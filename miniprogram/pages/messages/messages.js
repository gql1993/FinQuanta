const { request } = require("../../utils/request");

Page({
  data: {
    items: [],
    filtered: [],
    filter: "",
    loading: false,
    error: ""
  },
  onShow() {
    this.loadMessages();
  },
  async loadMessages() {
    this.setData({ loading: true, error: "" });
    try {
      const res = await request("/api/messages");
      const items = res.data || [];
      this.setData({ items, filtered: items });
    } catch (e) {
      this.setData({ error: "加载消息失败" });
    } finally {
      this.setData({ loading: false });
    }
  },
  onFilter(e) {
    const filter = e.currentTarget.dataset.filter || "";
    const items = this.data.items || [];
    let filtered = items;
    if (filter) {
      filtered = items.filter(x => (x.type || "").indexOf(filter) >= 0 || (x.title || "").indexOf(filter) >= 0);
    }
    this.setData({ filter, filtered });
  }
});
