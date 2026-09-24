import { useEffect, useState } from 'react';

import { useProxyConfig, useTestProxy, useUpdateProxy } from '../../api/hooks';
import { Button } from '../../components/Button';
import { useT } from '../../lib/i18n';
import type { ProxyMode } from '../../types';

const MODES: ProxyMode[] = ['system', 'http', 'https', 'custom'];

const MODE_TEXT: Record<
  ProxyMode,
  { title: 'modeSystem' | 'modeHttp' | 'modeHttps' | 'modeCustom'; hint: string; placeholder: string | null }
> = {
  system: {
    title: 'modeSystem',
    hint: 'modeSystemHint',
    placeholder: null,
  },
  http: { title: 'modeHttp', hint: 'modeHttpHint', placeholder: '127.0.0.1:7890' },
  https: { title: 'modeHttps', hint: 'modeHttpsHint', placeholder: '127.0.0.1:7890' },
  custom: {
    title: 'modeCustom',
    hint: 'modeCustomHint',
    placeholder: 'socks5://10.0.0.8:1080',
  },
};

export function ProxyTab() {
  const t = useT();
  const config = useProxyConfig();
  const update = useUpdateProxy();
  const test = useTestProxy();

  const [url, setUrl] = useState('');
  const [noProxy, setNoProxy] = useState('');

  useEffect(() => {
    if (!config.data) return;
    setUrl(config.data.url);
    setNoProxy(config.data.no_proxy);
  }, [config.data]);

  if (!config.data) {
    return <p className="text-sm text-ink-3">{t.loading}</p>;
  }

  const mode = config.data.mode;

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{t.proxy.modeTitle}</h3>
        <div className="space-y-2">
          {MODES.map((option) => {
            const meta = MODE_TEXT[option];
            const active = mode === option;
            return (
              <div
                key={option}
                className={`flex h-[52px] items-center gap-3 rounded-lg px-4 transition-colors ${
                  active ? 'bg-soft' : 'hover:bg-subtle'
                }`}
              >
                <button
                  type="button"
                  role="radio"
                  aria-checked={active}
                  aria-label={t.proxy[meta.title]}
                  onClick={() => update.mutate({ mode: option })}
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                    active ? 'border-brand' : 'border-line-strong'
                  }`}
                >
                  {active ? <span className="h-2 w-2 rounded-full bg-brand" /> : null}
                </button>

                <span className="w-40 shrink-0">
                  <span className="block text-sm font-medium text-ink">{t.proxy[meta.title]}</span>
                </span>
                <span className="min-w-0 flex-1 truncate text-2xs text-ink-2">
                  {t.proxy[meta.hint as 'modeSystemHint']}
                </span>

                {meta.placeholder ? (
                  <input
                    aria-label={`${t.proxy[meta.title]} URL`}
                    value={active ? url : ''}
                    placeholder={meta.placeholder}
                    disabled={!active}
                    onChange={(event) => setUrl(event.target.value)}
                    onBlur={() => {
                      if (active && url !== config.data.url) update.mutate({ url });
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') event.currentTarget.blur();
                    }}
                    className="h-8 w-[228px] shrink-0 rounded-lg border border-line bg-surface px-2.5 text-[11.5px] text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-brand disabled:opacity-50"
                  />
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h3 className="text-sm font-semibold text-ink">{t.proxy.noProxyTitle}</h3>
        <p className="mt-1 mb-2 text-2xs text-ink-2">{t.proxy.noProxyHint}</p>
        <input
          value={noProxy}
          placeholder={t.proxy.noProxyPlaceholder}
          onChange={(event) => setNoProxy(event.target.value)}
          onBlur={() => {
            if (noProxy !== config.data.no_proxy) update.mutate({ no_proxy: noProxy });
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') event.currentTarget.blur();
          }}
          className="h-10 w-full rounded-lg border border-line bg-surface px-3 text-xs text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-brand"
        />
      </section>

      <section className="flex items-center gap-3">
        <Button
          className="h-9 px-4 text-xs"
          disabled={test.isPending}
          onClick={() => test.mutate()}
        >
          {test.isPending ? t.proxy.testing : t.proxy.test}
        </Button>

        {test.data ? (
          <span
            className={`inline-flex h-9 items-center gap-2 rounded-full px-4 text-[11.5px] font-medium ${
              test.data.ok ? 'bg-success-soft text-success-ink' : 'bg-danger-soft text-danger-ink'
            }`}
          >
            <span
              className={`h-3 w-3 rounded-full ${test.data.ok ? 'bg-success' : 'bg-danger'}`}
            />
            {test.data.ok && test.data.latency_ms !== null
              ? `${test.data.message} · ${test.data.latency_ms}ms`
              : test.data.message}
          </span>
        ) : null}
      </section>

      <p className="text-2xs text-ink-3">{t.proxy.hint}</p>
    </div>
  );
}
