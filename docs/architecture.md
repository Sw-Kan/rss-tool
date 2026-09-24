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

## 阅读状态

`user_item_state` 是 `(user_id, article_id)` 的稀疏表：没行 = 未读未收藏。列表查询 left join 后归一为 `is_read/is_favorite` 布尔值返回。

## 前端路由契约

只有一个受保护路由 `/reader`，视图状态全部放在查询串里（便于分享与前进后退）：

```
/reader?kind=<article|picture|video>&fav=1&folder=<id|ungrouped>&feed=<id>&state=<unread|read>&item=<articleId>&settings=<tab>
```

- 各维度 **AND 组合**，空值省略；`folder=ungrouped` 映射为后端的 `folder_id=none`。
- 一级入口是快捷预设：`all`(无 kind) / `essays`(kind=article) / `pictures`(kind=picture) / `videos`(kind=video) / `favorites`(fav=1)。切换一级入口会保留已选目录、清除已选源与当前文章。
- 形态选择：`kind` 为 picture → 瀑布流，video → 网格，其余（含 all / favorites / 混合目录）→ 左列表右正文。
- 设置弹窗用 `settings=<tab>` 深链，不单独建路由。

纯函数在 `frontend/src/lib/scope.ts`，有对应单测。

## 模块索引

MVP：M0 基础设施 · M1 认证 · M2 订阅管理 · M3 抓取管线 · M4 内容导航 · M5 阅读器 · M6 媒体布局 · M7 阅读状态 · M8 设置 · M9 个人资料 · M10 数据导出 · M11 全文抽取。

后续（不实现，见 `docs/roadmap.md`）：F1 AI · F2 集成 · F3 自动化 · F4 代理 · F6 媒体缓存 · F7 i18n。
