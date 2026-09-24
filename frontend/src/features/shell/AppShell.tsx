import { useCallback, useEffect, useMemo, useState } from 'react';
import { Outlet, useSearchParams } from 'react-router-dom';

import { useMe, useSettings } from '../../api/hooks';
import { Resizer } from '../../components/Resizer';
import { isLocale, useI18n, useT } from '../../lib/i18n';
import { parseSearch } from '../../lib/scope';
import { SIDEBAR_KEY, SIDEBAR_SPLIT, loadWidth } from '../../lib/split';
import type { ReaderSearch } from '../../types';
import { SettingsDialog, SETTINGS_TABS, type SettingsTab } from '../settings/SettingsDialog';
import { Sidebar } from './Sidebar';

/** 阅读器视图状态。update 会保留 settings 深链参数，避免开设置时丢过滤条件。 */
export function useReaderSearch() {
  const [params, setParams] = useSearchParams();
  const search = useMemo(() => parseSearch(params), [params]);

  const update = useCallback(
    (next: ReaderSearch, options?: { replace?: boolean }) => {
      const merged = new URLSearchParams();
      if (next.kind) merged.set('kind', next.kind);
      if (next.fav) merged.set('fav', '1');
      if (next.folder) merged.set('folder', next.folder);
      if (next.feed) merged.set('feed', next.feed);
      if (next.state !== 'all') merged.set('state', next.state);
      if (next.item) merged.set('item', next.item);
      const settings = params.get('settings');
      if (settings) merged.set('settings', settings);
      setParams(merged, { replace: options?.replace ?? false });
    },
    [params, setParams],
  );

  return { search, update };
}

function readSettingsTab(params: URLSearchParams): SettingsTab | null {
  const value = params.get('settings');
  return SETTINGS_TABS.includes(value as SettingsTab) ? (value as SettingsTab) : null;
}

export function AppShell() {
  const t = useT();
  const { setLocale } = useI18n();
  const me = useMe();
  const settings = useSettings();
  const { search } = useReaderSearch();
  const [params, setParams] = useSearchParams();
  const [sidebarWidth, setSidebarWidth] = useState(() => loadWidth(SIDEBAR_KEY, SIDEBAR_SPLIT));

  const activeTab = readSettingsTab(params);

  // 登录后以服务端设置为准（登录前的语言来自 localStorage / 浏览器）
  const serverLanguage = settings.data?.language;
  useEffect(() => {
    if (isLocale(serverLanguage)) setLocale(serverLanguage);
  }, [serverLanguage, setLocale]);

  // 主题与正文字号挂在 <html> 上，令牌在 tokens.css 里切换
  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = settings.data?.theme ?? 'light';
    root.dataset.textstyle = settings.data?.text_style ?? 'comfortable';
  }, [settings.data?.theme, settings.data?.text_style]);

  const patchParams = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(params);
    mutate(next);
    setParams(next);
  };

  return (
    <div className="flex h-full bg-page">
      <div style={{ width: sidebarWidth }} className="h-full shrink-0">
        <Sidebar
          user={me.data ?? null}
          search={search}
          onOpenSettings={() => patchParams((next) => next.set('settings', 'appearance'))}
        />
      </div>

      <Resizer
        label={t.list.resizeSidebar}
        width={sidebarWidth}
        onChange={setSidebarWidth}
        config={SIDEBAR_SPLIT}
        storageKey={SIDEBAR_KEY}
      />

      <main className="min-w-0 flex-1">
        <Outlet />
      </main>

      <SettingsDialog
        open={activeTab !== null}
        activeTab={activeTab ?? 'appearance'}
        onTabChange={(tab) => patchParams((next) => next.set('settings', tab))}
        onOpenChange={(open) => {
          if (!open) patchParams((next) => next.delete('settings'));
        }}
      />
    </div>
  );
}
