const { request } = require("../../utils/request");

Page({
  data: {
    code: "",
    summary: null,
    kline: [],
    verify: [],
    error: ""
  },
  onCode(e) {
    this.setData({ code: e.detail.value });
  },
  async query() {
    if (!this.data.code) return;
    try {
      const [summaryRes, klineRes, verifyRes] = await Promise.all([
        request(`/api/stock/${this.data.code}`),
        request(`/api/stock/${this.data.code}/kline?limit=20`),
        request(`/api/stock/${this.data.code}/verify?limit=10`)
      ]);
      this.setData({
        summary: summaryRes.data || null,
        kline: (klineRes.data && klineRes.data.items) || [],
        verify: verifyRes.data || [],
        error: ""
      });
      setTimeout(() => this.drawChart(), 50);
    } catch (e) {
      this.setData({ error: "查询失败" });
    }
  },
  drawChart() {
    const items = this.data.kline || [];
    if (!items.length) return;
    const query = wx.createSelectorQuery();
    query.select('#klineCanvas').fields({ node: true, size: true }).exec((res) => {
      const data = res && res[0];
      if (!data || !data.node) return;
      const canvas = data.node;
      const ctx = canvas.getContext('2d');
      const dpr = wx.getWindowInfo ? wx.getWindowInfo().pixelRatio : 1;
      canvas.width = data.width * dpr;
      canvas.height = data.height * dpr;
      ctx.scale(dpr, dpr);

      const w = data.width;
      const h = data.height;
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#0d1117';
      ctx.fillRect(0, 0, w, h);

      const closes = items.map(x => Number(x.close || 0));
      const maxV = Math.max(...closes);
      const minV = Math.min(...closes);
      const pad = 16;
      const innerW = w - pad * 2;
      const innerH = h - pad * 2;

      ctx.strokeStyle = '#30363d';
      ctx.lineWidth = 1;
      ctx.strokeRect(pad, pad, innerW, innerH);

      ctx.beginPath();
      ctx.strokeStyle = '#4fc3f7';
      ctx.lineWidth = 2;
      closes.forEach((v, i) => {
        const x = pad + (innerW * i) / Math.max(closes.length - 1, 1);
        const y = pad + innerH - ((v - minV) / Math.max(maxV - minV, 0.0001)) * innerH;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      });
      ctx.stroke();

      ctx.fillStyle = '#8b949e';
      ctx.font = '12px sans-serif';
      ctx.fillText(String(minV.toFixed(2)), 2, h - 4);
      ctx.fillText(String(maxV.toFixed(2)), 2, 14);
    });
  }
});
