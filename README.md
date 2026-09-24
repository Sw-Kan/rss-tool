# rss-tool

本地自托管的 RSS 阅读器。支持订阅源分类管理、三种内容布局（文章 / 图片瀑布流 / 视频网格）、已读与收藏、深浅色主题、OPML 导入导出。

- 前端：pnpm + Vite + React + TypeScript + Tailwind + Radix
- 后端：FastAPI + SQLAlchemy + SQLite
- 数据全部保存在本地（`backend/data/`），不联网同步

## 快速开始

```bash
make setup   # 安装前后端依赖
make dev     # 前端 http://localhost:5173，后端 http://localhost:8000
```

首次进入可直接点登录页的「跳过，以 user 身份进入」。

Docker：

```bash
make up      # http://localhost:5173
```

## 文档

| 文件 | 内容 |
|---|---|
| `AGENTS.md` | **开发规范（权威）**：模块边界、写权限、代码风格、DoD |
| `docs/architecture.md` | 进程拓扑、分层、抓取管线 |
| `docs/data-model.md` | 表结构 |
| `docs/api.md` | 接口契约 |
| `docs/design-system.md` | 设计令牌与组件清单（源自 Penpot 设计稿） |
| `docs/development.md` | 启动、调试、手工验收清单 |
| `docs/roadmap.md` | 已划边界未实现的功能 |
| `pages.md` | 原始需求说明 |
