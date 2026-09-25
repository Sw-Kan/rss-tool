// @vitest-environment jsdom
/** 阅读器顶栏的 AI 按钮：没有启用供应商时是灰的但能点开「设置 → AI」。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../lib/i18n';
import { zhCN } from '../../lib/i18n/zh-CN';
import { parseSearch } from '../../lib/scope';
import { ArticlePane } from './ArticlePane';

const ITEM = {
  id: 'a1',
  feed_id: 'f1',
  feed_title: 'vox',
  feed_icon_url: null,
  title: 'A headline',
  author: 'Someone',
  url: 'https://example.com/a1',
  published_at: '2026-01-01T00:00:00+00:00',
  kind: 'article',
  image_url: null,
  image_width: null,
  image_height: null,
  video_url: null,
  channel_name: null,
  is_read: false,
  is_favorite: false,
  content_html: '<p>正文</p>',
  summary_html: null,
  word_count: 2,
};

const PROVIDER = {
  id: 'p1',
  label: 'OpenAI',
  protocol: 'openai',
  base_url: 'https://api.openai.com/v1',
  model: 'gpt-4o-mini',
  enabled: true,
  position: 1,
  has_key: true,
  api_key_hint: 'sk-••••••••abcd',
};

function json(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'content-type': 'application/json' },
  });
}

let calls: { url: string; method: string }[] = [];

/** 可控的 SSE 通道：测试里手动 push 帧来模拟流式（真实上游是分块给的）。 */
function sseChannel() {
  const encoder = new TextEncoder();
  let push: (text: string) => void = () => {};
  let close: () => void = () => {};
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      push = (text) => controller.enqueue(encoder.encode(text));
      close = () => controller.close();
    },
  });
  return {
    open: () =>
      Promise.resolve(
        new Response(body, { headers: { 'content-type': 'text/event-stream' } }),
      ),
    frame: (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`,
    send: (text: string) => push(text),
    close: () => close(),
  };
}

function stubFetch(enabledProviders: unknown[], stream?: () => Promise<Response>, item: unknown = ITEM) {
  calls = [];
  return (url: string, init?: RequestInit) => {
    calls.push({ url, method: (init?.method ?? 'GET').toUpperCase() });
    if (url.includes('/api/ai/generate/stream') && stream) return stream();
    if (url.includes('/api/ai/config'))
      return Promise.resolve(json({ providers: enabledProviders, token_limit: 0 }));
    if (url.includes('/api/ai/results'))
      return Promise.resolve(json({ summary: null, title_translation: null }));
    if (url.includes('/api/ai/generate'))
      return Promise.resolve(
        json({
          kind: 'summary',
          content: '一句话总结。',
          model: 'gpt-4o-mini',
          cached: false,
          tokens_in: 1,
          tokens_out: 1,
          created_at: '2026-01-01T00:00:00+00:00',
        }),
      );
    if (url.includes('/context'))
      return Promise.resolve(json({ prev_id: null, next_id: null, index: 0, total: 1 }));
    if (url.includes('/api/items/a1')) return Promise.resolve(json(item));
    return Promise.resolve(json({}));
  };
}

function Probe() {
  return <span data-testid="query">{useLocation().search}</span>;
}

function renderPane(options: { onClose?: () => void; variant?: 'pane' | 'overlay' } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="zh-CN">
        <MemoryRouter initialEntries={['/reader?item=a1']}>
          <ArticlePane
            itemId="a1"
            search={parseSearch(new URLSearchParams('item=a1'))}
            onNavigate={() => {}}
            onClose={options.onClose}
            variant={options.variant}
          />
          <Probe />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const summarizeButton = () => screen.getByRole('button', { name: zhCN.ai.summarize });
const query = () => screen.getByTestId('query').textContent;
const streamed = () => calls.filter((call) => call.url.includes('/api/ai/generate/stream'));

beforeEach(() => {
  vi.stubGlobal('fetch', stubFetch([]));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('ArticlePane 的 AI 按钮', () => {
  it('没有启用的供应商时：灰、有说明、点一下打开 设置 → AI，且不调上游', async () => {
    renderPane();
    await waitFor(() => expect(summarizeButton()).toBeTruthy());

    const button = summarizeButton();
    expect(button.getAttribute('title')).toBe(zhCN.ai.needProvider);
    expect(button.hasAttribute('disabled')).toBe(false);
    expect(button.className).toContain('opacity-60');

    fireEvent.click(button);
    expect(query()).toBe('?item=a1&settings=ai');
    expect(streamed()).toHaveLength(0);
  });

  it('有启用的供应商时：点击走 SSE 端点，结果落到正文上方', async () => {
    const channel = sseChannel();
    vi.stubGlobal('fetch', stubFetch([PROVIDER], channel.open));
    renderPane();
    await waitFor(() => expect(summarizeButton().getAttribute('title')).toBeNull());

    fireEvent.click(summarizeButton());
    await waitFor(() => expect(streamed()).toHaveLength(1));
    expect(streamed()[0]?.url).toContain('/api/ai/generate/stream?kind=summary');
    expect(streamed()[0]?.method).toBe('POST');
    expect(query()).toBe('?item=a1');

    channel.send(
      channel.frame('done', {
        kind: 'summary',
        content: '一句话总结。',
        model: 'gpt-4o-mini',
        cached: false,
        tokens_in: 3,
        tokens_out: 4,
        created_at: '2026-01-01T00:00:00+00:00',
      }),
    );
    channel.close();
    await waitFor(() => expect(screen.getByText('一句话总结。')).toBeTruthy());
  });

  it('流式：先出现部分文本，done 之后再补齐最终结果', async () => {
    const channel = sseChannel();
    vi.stubGlobal('fetch', stubFetch([PROVIDER], channel.open));
    renderPane();
    await waitFor(() => expect(summarizeButton().getAttribute('title')).toBeNull());

    fireEvent.click(summarizeButton());
    await waitFor(() => expect(streamed()).toHaveLength(1));

    channel.send(
      channel.frame('meta', { provider: 'OpenAI', model: 'gpt-4o-mini', attempt: 1 }),
    );
    channel.send(channel.frame('delta', { text: '前半' }));
    await waitFor(() => expect(screen.getByText('前半')).toBeTruthy());

    channel.send(channel.frame('delta', { text: '后半' }));
    channel.send(
      channel.frame('done', {
        kind: 'summary',
        content: '前半后半',
        model: 'gpt-4o-mini',
        cached: false,
        tokens_in: 3,
        tokens_out: 4,
        created_at: '2026-01-01T00:00:00+00:00',
      }),
    );
    channel.close();
    await waitFor(() => expect(screen.getByText('前半后半')).toBeTruthy());
  });

  it('流式：error 帧撤掉半成品，并把原因显示出来', async () => {
    const channel = sseChannel();
    vi.stubGlobal('fetch', stubFetch([PROVIDER], channel.open));
    renderPane();
    await waitFor(() => expect(summarizeButton().getAttribute('title')).toBeNull());

    fireEvent.click(summarizeButton());
    await waitFor(() => expect(streamed()).toHaveLength(1));

    channel.send(channel.frame('delta', { text: '写到一半' }));
    await waitFor(() => expect(screen.getByText('写到一半')).toBeTruthy());

    channel.send(channel.frame('error', { detail: 'AI 接口限流（429）：rate-limited' }));
    channel.close();

    await waitFor(() => expect(screen.getByText(/限流（429）/)).toBeTruthy());
    expect(screen.queryByText('写到一半')).toBeNull();
  });
});

const VIDEO_ITEM = {
  ...ITEM,
  kind: 'video',
  channel_name: '少数派视频',
  image_url: 'https://cdn.example.com/cover.jpg',
  image_width: 1280,
  image_height: 720,
  video_url: 'https://www.bilibili.com/video/BV1xx411c7mD',
};

describe('视频详情与弹层形态', () => {
  it('视频条目：封面 + 播放按钮指向原站，而不是那行裸链接', async () => {
    vi.stubGlobal('fetch', stubFetch([], undefined, VIDEO_ITEM));
    renderPane();

    const play = await screen.findByRole('link', { name: zhCN.article.playVideo });
    expect(play.getAttribute('href')).toBe(VIDEO_ITEM.video_url);
    expect(play.getAttribute('target')).toBe('_blank');
    expect(play.getAttribute('rel')).toContain('noopener');
    // 封面走媒体缓存（防盗链由后端带 Referer 处理）
    const cover = screen.getByRole('img', { name: VIDEO_ITEM.title });
    expect(cover.getAttribute('src')).toContain('/api/media?url=');
    expect(screen.queryByText(VIDEO_ITEM.video_url)).toBeNull();
  });

  it('视频条目没有 video_url 时退到原文页', async () => {
    vi.stubGlobal('fetch', stubFetch([], undefined, { ...VIDEO_ITEM, video_url: null }));
    renderPane();

    const play = await screen.findByRole('link', { name: zhCN.article.playVideo });
    expect(play.getAttribute('href')).toBe(ITEM.url);
  });

  it('overlay 形态：顶栏右端是关闭按钮，点一下就走回调', async () => {
    const onClose = vi.fn();
    renderPane({ variant: 'overlay', onClose });
    await waitFor(() => expect(screen.getByRole('heading', { name: ITEM.title })).toBeTruthy());

    fireEvent.click(screen.getByRole('button', { name: zhCN.close }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('右栏形态（all 模式）没有关闭按钮', async () => {
    renderPane();
    await waitFor(() => expect(screen.getByRole('heading', { name: ITEM.title })).toBeTruthy());
    expect(screen.queryByRole('button', { name: zhCN.close })).toBeNull();
  });
});
