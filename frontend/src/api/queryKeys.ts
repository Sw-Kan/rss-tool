/** 全部 queryKey 收敛在这里，避免各组件自己拼导致缓存失效不一致。 */

import type { ReaderSearch } from '../types';
import { queryKeyFor } from '../lib/scope';

export const keys = {
  me: ['me'] as const,
  summary: ['items', 'summary'] as const,
  settings: ['settings'] as const,
  folders: ['folders'] as const,
  feeds: (folderId: string | null) => ['feeds', folderId ?? 'all'] as const,
  feedLists: ['feeds'] as const,
  items: (search: ReaderSearch) => ['items', 'list', queryKeyFor(search)] as const,
  itemLists: ['items', 'list'] as const,
  item: (id: string) => ['items', 'detail', id] as const,
  itemDetails: ['items', 'detail'] as const,
  itemContext: (id: string, search: ReaderSearch) =>
    ['items', 'context', id, queryKeyFor(search)] as const,
};

/** 任何写操作完成后统一失效这些 key（AGENTS.md §跨模块契约）。 */
export const INVALIDATE_AFTER_WRITE = [keys.itemLists, keys.itemDetails, keys.summary];
