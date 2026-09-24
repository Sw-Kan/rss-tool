// @vitest-environment jsdom
/** 设置弹窗的「路由感」：切 tab 时外壳不动，只有内容区变化。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../lib/i18n';
import { SettingsDialog, SETTINGS_TABS, type SettingsTab } from './SettingsDialog';

const SETTINGS = {
  theme: 'light',
  language: 'zh-CN',
  auto_refresh_enabled: true,
  refresh_interval_minutes: 60,
  text_style: 'comfortable',
  ai_token_limit: 0,
};

function stubFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.includes('/api/settings')
      ? SETTINGS
      : url.includes('/api/feeds')
        ? { items: [] }
        : url.includes('/api/folders')
          ? { items: [], ungrouped: { feed_count: 0, unread_count: 0 } }
          : url.includes('/api/ai/config')
            ? { providers: [], token_limit: 0 }
            : url.includes('/api/ai/usage')
              ? { month_tokens: 0, total_tokens: 0, limit: 0, calls: 0, by_kind: {} }
              : url.includes('/api/ai/presets')
                ? []
                : {};
    return { ok: true, status: 200, statusText: 'OK', json: async () => body } as Response;
  });
}

function renderDialog(tab: SettingsTab) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="zh-CN">
        <SettingsDialog
          open
          activeTab={tab}
          onTabChange={() => {}}
          onOpenChange={() => {}}
        />
      </I18nProvider>
    </QueryClientProvider>,
  );
  return view;
}

beforeEach(() => {
  vi.stubGlobal('fetch', stubFetch());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('SettingsDialog', () => {
  it('keeps the shell size fixed while switching tabs', async () => {
    const { rerender } = renderDialog('appearance');
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
    const first = screen.getByRole('dialog');
    expect(first.style.width).toBe('960px');
    expect(first.style.height).toBe('760px');

    for (const tab of SETTINGS_TABS) {
      rerender(
        <QueryClientProvider client={client}>
          <I18nProvider initialLocale="zh-CN">
            <SettingsDialog open activeTab={tab} onTabChange={() => {}} onOpenChange={() => {}} />
          </I18nProvider>
        </QueryClientProvider>,
      );
      const dialog = screen.getByRole('dialog');
      expect(dialog.style.width).toBe('960px');
      expect(dialog.style.height).toBe('760px');
    }
  });

  it('renders exactly one active tab panel at a time', async () => {
    const { rerender } = renderDialog('integrations');
    await waitFor(() => expect(screen.getByRole('tabpanel')).toBeTruthy());

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    rerender(
      <QueryClientProvider client={client}>
        <I18nProvider initialLocale="zh-CN">
          <SettingsDialog
            open
            activeTab="automation"
            onTabChange={() => {}}
            onOpenChange={() => {}}
          />
        </I18nProvider>
      </QueryClientProvider>,
    );

    expect(screen.getAllByRole('tabpanel')).toHaveLength(1);
    expect(screen.getByRole('tab', { name: '自动化' }).getAttribute('aria-selected')).toBe('true');
  });

  it('marks every navigation entry as a tab', async () => {
    renderDialog('appearance');
    await waitFor(() => expect(screen.getAllByRole('tab')).toHaveLength(SETTINGS_TABS.length));
  });
});
