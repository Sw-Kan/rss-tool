# rss-tool

本地自托管的 RSS 阅读器。单用户、单实例，数据只落在自己的磁盘上（SQLite + 本地媒体缓存），没有任何云端同步。

- **三种阅读形态**：文章（左列表 + 右正文）、图片瀑布流（6 列）、视频网格（5 列）。后两者的详情走灯箱弹层，不挤压浏览区。
- **订阅管理**：目录 / 源两级，源可以长按拖到别的目录；支持 OPML 导入导出。
- **已读与收藏**：收藏是虚拟目录，与目录同级互斥、和内容类型横向叠加（「收藏的视频」= 两者相交）。
- **全文抽取**：feed 只给短摘要时去原网页抽正文（readability），抽取结果不会被下一轮刷新覆盖。
- **AI 助手**：总结与标题翻译，流式逐字输出；按 `position` 依次尝试所有启用的供应商，每家重试 2 次后故障转移。
- **集成**：自建 RSSHub（只管连接：地址 + 密钥 + 测试）、Obsidian 落盘、飞书推送、自定义接口导出（固定 JSON 结构）。
- **自动化**：触发可以是新条目 / 新视频 / 新图片 / 定时；条件按标题、字数、频道、源、类型、已读、收藏任意组合（`且 / 或`）；动作是收藏、标已读 / 未读、飞书推送、写入 Obsidian、推自定义接口。定时规则的时间按 `TZ` 解释。
- **代理**：系统代理或自定义（HTTP / HTTPS / SOCKS5 + `NO_PROXY`，支持 `.suffix` 与 CIDR）。
- **媒体缓存**：外链图经后端代理落盘，带 `Referer` 绕开防盗链，按总字节做 LRU 淘汰。
- 深浅色主题、中英双语（`zh-CN` / `en`）、数据导出 JSON、头像上传。
- 登录可以跳过（落到默认用户 `user`），密码用 bcrypt，会话是 httpOnly cookie 里的 JWT。

## 技术栈

| 层 | 选型 |
|---|---|
| 前端 | React 19 · TypeScript（strict）· Vite · Tailwind v4 · Radix primitives · TanStack Query · react-router |
| 后端 | Python 3.11+ · FastAPI · SQLAlchemy 2.0 · SQLite · APScheduler · httpx · readability-lxml |
| 数据 | SQLite（`backend/data/rss.db`）+ 媒体缓存目录（`backend/data/media/`）|
| 测试 | pytest（后端，网络请求一律 `respx` 拦截）· vitest + Testing Library（前端）|

## 快速开始

需要：Python ≥ 3.11 + [uv](https://github.com/astral-sh/uv)、Node 22 + pnpm 9（`corepack enable` 即可）。

```bash
make setup   # 安装前后端依赖
make dev     # 后端 http://localhost:8000，前端 http://localhost:5173
```

首次进入可直接点登录页的「跳过，以 user 身份进入」。

Docker（前端由 nginx 提供静态文件并反代 `/api`，所以只有一个入口端口）：

```bash
make up      # http://localhost:8080
make down
```

## 配置

复制 `.env.example` 为 `.env`，不填也能跑（后端会自动生成密钥）。常用项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `SECRET_KEY` | 自动生成 | JWT 签名密钥 |
| `ALLOW_PRIVATE_FETCH` | `false` | 是否允许抓内网 / 本机地址。**自建 RSSHub、局域网 feed 必须打开**；默认关闭是为防御 SSRF |
| `EXTRACT_ENABLED` / `EXTRACT_MIN_CHARS` / `EXTRACT_MAX_PER_REFRESH` | `true` / `200` / `10` | 全文抽取开关与每轮刷新上限 |
| `AI_TIMEOUT_SECONDS` / `AI_RETRY_BACKOFF_SECONDS` | `60` / `3` | 上游超时与退避重试间隔 |
| `MEDIA_CACHE_ENABLED` / `MEDIA_CACHE_MAX_MB` | `true` / `512` | 图片缓存与磁盘预算（超出按 LRU 淘汰）|
| `TZ` | 容器默认 UTC | 自动化「定时」规则按它解释，**Docker 里建议显式设置** |

AI 供应商、集成、代理**不在环境变量里**：它们是用户在「设置」弹窗里填的，存在数据库（见 `docs/data-model.md`）。

## 常用命令

| 命令 | 作用 |
|---|---|
| `make setup` / `make dev` | 装依赖 / 同时起前后端 |
| `make test` | 后端 pytest + 前端 vitest |
| `make lint` / `make typecheck` | ruff + eslint / tsc --noEmit |
| `make up` / `make down` | docker compose 起停（`http://localhost:8080`）|
| `make db-reset` | 删库重建（项目无迁移机制）|

## 安全与边界

- 抓取前对 URL 做 SSRF 校验（含**每次重定向后复检**）；`ALLOW_PRIVATE_FETCH=true` 才放行内网。
- 正文 HTML 一律经 `sanitizeHtml()` 清洗后渲染，外链带 `rel="noopener noreferrer"`。
- 媒体缓存只缓存**栅格图**白名单，**绝不缓存 SVG**（SVG 能带脚本，等于开 XSS），类型按魔数判定。
- AI 的 `api_key` 明文存本地 SQLite 且**永不回传前端**（只给掩码），日志里也不打印。
- 单用户本地实例：没有注册审核、密码找回、登录限流、多设备同步——这是定位而不是缺失。

## 文档

| 文件 | 内容 |
|---|---|
| `AGENTS.md` | **开发规范（权威）**：模块边界、写权限不变式、代码风格、DoD、已知限制 |
| `docs/architecture.md` | 进程拓扑、分层、抓取 / 抽取 / AI / 自动化 / 代理 / 媒体管线 |
| `docs/data-model.md` | 表结构与写入者 |
| `docs/api.md` | 接口契约（含 keyset 分页与错误约定）|
| `docs/design-system.md` | 设计令牌与组件清单（源自 Penpot 设计稿）|
| `docs/development.md` | 启动、调试、手工验收清单 |
| `docs/roadmap.md` | 已划边界但未实现的功能 |
| `pages.md` | 原始需求说明 |

## 注意

- 项目**没有数据库迁移**：改表结构就是删库重建（`make db-reset`），本地实例里数据随时可重新抓。
- 抓取类测试用 `respx` 拦截 HTTP，不会打真实网络。
- 视觉规范以 `docs/design-system.md` 为准；Penpot 设计稿与代码不一致时，先改稿再改代码。

## License

MIT，见 `LICENSE`。
