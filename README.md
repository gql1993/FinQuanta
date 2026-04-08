# FinQuanta

基于 PyQt6 的 A 股 AI 量化交易桌面客户端，配套 FastAPI 服务、小程序与 OpenClaw 等扩展能力。

## 数据与部署策略（推荐：模式 A）

- **桌面端**：默认使用本地 SQLite（`data_cache/quant.db`），安装即用。
- **API / 服务化部署**：推荐使用 PostgreSQL，详见 `.env.api.example` 与 [基础设施升级说明](doc/基础设施升级_服务化部署说明.md)。

两端数据不要求天然一致；需要一致时应单独设计同步或导入导出。

## 文档

- [系统介绍](doc/FinQuanta_系统介绍文档.md)
- [基础设施与服务化部署](doc/基础设施升级_服务化部署说明.md)
- [API 接口设计](doc/FinQuanta_API接口设计书.md)
