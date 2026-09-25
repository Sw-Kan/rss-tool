// @vitest-environment jsdom
/** 侧边栏点击后 URL 查询串的回归测试（层级组合关系见 docs/architecture.md）。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../lib/i18n';
import { zhCN } from '../../lib/i18n/zh-CN';
import { parseSearch } from '../../lib/scope';
import { Sidebar } from './Sidebar';

const FOLDERS = { items: [{ id: 'd1', name: '技术', position: 0 }] };

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
    {
      id: 'f2',
      url: 'https://example.com/tech',
      kind_override: 'auto',
      site_url: null,
      title: '技术源',
      description: null,
      icon_url: null,
      folder_id: 'd1',
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

/** 拖拽断言要看 PATCH 的 body，所以记下所有请求。 */
let requests: { url: string; method: string; body: unknown }[] = [];

beforeEach(() => {
  requests = [];
  vi.stubGlobal('fetch', (url: string, init?: RequestInit) => {
    requests.push({
      url: String(url),
      method: (init?.method ?? 'GET').toUpperCase(),
      body: init?.body ? JSON.parse(String(init.body)) : null,
    });
    if (url.includes('/api/items/summary')) return Promise.resolve(json(SUMMARY));
    if (url.includes('/api/folders')) return Promise.resolve(json(FOLDERS));
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

/** 长按 250ms 后拖拽：pointerdown → 等定时器 → 落点 pointerover → pointerup。 */
async function longPressAndDrop(source: HTMLElement, target: Element) {
  fireEvent.pointerDown(source, { button: 0, pointerType: 'mouse', clientX: 10, clientY: 10 });
  await act(async () => {
    vi.advanceTimersByTime(300);
  });
  // React 的 onPointerEnter 是由 pointerover 合成的（pointerenter 不冒泡，派发它没用）
  fireEvent.pointerOver(target);
  await act(async () => {
    fireEvent.pointerUp(window);
  });
}

const patch = () => requests.find((request) => request.method === 'PATCH');

describe('Sidebar 长按拖动源到别的目录', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('长按拖到目录行松手 → PATCH folder_id，且这次点击被吃掉', async () => {
    renderSidebar('/reader');
    await waitFor(() => expect(screen.getByText('新源')).toBeTruthy());

    const row = screen.getByText('新源');
    const folderRow = document.querySelector('[data-drop="d1"]');
    expect(folderRow).toBeTruthy();

    // 长按判定成立后应该多出一个跟着指针走的拖影
    fireEvent.pointerDown(row, { button: 0, pointerType: 'mouse', clientX: 10, clientY: 10 });
    await act(async () => {
      vi.advanceTimersByTime(300);
    });
    expect(screen.getAllByText('新源')).toHaveLength(2);
    fireEvent.pointerUp(window);

    await longPressAndDrop(row, folderRow as Element);

    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch()?.url).toContain('/api/feeds/f1');
    expect(patch()?.body).toEqual({ folder_id: 'd1', clear_folder: false, kind: undefined });

    // 松手紧跟的那次 click 不该切源（否则拖完就跳走了）
    fireEvent.click(row);
    expect(query()).toBe('');
    // 只吃一次：再点一下照常切源
    fireEvent.click(row);
    expect(query()).toBe('?feed=f1');
  });

  it('没到长按时长就松手 → 不发请求，点击还是切源', async () => {
    renderSidebar('/reader');
    await waitFor(() => expect(screen.getByText('新源')).toBeTruthy());

    const row = screen.getByText('新源');
    fireEvent.pointerDown(row, { button: 0, pointerType: 'mouse', clientX: 10, clientY: 10 });
    fireEvent.pointerUp(window);
    fireEvent.click(row);

    expect(patch()).toBeUndefined();
    expect(query()).toBe('?feed=f1');
  });

  it('把目录里的源拖回「未分组源」→ 发 clear_folder', async () => {
    renderSidebar('/reader');
    await waitFor(() => expect(screen.getByText('新源')).toBeTruthy());

    // 目录默认收起，先展开才能看到里面的源
    fireEvent.click(screen.getByRole('button', { name: zhCN.nav.expandFolder }));
    const row = await screen.findByText('技术源');
    const ungrouped = document.querySelector('[data-drop="ungrouped"]');
    expect(ungrouped).toBeTruthy();
    await longPressAndDrop(row, ungrouped as Element);

    await waitFor(() => expect(patch()).toBeTruthy());
    expect(patch()?.body).toEqual({ folder_id: undefined, clear_folder: true, kind: undefined });
  });

  it('手指点按不参与拖拽（留给滚动），点一下仍然切源', async () => {
    renderSidebar('/reader');
    await waitFor(() => expect(screen.getByText('新源')).toBeTruthy());

    const row = screen.getByText('新源');
    fireEvent.pointerDown(row, { button: 0, pointerType: 'touch', clientX: 10, clientY: 10 });
    act(() => {
      vi.advanceTimersByTime(300);
    });
    fireEvent.pointerUp(window);
    fireEvent.click(row);

    expect(patch()).toBeUndefined();
    expect(query()).toBe('?feed=f1');
  });
});
