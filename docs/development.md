# 开发流程

## 环境

- Node ≥ 20（已验证 24.19.0）、Python ≥ 3.11（已验证 3.12.3）
- pnpm：`corepack enable pnpm`
- 后端依赖装在 `backend/.venv`，用 **uv** 创建与安装（系统缺 `python3-venv` 时 pip 建不了 venv）

## 首次启动

```bash
make setup          # uv 建 venv + 装后端依赖 + pnpm install
make dev            # 后端 :8000 + 前端 :5173
```

打开 http://localhost:5173 。首次可用登录页的「跳过，以 user 身份进入」直接进入。

## 数据库

`backend/data/rss.db`（自动创建）。**无迁移**：改表结构就删库重建：

```bash
make db-reset       # 删除 rss.db 与 uploads/，下次启动重建
```

数据与上传文件都在 `backend/data/`，删除该目录即清空全部本地数据。

## 调试

| 场景 | 做法 |
|---|---|
| 看 API 文档 | http://localhost:8000/docs |
| 单独调某个源 | `curl -X POST localhost:8000/api/feeds/{id}/refresh`（需 cookie） |
| 前端绕过代理直连 | `frontend/.env.local` 里设 `VITE_API_BASE=http://localhost:8000` |
| 看调度器是否在跑 | 后端日志里的 `scheduler: user ... 每 N 分钟刷新` |
| 加自建 RSSHub / 局域网源 | 设 `ALLOW_PRIVATE_FETCH=true` 后重启后端；默认会被 SSRF 防护拒绝 |

## 测试

```bash
make test       # pytest + vitest
make lint       # ruff + eslint
make typecheck  # tsc --noEmit
```

抓取相关测试用 `respx` 拦截，不打真实网络。

## 手工验收清单

对应各模块的验收标准，发布前逐条走一遍。

- [ ] 登录页点「跳过」→ 进入阅读器，侧边栏底部显示 `user` / `example@example.com`
- [ ] 注册新账号 → 数据与 `user` 完全隔离（看不到对方的已读与订阅）
- [ ] 设置 → 订阅源 → 添加一个 RSS 源 → 侧边栏出现其 logo 与名称
- [ ] 目录刷新后列表出现文章；**再次刷新**不产生重复且已读/收藏保持
- [ ] 加一个坏源（如 `http://localhost:8000/nope`）→ 只该源报错，其它源正常
- [ ] 一级过滤：全部 / 文章 / 图片 / 视频 切换结果正确
- [ ] 收藏 ⊕ 视频 = 只有收藏的视频；目录 ⊕ 图片 = 只有该目录内图片源的图片
- [ ] 拖拽侧边栏与列表分隔条后刷新页面，宽度保持
- [ ] 图片页 6 列瀑布流无重叠；视频页宽屏每行 5 个；滚到底自动加载下一页
- [ ] 标记已读 / 收藏后刷新保持；批量已读后未读计数下降
- [ ] 正文里的 `<script>` 不执行（用一条含 script 的测试 feed 验证）
- [ ] 导出 OPML 能被第三方阅读器导入，且目录层级保留
- [ ] 上传 >3MB 或改名的文本文件当头像 → 被拒；首字母头像 5 色可切换
- [ ] 主题切深色后刷新保持；刷新间隔改为 5 分钟后调度器按新间隔触发
- [ ] 导出我的数据（JSON）可被 `jq` 解析且含已读/收藏记录

## 提交

Conventional Commits + 模块 scope，见 `AGENTS.md` §9。DoD 见 §10。
