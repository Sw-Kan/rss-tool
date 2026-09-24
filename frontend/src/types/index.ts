/** 与 backend/app/schemas.py 一一对应，两侧必须同步。 */

export type ItemKind = 'article' | 'picture' | 'video';
export type AvatarType = 'letter' | 'image';
export type Theme = 'light' | 'dark';
export type TextStyle = 'small' | 'comfortable' | 'large';
export type ReadState = 'all' | 'unread' | 'read';

export interface User {
  id: string;
  username: string;
  email: string;
  avatar_type: AvatarType;
  avatar_color: string;
  avatar_url: string | null;
}

export interface Folder {
  id: string;
  name: string;
  position: number;
  feed_count: number;
  unread_count: number;
}

export interface FolderList {
  items: Folder[];
  ungrouped: { feed_count: number; unread_count: number };
}

export interface Feed {
  id: string;
  url: string;
  site_url: string | null;
  title: string;
  description: string | null;
  icon_url: string | null;
  folder_id: string | null;
  custom_title: string | null;
  unread_count: number;
  last_status: string;
  last_error: string | null;
  last_fetched_at: string | null;
}

export interface RefreshResult {
  feed_id: string;
  new_count: number;
  status: string;
  error: string | null;
}

export interface OpmlImportResult {
  imported: number;
  skipped: number;
  errors: string[];
}

export interface Item {
  id: string;
  feed_id: string;
  feed_title: string;
  feed_icon_url: string | null;
  title: string;
  author: string | null;
  url: string | null;
  published_at: string;
  kind: ItemKind;
  image_url: string | null;
  image_width: number | null;
  image_height: number | null;
  video_url: string | null;
  channel_name: string | null;
  is_read: boolean;
  is_favorite: boolean;
}

export interface ItemDetail extends Item {
  content_html: string;
  summary_html: string | null;
  word_count: number;
}

export interface ItemPage {
  items: Item[];
  next_cursor: string | null;
}

export interface ItemContext {
  prev_id: string | null;
  next_id: string | null;
  index: number;
  total: number;
}

export interface SidebarSummary {
  by_kind: Record<string, number>;
  favorites: number;
  folders: Record<string, number>;
  feeds: Record<string, number>;
  ungrouped: number;
  total_unread: number;
  feed_count: number;
}

export interface AppSettings {
  theme: Theme;
  language: string;
  auto_refresh_enabled: boolean;
  refresh_interval_minutes: number;
  text_style: TextStyle;
  /** 每月 AI token 上限，0 = 不限 */
  ai_token_limit: number;
}

export interface UserExport {
  schema_version: number;
  exported_at: string;
  user: User;
  settings: AppSettings | null;
  folders: { id: string; name: string; position: number }[];
  subscriptions: {
    feed_url: string;
    feed_title: string | null;
    site_url: string | null;
    folder: string | null;
    custom_title: string | null;
    position: number;
  }[];
  item_states: {
    article_id: string;
    article_title: string;
    article_url: string | null;
    is_read: boolean;
    is_favorite: boolean;
    read_at: string | null;
  }[];
}

/** 侧边栏一级过滤的快捷入口 */
export type NavKey = 'all' | 'essays' | 'pictures' | 'videos' | 'favorites';

/**
 * 阅读器视图状态：与 `GET /api/items` 的查询参数一一对应，各维度 AND 组合。
 * 放在 URL 查询串里（`/reader?kind=&fav=&folder=&feed=&state=&item=`），便于分享与前进后退。
 */
export interface ReaderSearch {
  kind: ItemKind | null;
  fav: boolean;
  folder: string | null;
  feed: string | null;
  state: ReadState;
  item: string | null;
}

/* ---------- F1 AI ---------- */

export type AiProtocol = 'openai' | 'anthropic';
export type AiKind = 'summary' | 'title_translation';

export interface AiProvider {
  id: string;
  label: string;
  /** 报文协议，由预设决定，UI 不暴露 */
  protocol: AiProtocol;
  base_url: string;
  model: string;
  enabled: boolean;
  position: number;
  has_key: boolean;
  /** 掩码提示，例如 sk-••••••••4f2a；明文永不回传 */
  api_key_hint: string;
}

export interface AiConfig {
  providers: AiProvider[];
  token_limit: number;
}

export interface AiPreset {
  key: string;
  label: string;
  base_url: string;
  model: string;
}

export interface AiUsage {
  month_tokens: number;
  total_tokens: number;
  limit: number;
  calls: number;
  by_kind: Record<string, number>;
}

export interface AiResult {
  kind: AiKind;
  content: string;
  model: string;
  cached: boolean;
  tokens_in: number;
  tokens_out: number;
  created_at: string;
}

export interface AiResults {
  summary: AiResult | null;
  title_translation: AiResult | null;
}

/* ---------- F2 / F3 / F4 ---------- */

export type IntegrationKind = 'rsshub' | 'obsidian' | 'feishu' | 'custom_export';

export interface RsshubParam {
  name: string;
  scope: string;
  value: string;
  secret: boolean;
}

export interface RsshubConfig {
  base_url: string;
  access_key: string;
  env: string;
  params: RsshubParam[];
}

export interface Integration {
  kind: IntegrationKind;
  enabled: boolean;
  updated_at: string | null;
  rsshub?: RsshubConfig;
  obsidian?: { vault_path: string };
  feishu?: { webhook_url: string };
  custom_export?: { endpoint: string };
}

export interface IntegrationTest {
  ok: boolean;
  message: string;
  latency_ms: number | null;
}

export type ProxyMode = 'system' | 'http' | 'https' | 'custom';

export interface ProxyConfig {
  mode: ProxyMode;
  url: string;
  no_proxy: string;
}

export type RuleTrigger = 'item_arrived' | 'video_arrived' | 'picture_arrived';
export type RuleField = 'title' | 'word_count' | 'channel' | 'feed' | 'kind';
export type RuleOp = 'contains' | 'gt' | 'lt' | 'eq';
export type RuleActionType =
  | 'favorite'
  | 'mark_read'
  | 'mark_unread'
  | 'feishu'
  | 'obsidian'
  | 'custom_export';

export interface RuleCondition {
  field: RuleField;
  op: RuleOp;
  value: string;
}

export interface Rule {
  id: string;
  name: string;
  enabled: boolean;
  position: number;
  trigger: RuleTrigger;
  condition: RuleCondition;
  action: { type: RuleActionType };
}
