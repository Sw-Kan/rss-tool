import { Navigate, createBrowserRouter, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';

import { useMe } from './api/hooks';
import { zhCN } from './lib/i18n/zh-CN';
import { LoginPage } from './features/auth/LoginPage';
import { AppShell } from './features/shell/AppShell';
import { ReaderPage } from './features/reader/ReaderPage';

function Splash() {
  return (
    <div className="flex h-full items-center justify-center text-sm text-ink-3">
      {zhCN.loading}
    </div>
  );
}

/** 未登录一律回登录页；查询态不闪屏。 */
function RequireAuth({ children }: { children: ReactNode }) {
  const me = useMe();
  const location = useLocation();

  if (me.isPending) return <Splash />;
  if (me.isError || !me.data) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }
  return <>{children}</>;
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Navigate to="/reader" replace /> },
      { path: 'reader', element: <ReaderPage /> },
      { path: '*', element: <Navigate to="/reader" replace /> },
    ],
  },
]);
