/** 阅读器视图状态 ↔ URL 查询串 ↔ 后端查询参数。
 *
 *  各维度是 AND 关系（docs/architecture.md 的前端路由契约）：
 *    kind（一级类型） ⊕ folder（二级目录） ⊕ feed（三级单源） ⊕ fav ⊕ state
 */

import type { ItemKind, NavKey, ReaderSearch, ReadState } from '../types';

export const NAV_KINDS: Record<NavKey, ItemKind | null> = {
  all: null,
  essays: 'article',
  pictures: 'picture',
  videos: 'video',
  favorites: null,
};

export const NAV_ORDER: NavKey[] = ['all', 'essays', 'pictures', 'videos', 'favorites'];

const KINDS: ItemKind[] = ['article', 'picture', 'video'];
const STATES: ReadState[] = ['all', 'unread', 'read'];

export const UNGROUPED = 'ungrouped';

export function defaultSearch(): ReaderSearch {
  return { kind: null, fav: false, folder: null, feed: null, state: 'all', item: null };
}

function clean(value: string | null | undefined): string | null {
  const trimmed = (value ?? '').trim();
  return trimmed ? trimmed : null;
}

export function parseSearch(params: URLSearchParams): ReaderSearch {
  const kind = params.get('kind');
  const state = params.get('state');
  return {
    kind: KINDS.includes(kind as ItemKind) ? (kind as ItemKind) : null,
    fav: params.get('fav') === '1',
    folder: clean(params.get('folder')),
    feed: clean(params.get('feed')),
    state: STATES.includes(state as ReadState) ? (state as ReadState) : 'all',
    item: clean(params.get('item')),
  };
}

/** 省略默认值，URL 保持简短；item 参与序列化以便前进后退定位。 */
export function toSearchParams(search: ReaderSearch): URLSearchParams {
  const params = new URLSearchParams();
  if (search.kind) params.set('kind', search.kind);
  if (search.fav) params.set('fav', '1');
  if (search.folder) params.set('folder', search.folder);
  if (search.feed) params.set('feed', search.feed);
  if (search.state !== 'all') params.set('state', search.state);
  if (search.item) params.set('item', search.item);
  return params;
}

/** 点击侧边栏一级入口：只换类型/收藏，保留已选目录；丢弃源与当前文章。 */
export function applyNav(nav: NavKey, current: ReaderSearch): ReaderSearch {
  return {
    ...current,
    kind: NAV_KINDS[nav],
    fav: nav === 'favorites',
    feed: null,
    item: null,
  };
}

/** 点击二级目录（或未分组）：保留类型与收藏，切换目录，丢弃源与文章。 */
export function applyFolder(folderId: string | null, current: ReaderSearch): ReaderSearch {
  return { ...current, folder: folderId, feed: null, item: null };
}

/** 点击三级源：保留上级过滤，切换源，丢弃文章。 */
export function applyFeed(feedId: string | null, current: ReaderSearch): ReaderSearch {
  return { ...current, feed: feedId, item: null };
}

export function applyState(state: ReadState, current: ReaderSearch): ReaderSearch {
  return { ...current, state };
}

export function applyItem(itemId: string | null, current: ReaderSearch): ReaderSearch {
  return { ...current, item: itemId };
}

/** 反推侧边栏当前高亮项。 */
export function activeNav(search: ReaderSearch): NavKey {
  if (search.fav) return 'favorites';
  if (search.kind === 'article') return 'essays';
  if (search.kind === 'picture') return 'pictures';
  if (search.kind === 'video') return 'videos';
  return 'all';
}

/** 页面标题（设计稿顶部左侧的大字）。 */
export function viewTitle(search: ReaderSearch, folderName: string | null): string {
  if (search.folder) return folderName ?? '目录';
  return { all: '全部', essays: '文章', pictures: '图片', videos: '视频', favorites: '收藏' }[
    activeNav(search)
  ];
}

export function isSameSearch(a: ReaderSearch, b: ReaderSearch): boolean {
  return toSearchParams(a).toString() === toSearchParams(b).toString();
}

/** 转成 GET /api/items 的参数；空维度不发送。 */
export function apiParams(search: ReaderSearch): Record<string, string> {
  const params: Record<string, string> = {};
  if (search.kind) params.kind = search.kind;
  if (search.fav) params.favorite = 'true';
  if (search.feed) params.feed_id = search.feed;
  if (search.folder) params.folder_id = search.folder === UNGROUPED ? 'none' : search.folder;
  if (search.state !== 'all') params.state = search.state;
  return params;
}

/** 列表接口的稳定缓存键（顺序固定）。 */
export function queryKeyFor(search: ReaderSearch): string {
  return new URLSearchParams(apiParams(search)).toString();
}
