# 数据模型

SQLite，`backend/data/rss.db`。启动时 `create_all`，**无迁移**：表结构变更直接删库重建（见 `AGENTS.md` §11）。

`feeds` / `articles` 全局共享；`subscriptions` + `user_item_state` 承载用户维度。

## users — M1

| 字段 | 类型 | 说明 |
|---|---|---|
| id | UUID pk | |
| username | str(60) | |
| email | str(255) unique | 小写归一，身份标识，不可改 |
| password_hash | str | bcrypt；跳过登录的默认用户为不可登录的随机值 |
| avatar_type | str(10) | `letter` \| `image`，默认 `letter` |
| avatar_color | str(9) | 字母头像背景色，默认 `#4F46E5` |
| avatar_path | str | 图片头像相对 `data/uploads/` 的文件名，可空 |
| created_at | datetime | |

默认用户：email `skip@local`（前端展示为 `example@example.com`），username `user`。

## folders — M2

| 字段 | 说明 |
|---|---|
| id, user_id | |
| name | unique(user_id, name) |
| position | 排序，新建追加到末尾 |
| created_at | |

**收藏不是行**：它是虚拟目录，由 `user_item_state.is_favorite` 派生。

## feeds — M2 / M3

| 字段 | 说明 |
|---|---|
| id, url(unique) | url 为 feed 地址 |
| site_url, title, description, icon_url | 来自 feed 元数据，可空 |
| etag, modified | 条件请求用（M3 写） |
| last_fetched_at, last_status, last_error | `last_status` ∈ `ok`/`not_modified`/`error`（M3 写） |
| created_at | |

## subscriptions — M2

| 字段 | 说明 |
|---|---|
| id, user_id, feed_id | unique(user_id, feed_id) |
| folder_id | 可空 = 未分组 |
| custom_title | 覆盖 feed.title |
| position | |

## articles — M3

| 字段 | 说明 |
|---|---|
| id, feed_id | |
| guid | unique(feed_id, guid)。guid 缺失时回退 `link`，再回退 `sha1(title + published)` |
| url, title, author | |
| channel_name | 视频频道名；空时前端回退 feed 标题 |
| summary_html, content_html | feed 自带内容，未清洗（渲染前由前端清洗） |
| published_at, updated_at | 排序依据 |
| kind | `article` \| `picture` \| `video` |
| image_url, image_width, image_height | 瀑布流用；尺寸可能为空 |
| video_url | |
| word_count | 中文字符数 + 非中文词数 |
| content_source | `feed` \| `extracted`，默认 `feed`（F5 写） |
| extract_status | `null`（未尝试）\| `ok` \| `failed`（F5 写） |
| extracted_at | 首次（且唯一一次）尝试抽取的时间；非空即不再重试（F5 写） |
| fetched_at | |

索引：`(feed_id, published_at DESC, id)`、`(kind)`。

## user_item_state — M7

| 字段 | 说明 |
|---|---|
| id, user_id, article_id | unique(user_id, article_id) |
| is_read | |
| is_favorite | |
| read_at | 首次标记已读的时间 |

索引：`(user_id, is_read)`、`(user_id, is_favorite)`。稀疏表：无行 = 未读未收藏。

## user_settings — M8

| 字段 | 默认 | 说明 |
|---|---|---|
| user_id | | unique |
| theme | `light` | `light` \| `dark` |
| language | `zh-CN` | `zh-CN` \| `en`，可写；同时决定 AI 输出语言 |
| auto_refresh_enabled | `true` | |
| refresh_interval_minutes | `60` | 允许 5–1440 |
| text_style | `comfortable` | `small` \| `comfortable` \| `large` |
| ai_token_limit | `0` | 每月 AI token 上限，0 = 不限 |

## ai_providers — M12

| 字段 | 说明 |
|---|---|
| id, user_id, label, position | |
| protocol | `openai` \| `anthropic`，由预设决定，UI 不暴露 |
| base_url, model | |
| api_key | 明文；**永不回传**，接口只给掩码。空值 = 不发鉴权头（本地 Ollama） |
| enabled | 多个开启时按 `position` 取第一个 |

## ai_results — M12

| 字段 | 说明 |
|---|---|
| id, user_id, article_id | unique(user_id, article_id, kind) |
| kind | `summary` \| `title_translation` |
| model, content | |
| tokens_in, tokens_out | 上游未返回 usage 时为 0 |
| created_at | 用量按月聚合的依据 |

索引：`(user_id, created_at)`。这张表既是结果缓存（命中即不再调上游），也是用量账本。

## 后续模块的表设计（**本阶段尚未实现**）

记录下来只为划定边界。项目无迁移机制，提前建表没有价值；真正实现时再加。

- F1 AI：已实现，见上方 `ai_providers` / `ai_results`。
- F2 集成：`integrations(user_id, kind, config_json, enabled)`，kind ∈ `rsshub`/`obsidian`/`feishu`/`custom`
- F3 自动化：`automation_rules(user_id, enabled, trigger, conditions_json, actions_json, position)`
- F4 代理：`proxy_configs(user_id, mode, http_url, https_url, no_proxy)`
- F5 全文抽取：已实现，见 `docs/architecture.md`。
- F6 媒体缓存：`media_cache(hash, url, path, bytes, fetched_at)`
- F7 i18n：已实现，无新表，见 `user_settings.language`。
