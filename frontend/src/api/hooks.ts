/** 全部服务端状态的唯一入口：查询 + 变更 + 统一的缓存失效。
 *
 *  组件不要直接用 fetch，也不要自己写 useEffect 取数（AGENTS.md §5）。
 */

import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query';

import { apiParams } from '../lib/scope';
import type {
  AppSettings,
  Feed,
  Folder,
  FolderList,
  Item,
  ItemContext,
  ItemDetail,
  ItemPage,
  OpmlImportResult,
  ReaderSearch,
  RefreshResult,
  SidebarSummary,
  User,
} from '../types';
import { http, isUnauthorized, download } from './client';
import { keys } from './queryKeys';

const PAGE_SIZE = 30;

/* ---------------- 失效策略 ---------------- */

function invalidateContent(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: keys.itemLists });
  void client.invalidateQueries({ queryKey: keys.itemDetails });
  void client.invalidateQueries({ queryKey: keys.summary });
}

function invalidateSubscriptions(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: keys.feedLists });
  void client.invalidateQueries({ queryKey: keys.folders });
  invalidateContent(client);
}

/* ---------------- 会话 ---------------- */

export function useMe() {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => http.get<User>('/api/auth/me'),
    retry: false,
    staleTime: 60_000,
  });
}

function useAuthMutation<TBody>(path: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: TBody) => http.post<User>(path, body),
    onSuccess: async () => {
      await client.invalidateQueries();
    },
  });
}

export const useLogin = () => useAuthMutation<{ email: string; password: string }>('/api/auth/login');
export const useRegister = () =>
  useAuthMutation<{ username: string; email: string; password: string }>('/api/auth/register');

export function useSkipLogin() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => http.post<User>('/api/auth/skip'),
    onSuccess: async () => {
      await client.invalidateQueries();
    },
  });
}

export function useLogout() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => http.post<void>('/api/auth/logout'),
    onSuccess: () => {
      client.clear();
    },
  });
}

/* ---------------- 计数 / 目录 / 订阅源 ---------------- */

export function useSidebarSummary(enabled = true) {
  return useQuery({
    queryKey: keys.summary,
    queryFn: () => http.get<SidebarSummary>('/api/items/summary'),
    enabled,
  });
}

export function useFolders(enabled = true) {
  return useQuery({
    queryKey: keys.folders,
    queryFn: () => http.get<FolderList>('/api/folders'),
    enabled,
  });
}

export function useFeeds(folderId: string | null, enabled = true) {
  return useQuery({
    queryKey: keys.feeds(folderId),
    queryFn: () =>
      http.get<{ items: Feed[] }>('/api/feeds', folderId ? { folder_id: folderId } : undefined),
    enabled,
  });
}

export function useCreateFolder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => http.post<Folder>('/api/folders', { name }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.folders }),
  });
}

export function useRenameFolder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, name }: { id: string; name: string }) =>
      http.patch<Folder>(`/api/folders/${id}`, { name }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.folders }),
  });
}

export function useDeleteFolder() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => http.del<void>(`/api/folders/${id}`),
    onSuccess: () => invalidateSubscriptions(client),
  });
}

export function useCreateFeed() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: { url: string; folder_id?: string | null; title?: string }) =>
      http.post<Feed>('/api/feeds', body),
    onSuccess: () => invalidateSubscriptions(client),
  });
}

export function useUpdateFeed() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      title,
      folderId,
      clearFolder,
    }: {
      id: string;
      title?: string;
      folderId?: string | null;
      clearFolder?: boolean;
    }) =>
      http.patch<Feed>(`/api/feeds/${id}`, {
        title,
        folder_id: folderId ?? undefined,
        clear_folder: clearFolder ?? false,
      }),
    onSuccess: () => invalidateSubscriptions(client),
  });
}

export function useDeleteFeed() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => http.del<void>(`/api/feeds/${id}`),
    onSuccess: () => invalidateSubscriptions(client),
  });
}

export function useRefreshFeed() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => http.post<RefreshResult>(`/api/feeds/${id}/refresh`),
    onSuccess: () => invalidateSubscriptions(client),
  });
}

export function useRefreshAll() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (folderId: string | null) =>
      http.post<{ results: RefreshResult[] }>(
        folderId
          ? `/api/feeds/refresh?folder_id=${encodeURIComponent(folderId)}`
          : '/api/feeds/refresh',
      ),
    onSuccess: () => invalidateSubscriptions(client),
  });
}

export function useImportOpml() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => http.upload<OpmlImportResult>('/api/opml/import', file),
    onSuccess: () => invalidateSubscriptions(client),
  });
}

export const exportOpml = () => download('/api/opml/export', 'rss-tool.opml');
export const exportUserData = () => download('/api/users/me/export', 'rss-tool-export.json');

export function useClearLocalData() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => http.del<void>('/api/data'),
    onSuccess: () => client.clear(),
  });
}

/* ---------------- 文章列表 / 详情 / 阅读状态 ---------------- */

export function useItems(search: ReaderSearch, enabled = true) {
  return useInfiniteQuery({
    queryKey: keys.items(search),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      http.get<ItemPage>('/api/items', {
        ...apiParams(search),
        limit: PAGE_SIZE,
        cursor: pageParam,
      }),
    getNextPageParam: (last) => last.next_cursor,
    enabled,
  });
}

export function flattenItems(pages: ItemPage[] | undefined): Item[] {
  return pages?.flatMap((page) => page.items) ?? [];
}

export function useItem(itemId: string | null) {
  return useQuery({
    queryKey: keys.item(itemId ?? ''),
    queryFn: () => http.get<ItemDetail>(`/api/items/${itemId}`),
    enabled: Boolean(itemId),
  });
}

export function useItemContext(itemId: string | null, search: ReaderSearch) {
  return useQuery({
    queryKey: keys.itemContext(itemId ?? '', search),
    queryFn: () => http.get<ItemContext>(`/api/items/${itemId}/context`, apiParams(search)),
    enabled: Boolean(itemId),
  });
}

export function useSetItemState() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      is_read,
      is_favorite,
    }: {
      id: string;
      is_read?: boolean;
      is_favorite?: boolean;
    }) => http.patch<Item>(`/api/items/${id}/state`, { is_read, is_favorite }),
    onSuccess: () => invalidateContent(client),
  });
}

export function useBulkRead() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ ids, is_read }: { ids: string[]; is_read: boolean }) =>
      http.post<{ updated: number }>('/api/items/read', { ids, is_read }),
    onSuccess: () => invalidateContent(client),
  });
}

/* ---------------- 设置 / 个人资料 ---------------- */

export function useSettings(enabled = true) {
  return useQuery({
    queryKey: keys.settings,
    queryFn: () => http.get<AppSettings>('/api/settings'),
    enabled,
    staleTime: Infinity,
  });
}

export function useUpdateSettings() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<AppSettings>) => http.patch<AppSettings>('/api/settings', patch),
    onSuccess: (data) => {
      client.setQueryData(keys.settings, data);
    },
  });
}

export function useUpdateProfile() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<Pick<User, 'username' | 'avatar_type' | 'avatar_color'>>) =>
      http.patch<User>('/api/users/me', patch),
    onSuccess: (data) => {
      client.setQueryData(keys.me, data);
    },
  });
}

export function useUploadAvatar() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => http.upload<User>('/api/users/me/avatar', file, file.name),
    onSuccess: (data) => {
      client.setQueryData(keys.me, data);
    },
  });
}

export function useDeleteAvatar() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => http.del<User>('/api/users/me/avatar'),
    onSuccess: (data) => {
      client.setQueryData(keys.me, data);
    },
  });
}

/** 401 时把用户送回登录页（cookie 过期 / 后端重启换密钥）。 */
export function useUnauthorizedRedirect(onUnauthorized: () => void) {
  return (error: unknown): void => {
    if (isUnauthorized(error)) onUnauthorized();
  };
}
