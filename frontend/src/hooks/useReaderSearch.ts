import { useCallback, useMemo } from 'react';
import { useSearchParams } from 'react-router-dom';

import { parseSearch, toSearchParams } from '../lib/scope';
import type { ReaderSearch } from '../types';

/**
 * 阅读器视图状态存 URL 查询串。update 会保留 `settings` 深链参数，
 * 这样打开设置弹窗时不会丢掉当前的过滤条件。
 */
export function useReaderSearch() {
  const [params, setParams] = useSearchParams();
  const search = useMemo(() => parseSearch(params), [params]);

  const update = useCallback(
    (next: ReaderSearch, options?: { replace?: boolean }) => {
      const merged = toSearchParams(next);
      const settings = params.get('settings');
      if (settings) merged.set('settings', settings);
      setParams(merged, { replace: options?.replace ?? false });
    },
    [params, setParams],
  );

  return { search, update };
}
