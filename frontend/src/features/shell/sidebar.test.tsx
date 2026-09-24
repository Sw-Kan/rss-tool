// @vitest-environment jsdom
/** 侧边栏点击后 URL 查询串的回归测试（层级组合关系见 docs/architecture.md）。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../lib/i18n';
import { parseSearch } from '../../lib/scope';
import { Sidebar } from './Sidebar';

const FEEDS = {
  items: [
    {
      id: 'f1',
      url: 'https://example.com/feed',
      kind_override: 'auto',
      site_url: null,
      title: '新源',
      description: null,
      icon_url: null,
      folder_id: null,
      custom_title: null,
      unread_count: 0,
      last_status: 'ok',
      last_error: null,
      last_fetched_at: null,
    },
  ],
};

const SUMMARY = {
  by_kind: { all: 1, article: 1, picture: 0, video: 0 },
  favorites: 0,
  folders: {},
  feeds: { f1: 0 },
  ungrouped: 1,
  total_unread: 0,
  feed_count: 1,
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function Probe() {
  return <span data-testid="query">{useLocation().search}</span>;
}

const query = () => screen.getByTestId('query').textContent;

beforeEach(() => {
  vi.stubGlobal('fetch', (url: string) => {
    if (url.includes('/api/items/summary')) return Promise.resolve(json(SUMMARY));
    if (url.includes('/api/folders')) return Promise.resolve(json({ items: [] }));
    if (url.includes('/api/feeds')) return Promise.resolve(json(FEEDS));
    return Promise.resolve(json({}));
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderSidebar(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="zh-CN">
        <MemoryRouter initialEntries={[entry]}>
          <Sidebar
            user={null}
            search={parseSearch(new URLSearchParams(entry.split('?')[1] ?? ''))}
            onOpenSettings={() => {}}
          />
          <Probe />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

describe('Sidebar 点击源', () => {
  it('收藏态下点源：退出收藏', async () => {
    renderSidebar('/reader?fav=1');
    await waitFor(() => expect(screen.getByText('新源')).toBeTruthy());
    fireEvent.click(screen.getByText('新源'));
    expect(query()).toBe('?feed=f1');
  });

  it('图片类型下点源：kind 保留（叠加关系）', async () => {
    renderSidebar('/reader?kind=picture');
    await waitFor(() => expect(screen.getByText('新源')).toBeTruthy());
    fireEvent.click(screen.getByText('新源'));
    expect(query()).toBe('?kind=picture&feed=f1');
  });
});
