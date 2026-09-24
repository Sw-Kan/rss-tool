# 路线图

本阶段（MVP）见 `AGENTS.md`。以下为**已划边界但未实现**的模块。

原则：不建表、不写实现。项目无迁移机制，提前建表没有价值；预留只体现在「路由前缀 + 设置 tab 占位 + 本文档 + `.env.example` 注释变量名」。
本阶段 UI **不提供不可用的假入口**：设置弹窗内四个 tab 统一渲染「后续版本支持」占位。

做完一个就把对应小节从本文档移到 `AGENTS.md` 的模块表，并同步 `docs/api.md`、`docs/data-model.md`。

---

## F1 AI 助手

**能力**：文章摘要、标题翻译；多供应商（OpenAI 兼容 / Anthropic / 本地 Ollama）；token 用量统计与月度上限。

**接口占位**：`GET/PUT /api/ai/config`、`POST /api/ai/summarize`、`POST /api/ai/translate`、`GET /api/ai/usage`

**数据预留**：`ai_configs(user_id, provider, base_url, api_key, model, token_limit)`、`ai_usages(user_id, article_id, kind, tokens_in, tokens_out, created_at)`

**依赖**：抓取管线（正文）、阅读器（渲染位）、设置（配置 tab）

**触发条件**：需要摘要或翻译时。此时才在正文区顶部渲染 AI 区块（设计稿已给出位置与样式）。

**已知设计点**：api_key 存本地明文还是加密，实现前需定；token 上限超限时的行为（拒绝 / 降级）需定。

---

## F2 集成

**能力**：自建 RSSHub（url:port + env 参数）、Obsidian（导出到本地 vault 路径）、飞书群 webhook 推送、custom export（自定义 URL + schema 模板）。

**接口占位**：`/api/integrations/{rsshub|obsidian|feishu|custom}`

**数据预留**：`integrations(user_id, kind, config_json, enabled)`

**依赖**：抓取管线、设置

**触发条件**：用户提出具体集成目标时，一次只做一个 kind。

**已知设计点**：Obsidian 需要写本地文件系统路径，与"浏览器应用"的边界要定（后端代理写文件 vs 用户手动下载）。

---

## F3 自动化规则

**能力**：`当 → 如果 → 则` 规则链，可添加多条并排序。例：当新文章入库 / 如果标题含 "Rust" / 则标记收藏并推送飞书。

**接口占位**：`/api/automation/rules`（CRUD + 排序）

**数据预留**：`automation_rules(user_id, enabled, trigger, conditions_json, actions_json, position)`

**依赖**：抓取管线（触发点）、阅读状态（动作）、F2（推送动作）

**触发条件**：出现"新文章自动打标/推送"需求时。

**已知设计点**：condition 表达式的能力边界（是否允许正则）、动作失败是否重试。

---

## F4 代理配置

**能力**：默认 / 本地 http / https / no_proxy，支持自定义 `ip:port`。

**接口占位**：`GET/PUT /api/proxy/config`、`POST /api/proxy/test`

**数据预留**：`proxy_configs(user_id, mode, http_url, https_url, no_proxy)`

**依赖**：抓取管线（httpx client 构造处）

**触发条件**：抓取受限源时。

**已知设计点**：SOCKS5 是否支持；代理与 SSRF 校验的先后顺序（先解析再走代理）。

---

## F5 全文抽取

**能力**：feed 只给摘要或正文过短时，抓原网页抽取全文。

**接口**：无新端点，改造抓取管线（新增 `services/extract.py`）

**数据预留**：`articles.content_source`(`feed`|`extracted`)、`articles.extract_status`

**依赖**：抓取管线

**触发条件**：出现大量只有摘要的源时。届时评估 trafilatura，并明确失败回退策略与超时预算。

---

## F6 媒体缓存

**能力**：图片经后端代理与本地缓存，解决防盗链与外链失效。

**接口占位**：`GET /api/media/{hash}`

**数据预留**：`media_cache(hash, url, path, bytes, fetched_at)`

**依赖**：抓取管线、媒体布局

**触发条件**：图片大面积加载失败时。需要定缓存上限与淘汰策略（否则磁盘会无限增长）。

---

## F7 多语言 i18n

**能力**：中文 / English 切换。

**接口**：无新端点，`user_settings.language` 解除只读

**数据预留**：无

**依赖**：全部 UI 模块

**触发条件**：需要英文界面时。当前文案已集中在 `src/lib/strings.ts`，届时按命名空间拆分为 `src/lib/i18n/{zh-CN,en}.ts` 即可。

---

## 其他被推迟的工程事项

| 事项 | 推迟理由 | 何时做 |
|---|---|---|
| Alembic 迁移 | 单用户本地实例，删库成本为零 | 出现真实数据不可重建的场景时 |
| 列表虚拟滚动 | 游标分页已够用 | 单列表超过 2000 条并感知卡顿时 |
| 自动标记已读 | 产品未定 | 用户明确要求时（当前为进入正文后手动标记） |
| Playwright 端到端 | pytest + vitest 已覆盖主要逻辑 | 手工验收清单执行成本变高时 |
| 密码找回 / 邮箱验证 | 本地单实例，邮箱仅作身份标识 | 不计划 |
| 多设备同步 | 与"数据存本地"的定位冲突 | 不计划 |
