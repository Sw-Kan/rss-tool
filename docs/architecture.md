# 架构

## 进程拓扑

```
浏览器 (React SPA, :5173)
   │  /api/*  (Vite dev proxy → :8000，生产由 nginx 代理)
   ▼
FastAPI (:8000, 单进程)
   ├── SQLite  backend/data/rss.db
   ├── 上传目录 backend/data/uploads/
   └── APScheduler (AsyncIOScheduler，同事件循环内)
   ▼
外部：用户的 RSS 源 / RSSHub / 视频封面图
```

单用户单实例，无缓存层、无队列、无反向代理之外的中间件。

## 分层

| 层 | 位置 | 职责 | 约束 |
|---|---|---|---|
| 路由 | `app/routers/` | 参数校验、鉴权、编排 | 不写业务逻辑 |
| 服务 | `app/services/` | 抓取、解析、分类、OPML、导出 | 不 import FastAPI |
| 数据 | `app/models.py` + `app/db.py` | 表结构与会话 | 无业务规则 |
| 契约 | `app/schemas.py` | Pydantic 请求/响应 | 唯一 DTO 来源 |

前端对应：`src/api/` 是唯一取数出口，`src/lib/` 是纯函数，`src/features/` 是页面级组合。

## 请求流

1. 浏览器带 `rss_token` cookie → `deps.current_user` 解出 `User`。
2. 路由按功能域查/写自己的表；用户维度过滤一律靠 `user_id`。
3. 列表接口 keyset 分页：游标是 `(published_at, id)` 的 base64 编码。
4. 写操作完成后前端 invalidate：`items` 列表、`folders`（含计数）、受影响的 `item` 详情。

## 抓取管线

```
触发点：POST /api/feeds/{id}/refresh  |  POST /api/feeds/refresh?folder_id=
        APScheduler 定时 job
   ▼
refresh.refresh_feed(feed)
   ├─ asyncio.Lock per feed.url     (同一源不并发)
   ├─ feed_fetch.fetch()            httpx + 条件请求(ETag/Last-Modified) + SSRF 校验
   ├─ feed_parse.parse()            feedparser → ParsedFeed / ParsedEntry
   ├─ classify.entry()              kind / image_url / video_url / image_size
   ├─ upsert articles               按 (feed_id, guid) 去重，只更新内容字段
   └─ extract.extract_pending()     feed 正文过短的文章去原网页抽全文
```

### 全文抽取（F5）

只在刷新时触发，不在「添加订阅」时触发（否则新增一个源会立刻打十几个网页，接口延迟不可控）。

```
候选 = 该源最近 200 篇里满足全部条件的前 N 篇（N = EXTRACT_MAX_PER_REFRESH，默认 10）
        kind == 'article'               图片/视频不需要全文
        content_source == 'feed'       已抽取的不重复抽
        extracted_at is null           失败过的不重试
        url 是 http(s)
        feed 正文纯文本 < EXTRACT_MIN_CHARS（默认 200）
   ▼
feed_fetch.fetch(url, accept=text/html)     复用抓取那套：SSRF 校验 + 重定向复检 + 超时 + 体积上限
   ▼
readability-lxml 抽正文容器                 选它而非 trafilatura：需要保留 a/img/h1-h6/ul 结构，
                                            供前端白名单渲染；trafilatura 会压成单个 <p>
   ├─ 剔除 nav/aside/footer/header/form/script/style/iframe/noscript/svg/button
   ├─ 结果纯文本 < EXTRACT_MIN_CHARS → failed，保留 feed 内容
   └─ 否则替换 content_html、重算 word_count、content_source='extracted'
```

关键性质：

- **写权限隔离**：管线只写 `articles` 与 `feeds` 的抓取元数据，永不触碰 `user_item_state`。所以重复刷新不会丢已读/收藏。
- **抽取不反向覆盖**：`content_source == 'extracted'` 时抓取管线不写 `content_html`/`word_count`，否则下一轮刷新就会把全文换回短摘要。
- **失败隔离**：单源失败写 `feeds.last_status/last_error`，不影响其它源；目录刷新用 `asyncio.gather` 限流 5。抽取失败只标 `extract_status`，不影响刷新返回值。
- **共享**：`feeds`/`articles` 与用户无关，同一 URL 全库只抓一次，`subscriptions` 决定谁看得见。

## AI 助手（F1）

```
前端：设置 → AI                          前端：阅读器顶栏「AI 总结」「标题翻译」
  GET/POST/PATCH/DELETE /api/ai/providers     POST /api/ai/generate/stream?kind=…  (SSE，前端用)
  PATCH /api/settings {ai_token_limit}        POST /api/ai/generate?kind=…         (一次性 JSON，脚本用)
  GET /api/ai/usage                           GET  /api/ai/results?article_id=     (打开文章回填)
                                              ▼
                                     ai.prepare()  预检：命中缓存 / 上限 / 有没有供应商
                                       ├─ 命中 ai_results → done(cached)
                                       ├─ 本月用量 >= 上限 → 429（响应开始前，还来得及用状态码）
                                       └─ enabled_providers()  按 position 全部取出
                                              ▼
                                     ai.generate()  逐家尝试，每家最多 2 次
                                       ├─ meta   → 开始一次尝试（provider/model/attempt）
                                       ├─ delta  → 上游 stream:true 的文本增量
                                       ├─ done   → 写 ai_results（缓存兼账本）
                                       └─ error  → 全失败 / 中途断流
```

两套报文（都带 `stream: true`）：`openai`（`{base_url}/chat/completions` + Bearer，额外带 `stream_options.include_usage`）与 `anthropic`（`{base_url}/messages` + `x-api-key`）。
协议藏在 `ai_providers.protocol` 里由预设决定，UI 不暴露——需要别的协议就用「自定义」预设。

关键性质：

- **流式**：上游 `stream: true`，逐块转成 SSE 发给前端；前端把增量写进 `aiResults` 这份 query 缓存，所以 `ArticlePane` 不需要知道自己在看的是流式的一半还是最终结果。生产是 nginx 反代，响应头必须带 `X-Accel-Buffering: no`，否则会被缓冲到流结束才吐出来。
- **慢但一直在吐字不会被判超时**：httpx 在流式下是分块读超时（`AI_TIMEOUT_SECONDS`），只有完全卡住才算超时。
- **重试与切换**：可重试的是 429 / 5xx / 网络 / 超时；4xx（除 429）不重试（配置或上游本身的毛病，重试无意义）。按 `position` 依次尝试所有启用的供应商，每家用尽 `ATTEMPTS_PER_PROVIDER`（2）次，中间退避 `AI_RETRY_BACKOFF_SECONDS`。上游 200 却一句话都不给时也换下一家。
- **已吐字就不再重试/切换**：流出去的字收不回来，接上另一家的输出会拼出两段内容。此时报「已生成的内容未保存」。

- `api_key` 明文落库（本地单实例、库未加密，再包一层是摆设），但**永不回传**，接口只给 `sk-••••••••cdef` 掩码；空 key 时干脆不发鉴权头（本地 Ollama 的用法）。
- 上游失败**不写** `ai_results`（也不写半成品），所以用户修好配置后可以直接重试；成功则永久缓存，重复点击不重复计费。
- `ai_results` 同时是缓存与用量账本，`/api/ai/usage` 直接按月聚合这张表，不另开计数表。
- AI 的 `base_url` 是用户自己填的配置，**不做内网拦截**；这与 feed 侧 URL 必须过 SSRF 校验是两回事。
- 前端门闩 `aiReady` 只看「有没有一条 `enabled` 的供应商」，与源、条目类型无关：一条都没有时顶栏两个按钮保持灰色外观但**可点**，点一下走 `settings=ai` 深链直接打开「设置 → AI」（`disabled` 元素不派发鼠标事件，原生 `title` 就不会显示，所以这里不能用 `disabled`）。
- 条目类型决定按钮**是否出现**：只有 `article` 有 AI（`pages.md` 明确 video/picture 不需要）。

## 国际化（F7）

```
src/lib/i18n/zh-CN.ts   中文包（源语言，`Strings` 类型的来源）
src/lib/i18n/en.ts      English bundle，类型是 `Strings` → 漏翻一个 key 就编译不过
src/lib/i18n/index.tsx  LOCALES / detectLocale / bundles / I18nProvider / useT
```

- 组件只调 `useT()` 拿文案，调 `useI18n().locale` 拿语言（给 `Intl` 与格式化用）。
- 语言来源：登录前 localStorage → 浏览器语言 → `zh-CN`；登录后 `AppShell` 用 `user_settings.language` 覆盖。
- 日期/数字/阅读速度全走 `Intl`（`lib/format.ts`），不自己拼月份名。
- 没有引入 i18n 库：文案规模用不上 ICU 复数与命名空间加载，`Intl` 已经覆盖了唯一真正需要运行时能力的部分。
- `I18nProvider` 的默认值是中文包，所以单测里不套 Provider 也能渲染。

## 集成 / 自动化 / 代理（F2 / F3 / F4）

```
集成（integrations，按 kind 一行，config 是 JSON）
  rsshub        base_url + access_key + env + params[{name,scope,value,secret,target}]
  obsidian      vault_path
  feishu        webhook_url
  custom_export endpoint

  顶点用法一：POST /api/feeds 收到裸路由（/sspai/matrix）→ expand_route() 拼成完整地址
              并补 ?key=ACCESS_KEY；只有 target='query' 的参数按 scope 前缀拼成 query
              （target='env' 的是 RSSHub 自己的 config，拼进 URL 既没用又会把凭据写进 feeds.url）
  顶点用法二：GET /api/integrations/rsshub/env-snippet 把 target='env' 的参数与「env」
              文本框渲染成 docker -e / .env 两段可复制文本（rss-tool 不碰别人的容器）
  顶点用法三：被自动化的动作消费（推送飞书 / 写入 Obsidian / 推自定义接口）

  参数为什么分两类：PIXIV_REFRESH_TOKEN / GITHUB_ACCESS_TOKEN 这类是 RSSHub 的 config，
  RSSHub 从进程环境读、**不看 query**；而 limit / filter 这种才是路由自己读的 query 参数。
  弄反了就是「配置里填了、实际没生效」——界面上看不出来，所以归纳到两种用途并在 UI 里标明。

代理（proxy_config，实例级单行）
  feed_fetch.fetch() 每跳都用 proxy.build_client(spec, url, addresses) 建客户端
  → system: trust_env=True（环境变量里的代理不可用时降级直连并记警告）
  → http / https: 只代理对应 scheme
  → custom: 全部走该地址（socks5 需要 socksio）
  → no_proxy 命中（域名 / 后缀 / CIDR）则直连

自动化（automation_rules）
  触发点一（新条目）：refresh_feed() 在 upsert + 全文抽取之后
    1. run_for_new_articles(feed_id, 本次新增的 id)
    2. 对每个订阅了该源的用户，按 position 顺序匹配规则（命中后继续匹配后续规则）
    3. 条件 = conditions[] 按 join(and/or) 合并；trigger 先做类型/视频/图片判定
  触发点二（定时）：scheduler 每分钟一个 tick
    1. due_schedule_rules() 找 schedule_time == 当前 HH:MM 且今天没跑过的规则
    2. 只处理 last_run_at 之后入库的文章（默认回看 24 小时），跑完写 last_run_at
  动作：收藏 / 已读 / 未读 → 经 services/item_state.py（M7 写入口）
        推送飞书 / 写入 Obsidian / 推自定义接口 → 经 integrations，受 MAX_PUSH_PER_RUN 限制

  顺序很重要：抽取排在自动化之前，「字数 > N」这类条件才能看到抽取后的字数。
  定时规则的 HH:MM 按服务器时区解释（Docker 要设 TZ，否则默认 UTC）。
```

关键性质：

- **写权限不越界**：自动化改阅读状态走 M7 的写入口，不自己动 `user_item_state`。
- **失败隔离**：集成没配好只记日志跳过，不影响刷新结果，也不影响同批其它规则。
- **幂等**：自动化只对「本次新增」的文章生效，不会在全量重放时把旧文章再标一遍。

## 媒体缓存（F6）

```
前端                                       后端
resolveMediaUrl(src, article.url)          GET /api/media?url=<encoded>
  → /api/media?url=<encoded>                 ├─ lookup()  命中 → 直接回文件
                                             ├─ 冷启动 → fetch_and_store()
                                             │    ├─ feed_fetch.fetch()（SSRF + 重定向复检 + 限长 + 代理）
                                             │    ├─ sniff_content_type()  按魔数判类型
                                             │    ├─ 白名单外 → 记 failed，302 回原地址
                                             │    └─ 落盘 data/media/xx/yy/<sha256>
                                             └─ 取不到 → 302 回原地址（浏览器自己去试）
```

- 缓存键是源 URL 的 sha256，同时是主键与磁盘路径，按两位分片。
- 响应带 `private, max-age=31536000, immutable` + `X-Content-Type-Options: nosniff`。
- **不缓存 SVG**（能带脚本，同源返回等于 XSS），只缓存栅格图白名单。
- 失败也记一行：`MEDIA_RETRY_HOURS` 内不重试，避免反复打上游。
- 取图带 `Referer: <图片自身 origin>` —— 大量 CDN 靠它防盗链，不带就是 403（这是这个功能能生效的前提）。
- 超出 `MEDIA_CACHE_MAX_MB` 按 `last_used_at` 做 LRU 淘汰，但**保护刚写入的那条**；淘汰是惰性的，调小预算要到下次写入才收敛。
- 代理配置变更时清掉失败记录：失败很可能就是代理造成的，留着会让用户觉得"改了没用"。
- 前端覆盖点：`RemoteImage`、`SourceLogo`（源图标同样可能被防盗链）、正文 HTML（在清洗阶段改写）、阅读器的 picture 条目。

## 阅读状态

`user_item_state` 是 `(user_id, article_id)` 的稀疏表：没行 = 未读未收藏。列表查询 left join 后归一为 `is_read/is_favorite` 布尔值返回。

### 生效类型（源级覆盖）

`articles` 是全局共享的，而「这个源算不算图片源」是每个订阅自己的事，所以覆盖值放在
`subscriptions.kind_override`，查询时用 `COALESCE(subscription.kind_override, article.kind)`：

- 过滤：`WHERE COALESCE(...) = :kind`
- 投影：把合并结果作为 `effective_kind` 一起 select 出来，返回给前端的 `kind` 就是它
- 侧边栏计数（`services/counts.py`）用同一个表达式分组，否则数字会和列表对不上
- 全文抽取只在「至少有一个订阅者把这个源当文章看」时才跑（`_anyone_wants_articles`）

### 自定义导出的模板渲染

`{{变量}}` 替换时对值做 JSON 转义（标题里的引号不能把模板搞坏），然后 `json.loads`；
渲染后若还剩 `{{x}}` 就报「不认识的变量」并列出可用变量——比抛 JSON 解析错误清楚得多。

## 前端路由契约

只有一个受保护路由 `/reader`，视图状态全部放在查询串里（便于分享与前进后退）：

```
/reader?kind=<article|picture|video>&fav=1&folder=<id|ungrouped>&feed=<id>&state=<unread|read>&item=<articleId>&settings=<tab>
```

- 维度组合关系是 `kind ⊕ ( folder ⊕ feed | fav ) ⊕ state`：一级类型横向叠加，
  **收藏与目录同级互斥**（点收藏就离开目录，点目录/源就离开收藏）。
  于是「收藏」看到的是当前类型下收藏的内容，不会被目录或单源再筛一遍。
- 一级入口是快捷预设：`all`(无 kind) / `essays`(kind=article) / `pictures`(kind=picture) /
  `videos`(kind=video)。切类型只换 `kind`，二级选择（目录或收藏）原样保留。
- `favorites` 不是一级入口：它切的是二级的 `fav`，点一次进入、再点一次取消，
  进入时清掉 `folder`。高亮上「收藏」与当前类型行会**同时亮着**，因为两者是叠加的。
- `folder=ungrouped` 映射为后端的 `folder_id=none`。
- 互斥这条不变式在 `parseSearch` 里也收口：URL 同时带 `fav` 与 `folder`/`feed` 时**丢掉 `fav`**
  （目录/源优先，与 `ReaderPage` 取标题的优先级一致）。旧书签与改造前的浏览器历史正长这样，
  只靠点按函数保证的话，按一次后退就能重现「目录里的收藏」。
- 形态选择：`kind` 为 picture → 瀑布流，video → 网格，其余（含 all / favorites / 混合目录）→ 左列表右正文。
- 设置弹窗用 `settings=<tab>` 深链，不单独建路由。

纯函数在 `frontend/src/lib/scope.ts`，有对应单测。

## 模块索引

已成模块：M0 基础设施 · M1 认证 · M2 订阅管理 · M3 抓取管线 · M4 内容导航 · M5 阅读器 · M6 媒体布局 · M7 阅读状态 · M8 设置 · M9 个人资料 · M10 数据导出 · M11 全文抽取 · M12 AI 助手 · M13 国际化 · M14 集成 · M15 自动化 · M16 代理 · M17 媒体缓存。

路线图原定的 F1–F7 已全部实现；`docs/roadmap.md` 只剩被推迟的工程事项。
