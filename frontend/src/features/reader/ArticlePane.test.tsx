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

function stubFetch(enabledProviders: unknown[]) {
  calls = [];
  return (url: string, init?: RequestInit) => {
    calls.push({ url, method: (init?.method ?? 'GET').toUpperCase() });
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
    if (url.includes('/api/items/a1')) return Promise.resolve(json(ITEM));
    return Promise.resolve(json({}));
  };
}

function Probe() {
  return <span data-testid="query">{useLocation().search}</span>;
}

function renderPane() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="zh-CN">
        <MemoryRouter initialEntries={['/reader?item=a1']}>
          <ArticlePane
            itemId="a1"
            search={parseSearch(new URLSearchParams('item=a1'))}
            onNavigate={() => {}}
          />
          <Probe />
        </MemoryRouter>
      </I18nProvider>
    </QueryClientProvider>,
  );
}

const summarizeButton = () => screen.getByRole('button', { name: zhCN.ai.summarize });
const query = () => screen.getByTestId('query').textContent;
const generated = () => calls.filter((call) => call.url.includes('/api/ai/generate'));

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
    expect(generated()).toHaveLength(0);
  });

  it('有启用的供应商时：无说明、点击生成总结', async () => {
    vi.stubGlobal('fetch', stubFetch([PROVIDER]));
    renderPane();
    await waitFor(() => expect(summarizeButton()).toBeTruthy());
    await waitFor(() => expect(summarizeButton().getAttribute('title')).toBeNull());

    fireEvent.click(summarizeButton());
    await waitFor(() => expect(generated()).toHaveLength(1));
    expect(generated()[0]?.url).toContain('kind=summary');
    expect(query()).toBe('?item=a1');
  });
});
