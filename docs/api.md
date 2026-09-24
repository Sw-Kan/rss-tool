# API

统一前缀 `/api`。除 `/api/auth/*` 与 `/api/health` 外均需 cookie `rss_token`。

**错误**：`{"detail": "..."}`；未登录 `401 {"detail":"unauthorized"}`；校验失败走 FastAPI 默认 422。

**分页**：列表接口 `cursor`（不透明串）+ `limit`（默认 30，上限 100）。响应 `{"items": [...], "next_cursor": string|null}`。游标基于 `(published_at, id)` 倒序。

## 健康

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | `{"status":"ok"}` |

## 认证 — M1

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| POST | `/api/auth/register` | `{username, email, password}` | 201 `UserOut` + 种 cookie |
| POST | `/api/auth/login` | `{email, password}` | 200 `UserOut` |
| POST | `/api/auth/skip` | — | 200 `UserOut`（幂等，复用默认 user） |
| POST | `/api/auth/logout` | — | 204，清 cookie |
| GET | `/api/auth/me` | — | `UserOut` |

密码 ≥ 8 位。email 小写归一后判重，重复返回 409。

```ts
type UserOut = { id: string; username: string; email: string;
                 avatar_type: 'letter'|'image'; avatar_color: string; avatar_url: string | null }
```

## 用户与资料 — M9 / M10

| 方法 | 路径 | 请求 | 响应 |
|---|---|---|---|
| PATCH | `/api/users/me` | `{username?, avatar_type?, avatar_color?}` | `UserOut` |
| POST | `/api/users/me/avatar` | multipart `file`（≤3MB，png/jpg） | `UserOut` |
| DELETE | `/api/users/me/avatar` | — | `UserOut`（切回字母头像） |
| GET | `/api/users/me/export` | — | JSON 附件 |
| GET | `/api/users/avatar/{filename}` | — | 头像文件（仅允许读取属于某个用户的文件名） |
| DELETE | `/api/data` | — | 204，清空本机全部数据（单实例级，见下） |

导出结构：`{schema_version, exported_at, user, settings, folders, subscriptions, item_states}`，不含 `password_hash`。

`DELETE /api/data` 是设计稿「清空本地数据」的落地：删除本机全部订阅、文章、阅读记录、上传的头像与账号（保留数据库文件本身），调用方需自行跳回登录页。

## 目录 — M2

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/folders` | `{items: [{id, name, position, feed_count, unread_count}], ungrouped: {feed_count, unread_count}}` |
| POST | `/api/folders` | `{name}` → 201 |
| PATCH | `/api/folders/{id}` | `{name}` |
| DELETE | `/api/folders/{id}` | 204；源回落未分组，不删源 |

## 订阅源 — M2

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/feeds?folder_id=` | `folder_id=none` 取未分组。`{items: FeedOut[]}` |
| POST | `/api/feeds` | `{url, folder_id?, title?}`；先抓取校验再入库，失败 400 |
| PATCH | `/api/feeds/{id}` | `{title?, folder_id?}`（folder_id 传 null 移到未分组） |
| DELETE | `/api/feeds/{id}` | 204；删订阅，feed 无其它订阅时级联删文章 |
| POST | `/api/feeds/{id}/refresh` | `{new_count, status, error?}` |
| POST | `/api/feeds/refresh?folder_id=` | 批量，最多 5 并发 → `{results: [...]}` |

```ts
type FeedOut = { id, url, site_url, title, description, icon_url,
                 folder_id: string | null, custom_title: string | null,
                 unread_count: number, last_status: string, last_error: string | null,
                 last_fetched_at: string | null }
```

## OPML — M2

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/opml/export` | `text/x-opml` 附件 `rss-tool.opml` |
| POST | `/api/opml/import` | multipart `file` → `{imported, skipped, errors: string[]}`，保留嵌套 outline 目录 |

## 文章与阅读状态 — M5 / M7

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/items/summary` | 侧边栏计数一次拿齐，避免前端发 N 个请求 |
| GET | `/api/items` | 查询参数见下，`{items: ItemOut[], next_cursor}` |
| GET | `/api/items/{id}` | `ItemDetailOut` |
| GET | `/api/items/{id}/context` | 同过滤条件的 `{prev_id, next_id, index, total}` |
| PATCH | `/api/items/{id}/state` | `{is_read?, is_favorite?}` → `ItemOut` |
| POST | `/api/items/read` | `{ids: string[], is_read: bool}` → `{updated: number}` |

`GET /api/items` 查询参数（全部可选，**AND** 组合）：

| 参数 | 取值 | 说明 |
|---|---|---|
| `kind` | `article`\|`picture`\|`video` | 一级过滤；省略 = 全部类型 |
| `folder_id` | uuid \| `none` | 二级过滤（目录） |
| `feed_id` | uuid | 三级过滤（单源） |
| `favorite` | `true` | 只出收藏 |
| `state` | `all`(默认)\|`unread`\|`read` | |
| `cursor`, `limit` | | |

```ts
type ItemOut = { id, feed_id, feed_title, feed_icon_url, title, author, url,
                 published_at, kind, image_url, image_width, image_height,
                 video_url, channel_name, is_read, is_favorite }
type ItemDetailOut = ItemOut & { content_html: string; summary_html: string | null; word_count: number }
```

`GET /api/items/summary` 的响应（`by_kind` 的 key 为 `all`/`article`/`picture`/`video`，`folders`/`feeds` 是 id → 未读数）：

```ts
type SidebarSummaryOut = { by_kind: Record<string, number>; favorites: number;
                           folders: Record<string, number>; feeds: Record<string, number>;
                           ungrouped: number; total_unread: number; feed_count: number }
```

计数统一是**未读**口径（与设计稿一致）。

## 设置 — M8

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/settings` | `SettingsOut` |
| PATCH | `/api/settings` | `{theme?, auto_refresh_enabled?, refresh_interval_minutes?, text_style?}` |

```ts
type SettingsOut = { theme: 'light'|'dark'; language: 'zh-CN';
                     auto_refresh_enabled: boolean; refresh_interval_minutes: number;
                     text_style: 'small'|'comfortable'|'large' }
```

`refresh_interval_minutes` 允许 5–1440，越界 422。改动后调度器立即重排。

## 后续模块预留（本阶段不挂载）

`/api/ai/*`（F1）、`/api/integrations/*`（F2）、`/api/automation/*`（F3）、`/api/proxy/*`（F4）、`/api/media/*`（F6）。见 `docs/roadmap.md`。
