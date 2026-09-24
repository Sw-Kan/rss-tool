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
  AiConfig,
  AiKind,
  AiPreset,
  AiProvider,
  AiResult,
  AiResults,
  AiUsage,
  AppSettings,
  Feed,
  Folder,
  Integration,
  IntegrationKind,
  IntegrationTest,
  KindChoice,
  FolderList,
  Item,
  ItemContext,
  ItemDetail,
  ItemPage,
  OpmlImportResult,
  ProxyConfig,
  ReaderSearch,
  Rule,
  RefreshResult,
  RsshubEnvSnippet,
  SidebarSummary,
  User,
} from '../types';
import { ApiError, http, isUnauthorized, download } from './client';
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
    mutationFn: (body: {
      url: string;
      folder_id?: string | null;
      title?: string;
      kind?: KindChoice;
    }) => http.post<Feed>('/api/feeds', body),
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
      kind,
    }: {
      id: string;
      title?: string;
      folderId?: string | null;
      clearFolder?: boolean;
      kind?: KindChoice;
    }) =>
      http.patch<Feed>(`/api/feeds/${id}`, {
        title,
        folder_id: folderId ?? undefined,
        clear_folder: clearFolder ?? false,
        kind,
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

/* ---------------- F1 AI ---------------- */

export function useAiConfig() {
  return useQuery({ queryKey: keys.aiConfig, queryFn: () => http.get<AiConfig>('/api/ai/config') });
}

/** 预设是静态表，不随用户变化。 */
export function useAiPresets() {
  return useQuery({
    queryKey: keys.aiPresets,
    queryFn: () => http.get<AiPreset[]>('/api/ai/presets'),
    staleTime: Infinity,
  });
}

export function useAiUsage() {
  return useQuery({ queryKey: keys.aiUsage, queryFn: () => http.get<AiUsage>('/api/ai/usage') });
}

/** 已有结果（不触发上游），打开文章时回填。 */
export function useAiResults(articleId: string | null) {
  return useQuery({
    queryKey: keys.aiResults(articleId ?? ''),
    queryFn: () => http.get<AiResults>('/api/ai/results', { article_id: articleId }),
    enabled: Boolean(articleId),
    // 流式生成会往这份缓存里逐块写，别让 focus 触发的后台 refetch 用服务端旧结果盖掉
    staleTime: Infinity,
  });
}

export function useCreateAiProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (preset: string) => http.post<AiProvider>('/api/ai/providers', { preset }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.aiConfig }),
  });
}

export function useUpdateAiProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      ...patch
    }: {
      id: string;
      label?: string;
      base_url?: string;
      model?: string;
      enabled?: boolean;
      api_key?: string;
      clear_key?: boolean;
    }) => http.patch<AiProvider>(`/api/ai/providers/${id}`, patch),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.aiConfig }),
  });
}

export function useDeleteAiProvider() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => http.del<void>(`/api/ai/providers/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.aiConfig }),
  });
}

/** 生成总结 / 标题翻译：SSE 流式，边收边写进 `aiResults` 缓存（命中缓存时只有一个 done）。
 *
 * 写在缓存里而不是组件 state，是因为阅读器本来就是从这份缓存读结果的 ——
 * ArticlePane 不需要知道自己在看的是流式的一半还是最终结果。
 */
export function useGenerateAi() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async ({
      articleId,
      kind,
    }: {
      articleId: string;
      kind: AiKind;
    }): Promise<AiResult> => {
      const key = keys.aiResults(articleId);
      const snapshot = client.getQueryData<AiResults>(key);
      const startedAt = new Date().toISOString();
      // 回调里赋值：用属性而不是 let，避免 TS 的收窄把 result 当成永远是 null
      const state = { text: '', model: '', result: null as AiResult | null, failure: null as string | null };

      const put = (value: AiResult) =>
        client.setQueryData<AiResults>(key, (previous) => ({
          summary: kind === 'summary' ? value : (previous?.summary ?? null),
          title_translation:
            kind === 'title_translation' ? value : (previous?.title_translation ?? null),
        }));
      const partial = (): AiResult => ({
        kind,
        content: state.text,
        model: state.model,
        cached: false,
        tokens_in: 0,
        tokens_out: 0,
        created_at: startedAt,
      });

      try {
        await http.stream(
          `/api/ai/generate/stream?kind=${kind}`,
          { article_id: articleId },
          (event) => {
            const payload = parseEventData(event.data);
            if (event.event === 'meta') {
              if (typeof payload?.model === 'string') state.model = payload.model;
              put(partial());
            } else if (event.event === 'delta') {
              if (typeof payload?.text === 'string') state.text += payload.text;
              put(partial());
            } else if (event.event === 'done') {
              state.result = payload as unknown as AiResult;
            } else if (event.event === 'error') {
              state.failure = typeof payload?.detail === 'string' ? payload.detail : 'AI 生成失败';
            }
          },
        );
      } catch (error) {
        // 网络层失败：半成品不留在界面上
        restore(client, key, snapshot);
        throw error;
      }

      if (state.failure) {
        // 上游失败不写库，界面也不该留半截总结
        restore(client, key, snapshot);
        throw new ApiError(502, state.failure);
      }
      if (!state.result) throw new ApiError(502, 'AI 接口没有返回结果');

      put(state.result);
      void client.invalidateQueries({ queryKey: keys.aiUsage });
      return state.result;
    },
  });
}

function restore(client: QueryClient, key: readonly unknown[], snapshot: AiResults | undefined): void {
  client.setQueryData(key, snapshot ?? { summary: null, title_translation: null });
}

function parseEventData(data: string): Record<string, unknown> | null {
  try {
    const value: unknown = JSON.parse(data);
    return typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/* ---------------- F2 集成 / F3 自动化 / F4 代理 ---------------- */

export function useIntegrations() {
  return useQuery({
    queryKey: keys.integrations,
    queryFn: () => http.get<{ items: Integration[] }>('/api/integrations'),
  });
}

export function useUpdateIntegration() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      kind,
      ...patch
    }: { kind: IntegrationKind; enabled?: boolean } & Partial<
      Pick<Integration, 'rsshub' | 'obsidian' | 'feishu' | 'custom_export'>
    >) => http.put<Integration>(`/api/integrations/${kind}`, patch),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.integrations });
      // 片段是按参数现算的，参数一改就得重算
      void client.invalidateQueries({ queryKey: keys.rsshubEnvSnippet });
    },
  });
}

/** RSSHub 端环境变量片段（明文，供复制到 RSSHub 的启动命令 / `.env`）。 */
export function useRsshubEnvSnippet(enabled = true) {
  return useQuery({
    queryKey: keys.rsshubEnvSnippet,
    queryFn: () => http.get<RsshubEnvSnippet>('/api/integrations/rsshub/env-snippet'),
    enabled,
  });
}

export function useTestRsshub() {
  return useMutation({
    mutationFn: () => http.post<IntegrationTest>('/api/integrations/rsshub/test'),
  });
}

export function useProxyConfig() {
  return useQuery({ queryKey: keys.proxy, queryFn: () => http.get<ProxyConfig>('/api/proxy') });
}

export function useUpdateProxy() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<ProxyConfig>) => http.patch<ProxyConfig>('/api/proxy', patch),
    onSuccess: (data) => client.setQueryData(keys.proxy, data),
  });
}

export function useTestProxy() {
  return useMutation({
    mutationFn: () => http.post<IntegrationTest>('/api/proxy/test'),
  });
}

export function useTestCustomExport() {
  return useMutation({
    mutationFn: () => http.post<IntegrationTest>('/api/integrations/custom_export/test'),
  });
}

export function useDefaultExportSchema() {
  return useQuery({
    queryKey: ['integrations', 'default-schema'],
    queryFn: () => http.get<{ schema_template: string }>('/api/integrations/custom_export/default-schema'),
    staleTime: Infinity,
  });
}

export function useRules() {
  return useQuery({ queryKey: keys.rules, queryFn: () => http.get<Rule[]>('/api/automation/rules') });
}

export function useCreateRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<Rule>) => http.post<Rule>('/api/automation/rules', body),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.rules }),
  });
}

export function useUpdateRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: string } & Partial<Rule>) =>
      http.patch<Rule>(`/api/automation/rules/${id}`, patch),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.rules }),
  });
}

export function useDeleteRule() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => http.del<void>(`/api/automation/rules/${id}`),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.rules }),
  });
}
