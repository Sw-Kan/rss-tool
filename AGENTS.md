# AGENTS.md — rss-tool 开发规范

本文件是本仓库的**权威规范**。任何改动以本文件为准；与 `docs/` 冲突时以本文件为准，并顺手修正 `docs/`。

## 1. 项目概览

本地自托管的 RSS 阅读器。前端 `frontend/`（pnpm + Vite + React + TS），后端 `backend/`（Python + FastAPI + SQLite）。
产品范围见 `pages.md`（原始需求），视觉规范见 `docs/design-system.md`（从 Penpot 设计稿 `rss-tool-design` 提取）。

## 2. 常用命令

```bash
make setup      # 安装前后端依赖
make dev        # 同时启动后端(8000) + 前端(5173)
make test       # 后端 pytest + 前端 vitest
make lint       # ruff + eslint
make typecheck  # mypy(可选) + tsc --noEmit
make up         # docker compose 一键起
```

单端命令：

```bash
cd backend  && .venv/bin/uvicorn app.main:app --reload --port 8000
cd frontend && pnpm dev
cd backend  && .venv/bin/pytest -q
cd frontend && pnpm vitest run
```

## 3. 目录约定

```
backend/app/          FastAPI 应用（config/db/models/schemas/security/scheduler）
backend/app/routers/  每个功能域一个路由模块
backend/app/services/ 纯业务逻辑（可独立单测，不依赖 FastAPI）
backend/tests/        pytest
frontend/src/api/     后端调用 + queryKey 收敛点
frontend/src/features/ 按功能域组织的页面级组件
frontend/src/components/ 跨功能域复用组件
frontend/src/lib/     纯函数（必须可单测）
frontend/src/styles/  设计令牌
docs/                 架构、数据模型、API、设计系统、开发流程、路线图
```

## 4. 模块边界与写权限（强约束）

模块划分按**功能域横切**，详见 `docs/architecture.md`。**只有拥有者可以写对应数据**，禁止越权：

| 数据 | 唯一写入者 |
|---|---|
| `articles`、`feeds.etag/modified/last_*` | 抓取管线 |
| `user_item_state` | 阅读状态模块 |
| `folders`、`subscriptions` | 订阅管理模块 |
| `user_settings` | 设置模块 |
| `users.avatar_*` | 个人资料模块 |

**不变式（不可违反）**

1. 刷新订阅**绝不覆盖**已读/收藏状态。抓取管线不得读写 `user_item_state`。
2. `feeds` / `articles` 全局共享（同一 URL 只抓一次）；用户数据经 `subscriptions` + `user_item_state` 关联。
3. 收藏是**虚拟目录**，不落 `folders` 表。
4. 正文 HTML 必须先经 `sanitizeHtml()` 清洗再渲染。
5. 抓取用户提供的 URL 前必须过 SSRF 校验（含每次重定向后复检）。

## 5. 代码风格

**TypeScript / React**
- `strict: true`；禁止 `any`（用 `unknown` + 收窄）。
- 组件函数式 + hooks；文件内组件用 `export function`，不用 `default export`（路由懒加载入口除外）。
- 服务端状态一律走 TanStack Query，不自己写 `useEffect` 取数。
- 布尔/可选值显式处理，禁止 `!` 非空断言（除非紧跟长度检查）。
- 文案集中在 `src/lib/strings.ts`，不散落硬编码中文。

**Python**
- 行宽 100（ruff format 默认）；函数签名与返回值必须有类型注解；禁止裸 `except`。
- 路由层只做校验与编排，业务逻辑放 `services/`。
- 数据库访问用 SQLAlchemy 2.0 风格（`select()` + `Session.execute`），不用 legacy Query。
- 异步：抓取用 `httpx.AsyncClient`；同步 DB 通过 `run_in_threadpool`/`asyncio.to_thread` 调用。

**命名**：代码标识符与注释英文；用户可见文案中文。

## 6. API 约定

- 统一 `/api` 前缀；除 `/api/auth/*` 与 `/api/health` 外全部需要登录。
- 认证：JWT HS256 存在 httpOnly cookie `rss_token`（SameSite=Lax，30 天）。
- 错误体 `{"detail": string}`；未登录统一 `401 {"detail": "unauthorized"}`。
- 列表一律 **keyset 分页**（`cursor` + `limit`，默认 30，上限 100），禁止 offset 分页。
- 路由前缀已分配给后续模块，本阶段**不挂载**：`/api/ai`、`/api/integrations`、`/api/automation`、`/api/proxy`。

## 7. UI 约定

- **设计令牌优先**：颜色/字号/圆角/间距只能引用 `src/styles/tokens.css` 中的 CSS 变量或 Tailwind 语义类，禁止在组件里写裸 hex。
- 交互组件用 Radix primitives（dialog / tabs / dropdown-menu / switch / tooltip / avatar），样式自己写 Tailwind。
- 正文渲染：`dangerouslySetInnerHTML` + `sanitizeHtml()`；外链 `<a>` 必须 `target="_blank" rel="noopener noreferrer"`。
- 外链图片必须 `loading="lazy" referrerpolicy="no-referrer"` + `onError` 占位。
- 主题：`<html data-theme="light|dark">`，两套令牌在同一份 CSS 里定义。
- 不引入新依赖前先问：标准库 / 现有依赖能否覆盖。

## 8. 测试要求

| 改动内容 | 必须补的测试 |
|---|---|
| 后端业务逻辑（解析、分类、过滤、去重、导出、认证） | `backend/tests/test_*.py`（pytest） |
| 前端 `src/lib/` 下的纯函数 | 同目录 `*.test.ts`（vitest） |
| 纯样式 / 文案 / 布局微调 | 无需测试 |

- 抓取相关测试用 `respx` 拦截 HTTP，**不允许测试打真实网络**。
- 不追覆盖率数字；每个非平凡分支至少一条用例。

## 9. 提交规范

Conventional Commits，scope 用模块名：

```
feat(auth): 支持跳过登录并落到默认用户
fix(fetch): 重定向后复检 SSRF 黑名单
docs(design-system): 补充深色主题令牌
```

一次提交只做一个模块的改动；涉及数据模型变更必须在提交信息里写明"需删库重建"。

## 10. 完成定义（DoD）

一个改动完成 = 以下全部通过：

```bash
make lint && make typecheck && make test
```

外加：涉及 UI 的改动按 `docs/development.md` 的手工验收清单勾选对应条目。

## 11. 本阶段不做（禁止自行扩 scope）

- AI 总结 / 标题翻译（渲染入口也不要留假的）
- RSSHub / Obsidian / 飞书 / custom export 集成
- 自动化规则、代理配置、网页全文抽取、图片本地缓存、中英双语
- Alembic 迁移（表结构变更直接删 `backend/data/rss.db` 重建）
- 列表虚拟滚动、自动标记已读、多设备同步、Playwright 端到端测试

以上都在 `docs/roadmap.md` 里有边界与触发条件。要做，先改 `docs/roadmap.md` 并把对应模块从"后续"移到"当前"。

## 12. 已知限制（不要当 bug 修）

- 侧边栏顶部的搜索图标只做**本地过滤**（对已加载的目录名与源名做子串匹配），不发请求、不搜文章正文。
- 外链图片可能因防盗链加载失败，以占位图兜底。
- 单实例、无迁移、无密码找回、无登录限流。
