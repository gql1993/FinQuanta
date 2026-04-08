const { request } = require("../../utils/request");

Page({
  data: {
    ops: null,
    weights: [],
    loading: false,
    error: ""
  },
  onShow() {
    this.refresh();
  },
  async refresh() {
    this.setData({ loading: true, error: "" });
    try {
      const ops = await request("/api/ops/center");
      const w = await request("/api/openclaw/weights");
      this.setData({ ops: ops.data || null, weights: Object.entries(w.data || {}) });
    } catch (e) {
      this.setData({ error: "加载 OpenClaw 数据失败" });
    } finally {
      this.setData({ loading: false });
    }
  },
  async runPipeline() {
    this.setData({ loading: true, error: "" });
    try {
      await request("/api/openclaw/pipeline/run", "POST", { dry_run: false });
      await this.refresh();
    } catch (e) {
      this.setData({ error: "启动全流程失败" });
    } finally {
      this.setData({ loading: false });
    }
  },
  async runLearn() {
    this.setData({ loading: true, error: "" });
    try {
      await request("/api/openclaw/learn/run", "POST", { dry_run: false });
      await this.refresh();
    } catch (e) {
      this.setData({ error: "启动学习失败" });
    } finally {
      this.setData({ loading: false });
    }
  },
  async triggerTask(e) {
    const task = e.currentTarget.dataset.task;
    this.setData({ loading: true, error: "" });
    try {
      await request(`/api/task/trigger/${task}`, "POST", { dry_run: false });
      await this.refresh();
    } catch (e) {
      this.setData({ error: "触发任务失败" });
    } finally {
      this.setData({ loading: false });
    }
  }
});
