// @vitest-environment jsdom
/** 三个面板 + 新增弹窗的冒烟与回归测试。 */
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
    { kind: 'obsidian', enabled: true, updated_at: null, obsidian: { vault_path: '/vault/RSS' } },
    { kind: 'feishu', enabled: true, updated_at: null, feishu: { webhook_url: '' } },
    {
      kind: 'custom_export',
      enabled: true,
      updated_at: null,
      custom_export: { endpoint: 'https://api.example.com/x', schema_template: '{"t":"{{title}}"}' },
    },
  ],
};

const PROXY = {
  mode: 'custom',
  http_url: 'http://127.0.0.1:7890',
  https_url: '',
  socks5_url: 'socks5://10.0.0.8:1080',
  no_proxy: 'localhost, *.internal',
};

const RULES = [
  {
    id: 'r1',
    name: 'Rust 长文自动收藏',
    enabled: true,
    position: 1,
    trigger: 'item_arrived',
    schedule_time: null,
    join: 'and',
    conditions: [
      { field: 'title', op: 'contains', value: 'Rust' },
      { field: 'word_count', op: 'gt', value: '3000' },
    ],
    action: { type: 'favorite' },
  },
  {
    id: 'r2',
    name: '每天早八点推送飞书',
    enabled: false,
    position: 2,
    trigger: 'schedule',
    schedule_time: '08:00',
    join: 'or',
    conditions: [{ field: 'kind', op: 'eq', value: 'article' }],
    action: { type: 'feishu' },
  },
];

interface Call {
  url: string;
  method: string;
  body: unknown;
}

let calls: Call[] = [];

function json(body: unknown): Response {
  return { ok: true, status: 200, statusText: 'OK', json: async () => body } as Response;
}

function stubFetch() {
  return vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({
      url,
      method: (init?.method ?? 'GET').toUpperCase(),
      body: typeof init?.body === 'string' ? JSON.parse(init.body) : init?.body,
    });
    if (url.includes('/api/integrations')) return json(INTEGRATIONS);
    if (url.includes('/api/proxy')) return json(PROXY);
    if (url.includes('/api/automation/rules')) return json(RULES);
    return json({});
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

beforeEach(() => {
  calls = [];
  vi.stubGlobal('fetch', stubFetch());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe('IntegrationsTab', () => {
  it('shows the RSSHub fields with masked secrets', async () => {
    renderTab(<IntegrationsTab />);
    await waitFor(() =>
      expect(screen.getByDisplayValue('http://192.168.1.20:1200')).toBeTruthy(),
    );
    expect(screen.getByDisplayValue('sec-••••••••1234')).toBeTruthy();
    expect(screen.getByText('z_c0=••••••••')).toBeTruthy();
    expect(screen.getByText('20')).toBeTruthy();
  });

  it('lists the other integrations with their configured values', async () => {
    renderTab(<IntegrationsTab />);
    await waitFor(() => expect(screen.getByText('/vault/RSS')).toBeTruthy());
    expect(screen.getByText('飞书 Webhook')).toBeTruthy();
    expect(screen.getByText('https://api.example.com/x')).toBeTruthy();
    expect(screen.getAllByText('编辑')).toHaveLength(3);
  });

  it('adds a route parameter through the dialog', async () => {
    // 回归：以前「添加参数」会立刻 PUT 一条空 name 的参数，被 422 挡下，参数永远存不进去
    renderTab(<IntegrationsTab />);
    await waitFor(() => expect(screen.getByText('添加参数')).toBeTruthy());

    fireEvent.click(screen.getByText('添加参数'));
    await waitFor(() => expect(screen.getByLabelText('参数名')).toBeTruthy());

    fireEvent.change(screen.getByLabelText('参数名'), { target: { value: 'limit' } });
    fireEvent.change(screen.getByLabelText('作用范围'), { target: { value: '/twitter/user' } });
    fireEvent.change(screen.getByLabelText('值'), { target: { value: '20' } });
    fireEvent.click(screen.getByText('保存'));

    await waitFor(() => {
      const put = calls.find((call) => call.method === 'PUT');
      expect(put).toBeTruthy();
      const params = (put?.body as { rsshub: { params: unknown[] } }).rsshub.params;
      expect(params).toHaveLength(3);
      expect(params[2]).toEqual({ name: 'limit', scope: '/twitter/user', value: '20', secret: false });
    });
  });

  it('does not PUT before the dialog is saved', async () => {
    renderTab(<IntegrationsTab />);
    await waitFor(() => expect(screen.getByText('添加参数')).toBeTruthy());

    fireEvent.click(screen.getByText('添加参数'));
    await waitFor(() => expect(screen.getByLabelText('参数名')).toBeTruthy());

    expect(calls.some((call) => call.method === 'PUT')).toBe(false);
  });

  it('edits a route parameter in place', async () => {
    renderTab(<IntegrationsTab />);
    await waitFor(() => expect(screen.getByText('cookie')).toBeTruthy());

    fireEvent.click(screen.getAllByLabelText('编辑')[0] as HTMLElement);
    await waitFor(() => expect(screen.getByLabelText('参数名')).toBeTruthy());
    expect((screen.getByLabelText('参数名') as HTMLInputElement).value).toBe('cookie');
    expect((screen.getByLabelText('作用范围') as HTMLInputElement).value).toBe('/zhihu');
  });

  it('opens the custom export dialog with endpoint and schema', async () => {
    renderTab(<IntegrationsTab />);
    await waitFor(() => expect(screen.getByText('https://api.example.com/x')).toBeTruthy());

    fireEvent.click(screen.getAllByText('编辑')[2] as HTMLElement);
    await waitFor(() => expect(screen.getByText('Schema（JSON 模板）')).toBeTruthy());
    expect(screen.getByDisplayValue('https://api.example.com/x')).toBeTruthy();
    expect(screen.getByDisplayValue('{"t":"{{title}}"}')).toBeTruthy();
    expect(screen.getByText('测试推送')).toBeTruthy();
  });
});

describe('AutomationTab', () => {
  it('renders rule name, trigger, conditions and action', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getByDisplayValue('Rust 长文自动收藏')).toBeTruthy());

    expect(screen.getByText('标题包含 “Rust”')).toBeTruthy();
    expect(screen.getByText('字数大于 “3000”')).toBeTruthy();
    expect(screen.getByText('并且')).toBeTruthy();
    expect(screen.getByText('加入收藏')).toBeTruthy();
  });

  it('labels the three columns and shows the schedule trigger with its time', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getAllByText('当')).toHaveLength(2));
    expect(screen.getAllByText('如果')).toHaveLength(2);
    expect(screen.getAllByText('则')).toHaveLength(2);

    expect(screen.getByText('每天早上 08:00')).toBeTruthy();
    expect(screen.getByDisplayValue('08:00')).toBeTruthy();
  });

  it('reflects each rule enabled state', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getAllByRole('switch')).toHaveLength(2));
    expect(
      screen.getAllByRole('switch').map((node) => node.getAttribute('aria-checked')),
    ).toEqual(['true', 'false']);
  });

  it('toggles the and/or join', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getByText('并且')).toBeTruthy());

    fireEvent.click(screen.getByText('并且'));

    await waitFor(() => {
      const patch = calls.find((call) => call.method === 'PATCH');
      expect((patch?.body as { join: string }).join).toBe('or');
    });
  });

  it('adds a condition', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getAllByText('+ 添加条件')).toHaveLength(2));

    fireEvent.click(screen.getAllByText('+ 添加条件')[0] as HTMLElement);

    await waitFor(() => {
      const patch = calls.find((call) => call.method === 'PATCH');
      const conditions = (patch?.body as { conditions: unknown[] }).conditions;
      expect(conditions).toHaveLength(3);
    });
  });

  it('deletes a rule through a confirm dialog, not a floating menu', async () => {
    renderTab(<AutomationTab />);
    await waitFor(() => expect(screen.getByDisplayValue('Rust 长文自动收藏')).toBeTruthy());

    fireEvent.click(screen.getAllByLabelText('删除规则')[0] as HTMLElement);
    await waitFor(() => expect(screen.getByText('删除规则？')).toBeTruthy());

    // 弹窗里点确认才真的删
    expect(calls.some((call) => call.method === 'DELETE')).toBe(false);
    fireEvent.click(screen.getByText('删除'));

    await waitFor(() => expect(calls.some((call) => call.method === 'DELETE')).toBe(true));
  });
});

describe('ProxyTab', () => {
  it('offers exactly two modes and marks the active one', async () => {
    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByText('系统代理')).toBeTruthy());

    const radios = screen.getAllByRole('radio');
    expect(radios).toHaveLength(2);
    expect(radios.map((node) => node.getAttribute('aria-checked'))).toEqual(['false', 'true']);
  });

  it('shows the four custom address fields', async () => {
    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByLabelText('HTTP 代理')).toBeTruthy());
    for (const label of ['HTTPS 代理', 'SOCKS5 代理', 'NO_PROXY']) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
    expect((screen.getByLabelText('HTTP 代理') as HTMLInputElement).value).toBe(
      'http://127.0.0.1:7890',
    );
    expect((screen.getByLabelText('NO_PROXY') as HTMLInputElement).value).toBe(
      'localhost, *.internal',
    );
  });

  it('hides the custom block in system mode', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => json({ ...PROXY, mode: 'system' })),
    );
    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByText('系统代理')).toBeTruthy());
    expect(screen.queryByLabelText('HTTP 代理')).toBeNull();
  });

  it('patches the mode when switching', async () => {
    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByText('系统代理')).toBeTruthy());

    fireEvent.click(screen.getByText('系统代理'));

    await waitFor(() => {
      const patch = calls.find((call) => call.method === 'PATCH');
      expect((patch?.body as { mode: string }).mode).toBe('system');
    });
  });

  it('commits an edited address on blur', async () => {
    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByLabelText('HTTPS 代理')).toBeTruthy());

    const input = screen.getByLabelText('HTTPS 代理');
    fireEvent.change(input, { target: { value: 'http://127.0.0.1:7891' } });
    fireEvent.blur(input);

    await waitFor(() => {
      const patch = calls.find((call) => call.method === 'PATCH');
      expect((patch?.body as { https_url: string }).https_url).toBe('http://127.0.0.1:7891');
    });
  });

  it('reports the test result', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/api/proxy/test')) {
          return json({ ok: true, message: '连接正常 · 经由 socks5://10.0.0.8:1080', latency_ms: 32 });
        }
        return json(PROXY);
      }),
    );
    renderTab(<ProxyTab />);
    await waitFor(() => expect(screen.getByText('测试连接')).toBeTruthy());
    fireEvent.click(screen.getByText('测试连接'));

    expect(await screen.findByText(/连接正常.*32ms/)).toBeTruthy();
  });
});
