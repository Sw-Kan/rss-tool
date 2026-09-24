/** 阅读器视图状态 ↔ URL 查询串 ↔ 后端查询参数。
 *
 *  一级类型横向叠加；二级是「目录」或「收藏」，两者同级、互斥：
 *    kind ⊕ ( folder ⊕ feed | fav ) ⊕ state
 *
 *  所以收藏看的是「当前类型下收藏的内容」，不会被目录或单源再筛一遍
 *  （docs/architecture.md 的前端路由契约）。
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

/** 点击一级类型入口（全部/文章/图片/视频）：只换类型，二级选择原样保留。 */
export function applyNav(nav: NavKey, current: ReaderSearch): ReaderSearch {
  if (nav === 'favorites') {
    // 收藏与目录同级：进入收藏就离开目录；再点一次取消，回到当前类型的普通视图
    return { ...current, fav: !current.fav, folder: null, feed: null, item: null };
  }
  return { ...current, kind: NAV_KINDS[nav], feed: null, item: null };
}

/** 点击二级目录（或未分组）：与收藏同级，进目录就离开收藏。 */
export function applyFolder(folderId: string | null, current: ReaderSearch): ReaderSearch {
  return { ...current, folder: folderId, fav: false, feed: null, item: null };
}

/** 点击三级源：源在目录里，同样离开收藏。 */
export function applyFeed(feedId: string | null, current: ReaderSearch): ReaderSearch {
  return { ...current, feed: feedId, fav: false, item: null };
}

export function applyState(state: ReadState, current: ReaderSearch): ReaderSearch {
  return { ...current, state };
}

export function applyItem(itemId: string | null, current: ReaderSearch): ReaderSearch {
  return { ...current, item: itemId };
}

/** 反推一级类型入口的高亮项。收藏是二级，单独由 search.fav 决定，可以同时高亮。 */
export function activeNav(search: ReaderSearch): NavKey {
  if (search.kind === 'article') return 'essays';
  if (search.kind === 'picture') return 'pictures';
  if (search.kind === 'video') return 'videos';
  return 'all';
}

/** 页面标题（设计稿顶部左侧的大字）。 */
export function viewTitle(search: ReaderSearch, folderName: string | null): string {
  if (search.folder) return folderName ?? '目录';
  if (search.fav) return '收藏';
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
