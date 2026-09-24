// @vitest-environment jsdom
/** AI tab 渲染冒烟：验证供应商列表、掩码与用量条真的接到了数据。
 *  上游调用与 prompt 构造由后端 tests/test_ai.py 覆盖。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AiTab } from './AiTab';

const CONFIG = {
  providers: [
    {
      id: 'p1',
      label: 'OpenAI',
      protocol: 'openai',
      base_url: 'https://api.openai.com/v1',
      model: 'gpt-4o-mini',
      enabled: true,
      position: 1,
      has_key: true,
      api_key_hint: 'sk-••••••••4f2a',
    },
    {
      id: 'p2',
      label: 'Ollama（本地）',
      protocol: 'openai',
      base_url: 'http://127.0.0.1:11434/v1',
      model: 'qwen2.5:14b',
      enabled: false,
      position: 2,
      has_key: false,
      api_key_hint: '',
    },
  ],
  token_limit: 500000,
};

const USAGE = {
  month_tokens: 128400,
  total_tokens: 200000,
  limit: 500000,
  calls: 42,
  by_kind: { summary: 100000, title_translation: 28400 },
};

const PRESETS = [{ key: 'custom', label: '自定义', base_url: '', model: '' }];

function stubFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.includes('/api/ai/config')
      ? CONFIG
      : url.includes('/api/ai/usage')
        ? USAGE
        : url.includes('/api/ai/presets')
          ? PRESETS
          : {};
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => body,
    } as Response;
  });
}

function renderTab() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AiTab />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal('fetch', stubFetch());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('AiTab', () => {
  it('renders every provider with its base url, model and masked key', async () => {
    renderTab();

    await waitFor(() => expect(screen.getByDisplayValue('OpenAI')).toBeTruthy());
    expect(screen.getByDisplayValue('https://api.openai.com/v1')).toBeTruthy();
    expect(screen.getByDisplayValue('gpt-4o-mini')).toBeTruthy();
    // 明文 key 永远拿不到，只有掩码
    expect(screen.getByDisplayValue('sk-••••••••4f2a')).toBeTruthy();

    expect(screen.getByDisplayValue('Ollama（本地）')).toBeTruthy();
    expect(screen.getByDisplayValue('http://127.0.0.1:11434/v1')).toBeTruthy();
  });

  it('reflects each provider enabled state on its switch', async () => {
    renderTab();

    await waitFor(() => expect(screen.getByLabelText('OpenAI 启用')).toBeTruthy());
    expect(screen.getByLabelText('OpenAI 启用').getAttribute('aria-checked')).toBe('true');
    expect(screen.getByLabelText('Ollama（本地） 启用').getAttribute('aria-checked')).toBe(
      'false',
    );
  });

  it('shows monthly usage against the limit', async () => {
    renderTab();

    await waitFor(() => expect(screen.getByText('128,400')).toBeTruthy());
    expect(screen.getByText('500,000')).toBeTruthy();
    expect(screen.getByText(/达到上限后将暂停/)).toBeTruthy();
    expect(screen.getByDisplayValue('500000')).toBeTruthy();
    expect(screen.getByText(/本月 42 次调用/)).toBeTruthy();
  });
});
