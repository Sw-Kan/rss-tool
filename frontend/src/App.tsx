import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RouterProvider } from 'react-router-dom';
import * as Tooltip from '@radix-ui/react-tooltip';
import { useState } from 'react';

import { I18nProvider } from './lib/i18n';
import { router } from './router';
import { ApiError } from './api/client';

export function App() {
  // 401 不重试：cookie 过期就交给路由守卫跳登录页
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: (failureCount, error) =>
              error instanceof ApiError && error.status === 401 ? false : failureCount < 2,
            refetchOnWindowFocus: false,
            staleTime: 15_000,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={client}>
      <I18nProvider>
        <Tooltip.Provider delayDuration={300}>
          <RouterProvider router={router} />
        </Tooltip.Provider>
      </I18nProvider>
    </QueryClientProvider>
  );
}
