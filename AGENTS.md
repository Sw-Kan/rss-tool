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

`backend/` 与 `frontend/` 各有一份 `.dockerignore`：前端那份必须排除 `node_modules/`，
否则 Dockerfile 里的 `COPY . .` 会把宿主机的二进制盖进镜像。改 Dockerfile 时别把它删了。

## 4. 模块边界与写权限（强约束）

模块划分按**功能域横切**，详见 `docs/architecture.md`。**只有拥有者可以写对应数据**，禁止越权：

| 数据 | 唯一写入者 |
|---|---|
| `articles`（除下一行列出的字段）与 `feeds` 的抓取元数据 | 抓取管线 |
| `articles.content_html`、`word_count`、`content_source`、`extract_status`、`extracted_at` | 全文抽取 |
| `user_item_state` | 阅读状态模块 |
| `folders`、`subscriptions` | 订阅管理模块 |
| `user_settings` | 设置模块 |
| `users.avatar_*` | 个人资料模块 |
| `ai_providers`、`ai_results` | AI 助手 |
| `integrations` | 集成 |
| `automation_rules` | 自动化 |
| `proxy_config` | 代理（实例级单行，不按用户分） |
| `media_cache` | 媒体缓存 |

**不变式（不可违反）**

1. 刷新订阅**绝不覆盖**已读/收藏状态。抓取管线不得读写 `user_item_state`。
2. 刷新订阅**绝不用 feed 的短摘要覆盖已抽取的全文**：`content_source == 'extracted'` 时，抓取管线不写 `content_html` / `word_count`。
3. 抽取失败必须保留 feed 自带内容，绝不写入空正文或半成品。
4. `feeds` / `articles` 全局共享（同一 URL 只抓一次）；用户数据经 `subscriptions` + `user_item_state` 关联。
5. 收藏是**虚拟目录**，不落 `folders` 表；路由上它与目录**同级互斥**（`fav` 与 `folder` 不能同时有值），一级类型横向叠加。
6. 正文 HTML 必须先经 `sanitizeHtml()` 清洗再渲染。
7. `ai_providers.api_key` 明文落库但**永不回传**给前端（只给掩码提示）；日志里也不打印。
8. 自动化**不得直接写 `user_item_state`**，改状态一律经 `services/item_state.py`（M7 的写入口）。
9. 抓取**来自 feed 内容**的 URL（订阅源、原文链接）前必须过 SSRF 校验（含每次重定向后复检）；仅 `ALLOW_PRIVATE_FETCH=true` 时放行内网地址。AI 的 `base_url` 是用户自己在设置里填的，不做内网拦截（否则本地 Ollama / 局域网网关会被误伤）。

## 5. 代码风格

**TypeScript / React**
- `strict: true`；禁止 `any`（用 `unknown` + 收窄）。
- 组件函数式 + hooks；文件内组件用 `export function`，不用 `default export`（路由懒加载入口除外）。
- 服务端状态一律走 TanStack Query，不自己写 `useEffect` 取数。
- 布尔/可选值显式处理，禁止 `!` 非空断言（除非紧跟长度检查）。
- 文案一律走 `useT()`（`src/lib/i18n/`），**不在组件里硬编码任何语言的字符串**，包括 `aria-label` 与 `title`。新增文案先加 `zh-CN.ts`，`en.ts` 的类型会强制同步。

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

## 11. 路线图状态

`docs/roadmap.md` 里原定的 F1–F7 **已全部实现**，各自成了模块：

| 原编号 | 模块 | 落点 |
|---|---|---|
| F5 全文抽取 | M11 | `services/extract.py` |
| F1 AI 助手 | M12 | `services/ai.py` |
| F7 中英双语 | M13 | `frontend/src/lib/i18n/` |
| F2 集成 | M14 | `services/integrations.py` |
| F3 自动化 | M15 | `services/automation.py` |
| F4 代理 | M16 | `services/proxy.py` |
| F6 媒体缓存 | M17 | `services/media.py` |

`docs/roadmap.md` 里只剩「其他被推迟的工程事项」（Alembic、虚拟滚动、自动已读、Playwright、第三种语言）。
要新增功能，先在那份文档里写清边界、接口与触发条件再动手——不要因为"下个版本可能会用"就提前铺代码。

## 12. 已知限制（不要当 bug 修）

- 正文优先用 feed 自带内容；只有「文章类 + 纯文本短于 `EXTRACT_MIN_CHARS`（默认 200）+ 有原文链接 + 未尝试过」才去原网页抽全文，且每源每轮刷新最多抽 `EXTRACT_MAX_PER_REFRESH` 篇。
- 全文抽取用 readability-lxml，受其 `MIN_LEN` 启发式影响：**条目文字短于 25 字的列表会被整块丢弃**（`tests/test_extract.py` 有两条用例钉住这个行为）。
- 抽取结果里偶尔会残留站点自身的措辞（作者前言、登录/版权字样等），不做进一步清洗——过度过滤会误删正文。
- 抽取失败（含超时）会写 `extracted_at` 且不再重试，避免每轮刷新反复撞同一个坏页面；要强制重试只能删库重建。
- 侧边栏顶部的搜索图标只做**本地过滤**（对已加载的目录名与源名做子串匹配），不发请求、不搜文章正文。
- 外链图片可能因防盗链加载失败，以占位图兜底。
- AI：`api_key` 明文存 SQLite（本地单实例、库本身未加密，额外加密只是摆设）；**流式输出**（SSE，`POST /api/ai/generate/stream`，`/api/ai/generate` 保留为一次性 JSON 给脚本用）；上游失败不写 `ai_results`，也不写半成品；上游未返回 usage 时 token 记 0。
- AI：按 `position` 依次尝试所有**启用**的供应商，每家用尽 2 次尝试（退避 `AI_RETRY_BACKOFF_SECONDS`）；可重试的是 429 / 5xx / 网络 / 超时，4xx（除 429）不重试；**只有本次请求还没吐出任何字符时**才重试/切换（已流出的字接不上另一家的输出），全失败才报错。
- AI：与源、条目类型无关 —— 只要有一条启用的供应商，任何 `article` 条目都能总结／翻译；一条都没有时顶栏两个按钮保持灰色外观但可点，直接跳到「设置 → AI」。
- 界面语言只有 `zh-CN` / `en` 两种；不引入 i18n 库（几百条文案用不上 ICU 复数规则），日期与数字走 `Intl`。
- 语言来源：登录前用 localStorage / 浏览器语言，登录后以 `user_settings.language` 为准；切换语言时 `document.documentElement.lang` 同步更新。
- AI 输出语言跟随界面语言（`services/ai.py` 的 `_PROMPTS`）；已缓存的总结不会因为切语言而重新生成，要换语言得清掉 `ai_results` 对应行。
- 代理是**实例级**配置（`proxy_config` 单行）：feed/article 全库共享，同一 URL 只抓一次，"每用户不同代理"在模型上就不成立。
- 代理的 `NO_PROXY` 支持精确域名、`.suffix` / `*.suffix`、CIDR；CIDR 靠抓取时解析到的 IP 判断。
- 自动化只在**刷新**触发，且只处理本次新增的文章；「添加订阅」不触发（否则加一个源就会瞬间打出一堆推送）。
- 定时规则（`trigger=schedule`）的 `HH:MM` 按**服务器时区**解释。Docker 里容器默认 UTC，必须设 `TZ`（compose 已透传，默认 `Asia/Shanghai`），否则「早上八点」会差好几个小时。
- 推送类动作（飞书 / Obsidian / 自定义接口）每条规则每轮刷新上限 `MAX_PUSH_PER_RUN`（5 条）。集成未配置时记日志跳过，不算命中、不抛错。
- RSSHub 参数分两种用途（`target`）：`query` = 按 `scope`（路由前缀，写库前自动补 `/`）拼进展开后的订阅地址；`env` = RSSHub 自己的 config（它从**进程环境**读，不看 query），只出现在 `GET /api/integrations/rsshub/env-snippet` 生成的 `docker -e` / `.env` 片段里，由用户自己贴到 RSSHub 的启动命令（rss-tool 不碰别人的容器）。`ACCESS_KEY` 一律以 `?key=` 传递。设计稿里「作用范围」写的是服务名（如「知乎 / 微博」），实际语义按路由前缀实现。
- **`/api/integrations/rsshub/env-snippet` 是全项目唯一把集成凭据明文回传的接口**（其余接口只给掩码，`access_key` 与密文参数同理）；密文判定包含 `target='env'` 与名字命中 `token/cookie/secret/key/password/auth` 的参数，在**写库时**归一化（不是只在读时描），否则前端回传的掩码会被当成真值存起来。
- 自定义导出推的是固定 JSON 结构（title/url/author/feed/channel/kind/published_at/summary），不做用户自定义 schema 模板。
- Obsidian / 飞书 / 自定义接口目前只被自动化的动作消费，阅读器里没有单独的「发送到」按钮。
- 媒体缓存只缓存**栅格图**白名单（jpeg/png/gif/webp/avif/bmp），**绝不缓存 SVG**——SVG 能带脚本，从本站源上返回等于开 XSS。类型按魔数判定，不信上游声明的 Content-Type。
- 媒体缓存拉不到图时 302 回原地址（让浏览器自己试），并把失败记一行；`MEDIA_RETRY_HOURS`（默认 6）内不再重试，否则一屏几十张坏图会在每次刷新页面时把上游打一遍。
- 取图会带 `Referer: <图片自身 origin>`：大量 CDN（含少数派的 cdnfile）靠它做防盗链，不带就是 403，这是 F6 生效的前提。
- 缓存按总字节预算（`MEDIA_CACHE_MAX_MB`，默认 512）做 LRU 淘汰，且**保护刚写入的那一条**——预算比单张图还小时，刚取到的图也必须能正常返回，而不是紧接着 302。淘汰是惰性的（只在写入时触发），调小预算要到下次写入才收敛。
- 失败行字节数为 0，不参与淘汰；**代理配置变更时会清掉失败记录**，否则用户改完代理还要白等一个重试窗口。
- 正文里的 `<img>` 会先按文章原文地址绝对化，再改写为 `/api/media?url=...`；`srcset` 被移出白名单（会绕过缓存直连原站，在防盗链的源上必坏）。
- 单实例、无迁移、无密码找回、无登录限流。
