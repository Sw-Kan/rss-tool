// @vitest-environment jsdom
/** pictures / videos：点条目在弹层里看详情，墙与网格保持全宽（不出现右栏分隔条）。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../lib/i18n';
import { zhCN } from '../../lib/i18n/zh-CN';
import type { ItemDetail } from '../../types';
import { ReaderPage } from './ReaderPage';

/** jsdom 里量不到尺寸：PictureWall 靠 clientWidth + ResizeObserver 算列数，宽为 0 就不渲染卡片。 */
const WIDTH = 1200;
class ResizeObserverStub {
  private cb: (entries: { contentRect: { width: number } }[]) => void;
  constructor(cb: (entries: { contentRect: { width: number } }[]) => void) {
    this.cb = cb;
  }
  observe() {
    this.cb([{ contentRect: { width: WIDTH } }]);
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
Object.defineProperty(HTMLElement.prototype, 'clientWidth', {
  configurable: true,
  get: () => WIDTH,
});

/** 列表/详情接口都直接喂这个 fixture（stub 的 fetch 不看类型）。 */
function item(overrides: Partial<ItemDetail>): ItemDetail {
  return {
    id: 'x',
    feed_id: 'f1',
    feed_title: '少数派',
    feed_icon_url: null,
    title: '',
    author: null,
    url: 'https://example.com/post',
    published_at: '2026-01-01T00:00:00+00:00',
    kind: 'picture',
    image_url: null,
    image_width: null,
    image_height: null,
    video_url: null,
    channel_name: null,
    is_read: false,
    is_favorite: false,
    content_html: '<p>正文</p>',
    summary_html: null,
    word_count: 0,
    ...overrides,
  };
}

const PICTURE = item({
  id: 'p1',
  title: '京都的秋天：一整个下午的银杏',
  kind: 'picture',
  image_url: 'https://cdn.example.com/kyoto.jpg',
  image_width: 1200,
  image_height: 800,
  content_html: '<p>胶片扫描后才发现，那天下午的光是斜的。</p>',
});

const VIDEO = item({
  id: 'v1',
  title: '用 RSS 搭建自己的信息流（上）',
  kind: 'video',
  image_url: 'https://cdn.example.com/cover.jpg',
  image_width: 1280,
  image_height: 720,
  video_url: 'https://www.bilibili.com/video/BV1xx411c7mD',
  channel_name: '少数派视频',
  content_html: '<p>这期把订阅、目录整理和全文抓取串了一遍。</p>',
});

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

function stubFetch(items: ItemDetail[]) {
  return (input: string) => {
    const url = String(input);
    if (url.includes('/api/ai/config')) return Promise.resolve(json({ providers: [], token_limit: 0 }));
    if (url.includes('/api/ai/results'))
      return Promise.resolve(json({ summary: null, title_translation: null }));
    if (url.includes('/context'))
      return Promise.resolve(json({ prev_id: null, next_id: null, index: 0, total: 1 }));
    if (url.includes('/api/items/summary'))
      return Promise.resolve(
        json({
          total_unread: 2,
          feed_count: 1,
          favorites: 0,
          by_kind: { article: 0, picture: 1, video: 1 },
        }),
      );
    const detail = /\/api\/items\/([^?]+)$/.exec(url);
    if (detail) {
      const found = items.find((item) => item.id === detail[1]);
      return Promise.resolve(found ? json(found) : new Response('{}', { status: 404 }));
    }
    if (url.includes('/api/items')) return Promise.resolve(json({ items, next_cursor: null }));
    return Promise.resolve(json({ items: [] }));
  };
}

function Probe() {
  return <span data-testid="query">{useLocation().search}</span>;
}

function renderReader(entry: string, items: ItemDetail[]) {
  vi.stubGlobal('fetch', stubFetch(items));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="zh-CN">
        <MemoryRouter initialEntries={[entry]}>
          <ReaderPage />
          <Probe />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const query = () => screen.getByTestId('query').textContent ?? '';
const dialog = () => screen.getByRole('dialog');

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('图片模式的详情弹层', () => {
  it('点卡片：写 item= 进 URL、弹层出现、图片走媒体缓存', async () => {
    renderReader('/reader?kind=picture', [PICTURE]);
    const card = await screen.findByRole('button', { name: /京都的秋天/ });

    // 不是右栏：进图片页不该有分隔条，也不该自动选中第一条
    expect(screen.queryByRole('separator')).toBeNull();
    expect(screen.queryByRole('dialog')).toBeNull();

    fireEvent.click(card);
    await waitFor(() => expect(query()).toBe('?kind=picture&item=p1'));

    const inside = within(dialog());
    expect(inside.getByRole('heading', { name: PICTURE.title })).toBeTruthy();
    const image = inside.getByRole('img', { name: PICTURE.title });
    expect(image.getAttribute('src')).toContain('/api/media?url=');
  });

  it('× 关闭：清掉 item= 且不变成右栏', async () => {
    renderReader('/reader?kind=picture', [PICTURE]);
    fireEvent.click(await screen.findByRole('button', { name: /京都的秋天/ }));
    await waitFor(() => expect(query()).toBe('?kind=picture&item=p1'));

    fireEvent.click(within(dialog()).getByRole('button', { name: zhCN.close }));

    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(query()).toBe('?kind=picture');
    expect(screen.queryByRole('separator')).toBeNull();
    // 弹层关掉后墙还在
    expect(screen.getByRole('button', { name: /京都的秋天/ })).toBeTruthy();
  });

  it('Esc 也能关', async () => {
    renderReader('/reader?kind=picture', [PICTURE]);
    fireEvent.click(await screen.findByRole('button', { name: /京都的秋天/ }));
    await waitFor(() => expect(query()).toBe('?kind=picture&item=p1'));

    fireEvent.keyDown(document.body, { key: 'Escape', code: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
  });

  it('深链 ?kind=picture&item=p1 直接就绪', async () => {
    renderReader('/reader?kind=picture&item=p1', [PICTURE]);
    await waitFor(() => expect(screen.getByRole('dialog')).toBeTruthy());
    expect(within(dialog()).getByRole('heading', { name: PICTURE.title })).toBeTruthy();
  });
});

describe('视频模式的详情弹层', () => {
  it('点卡片：弹层里是封面 + 播放按钮，点开原站', async () => {
    renderReader('/reader?kind=video', [VIDEO]);
    fireEvent.click(await screen.findByRole('button', { name: /用 RSS 搭建自己的信息流/ }));
    await waitFor(() => expect(query()).toBe('?kind=video&item=v1'));

    const play = within(dialog()).getByRole('link', { name: zhCN.article.playVideo });
    expect(play.getAttribute('href')).toBe(VIDEO.video_url);
    expect(play.getAttribute('target')).toBe('_blank');
    expect(play.getAttribute('rel')).toContain('noopener');
    // 封面走媒体缓存，不再是那行裸链接
    expect(within(dialog()).getByRole('img', { name: VIDEO.title }).getAttribute('src')).toContain(
      '/api/media?url=',
    );
    expect(within(dialog()).queryByText(VIDEO.video_url ?? '')).toBeNull();
  });
});
