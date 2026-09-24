// @vitest-environment jsdom
/** 登录页渲染冒烟测试：验证 provider / 路由 / Radix 接线没坏。
 *  不做交互断言（请求层由后端 pytest 覆盖）。 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it } from 'vitest';

import { LoginPage } from './LoginPage';

// vitest 未开启 globals，RTL 的自动清理不会注册，需手动挂上
afterEach(cleanup);

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LoginPage', () => {
  it('renders branding, both tabs and the skip action', () => {
    renderPage();

    expect(screen.getByText('RSS Reader')).toBeTruthy();
    expect(screen.getByText('自托管 RSS 阅读器')).toBeTruthy();
    expect(screen.getByRole('tab', { name: '登录' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: '注册' })).toBeTruthy();
    expect(screen.getByRole('button', { name: '跳过，以 user 身份进入' })).toBeTruthy();
    expect(screen.getByText(/仅保存在本地/)).toBeTruthy();
  });

  it('wires the tab trigger to a real tabpanel', () => {
    renderPage();
    const panel = screen.getByRole('tabpanel');
    expect(panel.getAttribute('aria-labelledby')).toBe(
      screen.getByRole('tab', { name: '登录' }).id,
    );
  });

  it('exposes email and password fields', () => {
    renderPage();
    expect(screen.getByPlaceholderText('user@example.com')).toBeTruthy();
    expect(screen.getByPlaceholderText('••••••••')).toBeTruthy();
  });
});
