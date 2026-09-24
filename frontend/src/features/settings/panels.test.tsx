// @vitest-environment jsdom
/** 三个新面板的渲染冒烟：验证设计稿里的关键控件真的接到了数据。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../lib/i18n';
import { AutomationTab } from './AutomationTab';
import { IntegrationsTab } from './IntegrationsTab';
import { ProxyTab } from './ProxyTab';

const INTEGRATIONS = {
  items: [
    {
      kind: 'rsshub',
      enabled: true,
      updated_at: null,
      rsshub: {
        base_url: 'http://192.168.1.20:1200',
        access_key: 'sec-••••••••1234',
        env: 'CACHE_TYPE=memory',
        params: [
          { name: 'cookie', scope: '/zhihu', value: 'z_c0=••••••••', secret: true },
          { name: 'limit', scope: '/twitter/user', value: '20', secret: false },
        ],
      },
    },
    {
      kind: 'obsidian',
      enabled: true,
      updated_at: null,
      obsidian: { vault_path: '/vault/RSS' },
    },
    { kind: 'feishu', enabled: true, updated_at: null, feishu: { webhook_url: '' } },
    {
      kind: 'custom_export',
      enabled: true,
      updated_at: null,
      custom_export: { endpoint: '' },
    },
  ],
};

const PROXY = { mode: 'http', url: '127.0.0.1:7890', no_proxy: 'localhost, *.internal' };

const RULES = [
  {
    id: 'r1',
    name: 'Rust 文章自动收藏',
    enabled: true,
    position: 1,
    trigger: 'item_arrived',
    condition: { field: 'title', op: 'contains', value: 'Rust' },
    action: { type: 'favorite' },
  },
  {
    id: 'r2',
    name: '长文标记稍后读',
    enabled: false,
    position: 2,
    trigger: 'item_arrived',
    condition: { field: 'word_count', op: 'gt', value: '3000' },
    action: { type: 'mark_unread' },
  },
];

function stubFetch() {
  return vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input);
    const body = url.includes('/api/integrations')
      ? INTEGRATIONS
      : url.includes('/api/proxy')
        ? PROXY
        : url.includes('/api/automation/rules')
          ? RULES
          : {};
    return { ok: true, status: 200, statusText: 'OK', json: async () => body } as Response;
  });
}

function renderTab(node: React.ReactNode) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <I18nProvider initialLocale="zh-CN">{node}</I18nProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => vi.stubGlobal('fetch', stubFetch()));
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('IntegrationsTab', () => {
  it('shows the RSSHub fields and masks secrets', async () => {
    renderTab(<IntegrationsTab />);

    await waitFor(() =>
      expect(screen.getByDisplayValue('http://192.168.1.20:1200')).toBeTruthy(),
    );
    expect(screen.getByDisplayValue('sec-••••••••1234')).toBeTruthy();
    expect(screen.getByDisplayValue('CACHE_TYPE=memory')).toBeTruthy();
    // 路由参数表：密文列是掩码（表格里是纯文本，不是输入框）
    expect(screen.getByText('cookie')).toBeTruthy();
    expect(screen.getByText('z_c0=••••••••')).toBeTruthy();
    expect(screen.getByText('20')).toBeTruthy();
  });

  it('lists the other three integrations with their configured values', async () => {
    renderTab(<IntegrationsTab />);
    // 「Obsidian」这类标题是静态文案，要等数据依赖的部分出现才说明加载完成
    await waitFor(() => expect(screen.getByText('/vault/RSS')).toBeTruthy());
    expect(screen.getByText('Obsidian')).toBeTruthy();
    expect(screen.getByText('飞书 Webhook')).toBeTruthy();
    expect(screen.getByText('自定义导出')).toBeTruthy();
    expect(screen.getAllByText('编辑')).toHaveLength(3);
  });

  it('switches a row into edit mode', async () => {
    renderTab(<IntegrationsTab />);
    await waitFor(() => expect(screen.getByText('/vault/RSS')).toBeTruthy());

    const row = screen.getByText('Obsidian').closest('div');
    const editButton = row?.querySelector('button');
    expect(editButton).toBeTruthy();
    fireEvent.click(editButton as HTMLElement);
    expect(await screen.findByText('保存')).toBeTruthy();
  });
});

describe('AutomationTab', () => {
  it('renders each rule with its when / if / then description', async () => {
    renderTab(<AutomationTab />);

    await waitFor(() => expect(screen.getByDisplayValue('Rust 文章自动收藏')).toBeTruthy());
    expect(screen.getByText('标题包含 “Rust”')).toBeTruthy();
    expect(screen.getByText('字数大于 “3000”')).toBeTruthy();
    expect(screen.getAllByText('新文章到达')).toHaveLength(2);
    expect(screen.getByText('加入收藏')).toBeTruthy();
    expect(screen.getByText('标记为未读')).toBeTruthy();
  });

  it('reflects enabled state and labels the three columns', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getAllByText('当')).toHaveLength(2));
    expect(screen.getAllByText('如果')).toHaveLength(2);
    expect(screen.getAllByText('则')).toHaveLength(2);

    const switches = screen.getAllByRole('switch');
    expect(switches.map((node) => node.getAttribute('aria-checked'))).toEqual(['true', 'false']);
  });

  it('opens the condition menu and offers value-bearing presets', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getByText('标题包含 “Rust”')).toBeTruthy());

    fireEvent.click(screen.getByText('标题包含 “Rust”'));
    expect(await screen.findByText('频道等于')).toBeTruthy();
    expect(screen.getByText('来源包含')).toBeTruthy();
  });
});

describe('ProxyTab', () => {
  it('renders the four modes with the active one selected', async () => {
    renderTab(<ProxyTab />);

    await waitFor(() => expect(screen.getByText('默认（跟随系统）')).toBeTruthy());
    for (const label of ['本地 HTTP 代理', '本地 HTTPS 代理', '自定义']) {
      expect(screen.getByText(label)).toBeTruthy();
    }

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(4);
    expect(radios.map((node) => node.getAttribute('aria-checked'))).toEqual([
      'false',
      'true',
      'false',
      'false',
    ]);
  });

  it('shows the proxy url and NO_PROXY values', async () => {
    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByDisplayValue('127.0.0.1:7890')).toBeTruthy());
    expect(screen.getByDisplayValue('localhost, *.internal')).toBeTruthy();
  });

  it('reports the test result', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/proxy/test')) {
        return {
          ok: true,
          status: 200,
          statusText: 'OK',
          json: async () => ({ ok: true, message: '连接正常 · 经由 127.0.0.1:7890', latency_ms: 32 }),
        } as Response;
      }
      const body = url.includes('/api/proxy') ? PROXY : {};
      return { ok: true, status: 200, statusText: 'OK', json: async () => body } as Response;
    });
    vi.stubGlobal('fetch', fetchMock);

    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByText('测试连接')).toBeTruthy());
    fireEvent.click(screen.getByText('测试连接'));

    expect(await screen.findByText(/连接正常.*32ms/)).toBeTruthy();
  });
});
