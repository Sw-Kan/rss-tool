import { useEffect, useState } from 'react';

import { useProxyConfig, useTestProxy, useUpdateProxy } from '../../api/hooks';
import { Button } from '../../components/Button';
import { useT } from '../../lib/i18n';
import type { ProxyMode } from '../../types';

const MODE_META: { mode: ProxyMode; title: 'modeSystem' | 'modeCustom'; hint: string }[] = [
  { mode: 'system', title: 'modeSystem', hint: 'modeSystemHint' },
  { mode: 'custom', title: 'modeCustom', hint: 'modeCustomHint' },
];

/** 自定义代理下的四个地址字段。 */
const URL_FIELDS = [
  { key: 'http_url', label: 'httpUrl', placeholder: 'urlPlaceholder' },
  { key: 'https_url', label: 'httpsUrl', placeholder: 'urlPlaceholder' },
  { key: 'socks5_url', label: 'socks5Url', placeholder: 'socksPlaceholder' },
  { key: 'no_proxy', label: 'noProxy', placeholder: 'noProxyHint' },
] as const;

type UrlKey = (typeof URL_FIELDS)[number]['key'];

export function ProxyTab() {
  const t = useT();
  const config = useProxyConfig();
  const update = useUpdateProxy();
  const test = useTestProxy();

  const [drafts, setDrafts] = useState<Record<UrlKey, string>>({
    http_url: '',
    https_url: '',
    socks5_url: '',
    no_proxy: '',
  });

  useEffect(() => {
    if (!config.data) return;
    setDrafts({
      http_url: config.data.http_url,
      https_url: config.data.https_url,
      socks5_url: config.data.socks5_url,
      no_proxy: config.data.no_proxy,
    });
  }, [config.data]);

  if (!config.data) {
    return <p className="text-sm text-ink-3">{t.loading}</p>;
  }

  const mode = config.data.mode;

  const commit = (key: UrlKey) => {
    if (drafts[key] !== config.data?.[key]) update.mutate({ [key]: drafts[key] });
  };

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{t.proxy.modeTitle}</h3>
        <div className="space-y-2">
          {MODE_META.map((meta) => {
            const active = mode === meta.mode;
            return (
              <button
                key={meta.mode}
                type="button"
                role="radio"
                aria-checked={active}
                onClick={() => update.mutate({ mode: meta.mode })}
                className={`flex h-[52px] w-full items-center gap-3 rounded-[10px] px-4 text-left transition-colors ${
                  active ? 'bg-soft' : 'hover:bg-subtle'
                }`}
              >
                <span
                  className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
                    active ? 'border-brand bg-brand' : 'border-line-strong'
                  }`}
                >
                  {active ? <span className="h-2 w-2 rounded-full bg-surface" /> : null}
                </span>
                <span className="w-40 shrink-0 text-sm font-medium text-ink">{t.proxy[meta.title]}</span>
                <span className="min-w-0 flex-1 truncate text-2xs text-ink-2">
                  {t.proxy[meta.hint as 'modeSystemHint']}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {mode === 'custom' ? (
        <section className="rounded-xl border border-line bg-page px-4 py-4">
          <div className="grid grid-cols-2 gap-4">
            {URL_FIELDS.map((field) => (
              <label key={field.key} className="block min-w-0">
                <span className="mb-1 block text-[10.5px] text-ink-3">{t.proxy[field.label]}</span>
                <input
                  aria-label={t.proxy[field.label]}
                  value={drafts[field.key]}
                  placeholder={t.proxy[field.placeholder as 'urlPlaceholder']}
                  onChange={(event) =>
                    setDrafts((previous) => ({ ...previous, [field.key]: event.target.value }))
                  }
                  onBlur={() => commit(field.key)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') event.currentTarget.blur();
                  }}
                  className="h-[34px] w-full rounded-lg border border-line bg-surface px-2.5 text-[11.5px] text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-brand"
                />
              </label>
            ))}
          </div>

          <div className="mt-4 flex items-center gap-3">
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
                <span className={`h-3 w-3 rounded-full ${test.data.ok ? 'bg-success' : 'bg-danger'}`} />
                {test.data.ok && test.data.latency_ms !== null
                  ? `${test.data.message} · ${test.data.latency_ms}ms`
                  : test.data.message}
              </span>
            ) : null}
          </div>
        </section>
      ) : null}

      <p className="text-2xs text-ink-3">{t.proxy.hint}</p>
    </div>
  );
}
