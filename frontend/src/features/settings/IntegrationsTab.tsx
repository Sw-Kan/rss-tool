import { Pencil, Plus, RefreshCw } from 'lucide-react';
import { useEffect, useState } from 'react';

import { useIntegrations, useTestRsshub, useUpdateIntegration } from '../../api/hooks';
import { Button } from '../../components/Button';
import { Switch } from '../../components/Field';
import { useT } from '../../lib/i18n';
import type { RsshubConfig, RsshubParam } from '../../types';
import { CustomExportDialog, ParamDialog } from './IntegrationDialogs';

export function IntegrationsTab() {
  const t = useT();
  const integrations = useIntegrations();
  const update = useUpdateIntegration();
  const test = useTestRsshub();

  const [status, setStatus] = useState<string | null>(null);
  const [paramIndex, setParamIndex] = useState<number | null>(null);
  const [paramOpen, setParamOpen] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  const row = (kind: string) => integrations.data?.items.find((item) => item.kind === kind);
  const rsshub = row('rsshub')?.rsshub;
  const params = rsshub?.params ?? [];
  const currentRsshub = (): RsshubConfig =>
    rsshub ?? { base_url: '', access_key: '', env: '', params: [] };

  const [baseUrl, setBaseUrl] = useState('');
  const [accessKey, setAccessKey] = useState('');
  const [env, setEnv] = useState('');

  useEffect(() => {
    if (!rsshub) return;
    setBaseUrl(rsshub.base_url);
    setAccessKey(rsshub.access_key);
    setEnv(rsshub.env);
  }, [rsshub]);

  const saveRsshub = (patch: Partial<RsshubConfig> = {}) => {
    update.mutate({
      kind: 'rsshub',
      rsshub: { ...currentRsshub(), base_url: baseUrl, access_key: accessKey, env, ...patch },
    });
  };

  return (
    <div className="space-y-6">
      <section>
        <div className="mb-3 flex items-center gap-3">
          <h3 className="flex-1 text-sm font-semibold text-ink">{t.integrations.rsshubTitle}</h3>
          <Switch
            checked={row('rsshub')?.enabled ?? true}
            label={t.integrations.rsshubTitle}
            onChange={(enabled) => update.mutate({ kind: 'rsshub', enabled })}
          />
        </div>

        <div className="rounded-xl border border-line bg-page px-4 py-3">
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label={t.integrations.testConnection}
              disabled={test.isPending}
              onClick={() =>
                test.mutate(undefined, {
                  onSuccess: (result) =>
                    setStatus(
                      result.latency_ms !== null
                        ? `${result.message} · ${result.latency_ms}ms`
                        : result.message,
                    ),
                  onError: (cause) =>
                    setStatus(cause instanceof Error ? cause.message : t.error),
                })
              }
              className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded text-ink-3 transition-colors hover:text-brand-ink disabled:opacity-50"
            >
              <RefreshCw size={15} className={test.isPending ? 'animate-spin' : ''} />
            </button>
            <span
              className={`text-[11.5px] ${
                status && test.data && !test.data.ok ? 'text-danger-ink' : 'text-ink-2'
              }`}
            >
              {status ?? (test.isPending ? t.integrations.testing : t.integrations.rsshubHint)}
            </span>
          </div>

          <div className="mt-3 grid grid-cols-[300px_1fr] gap-3">
            <MiniInput
              label={t.integrations.serviceUrl}
              value={baseUrl}
              placeholder={t.integrations.serviceUrlPlaceholder}
              onChange={setBaseUrl}
              onCommit={() => saveRsshub()}
            />
            <MiniInput
              label={t.integrations.accessKey}
              value={accessKey}
              placeholder={t.integrations.accessKeyPlaceholder}
              onChange={setAccessKey}
              onCommit={() => saveRsshub()}
            />
          </div>

          <div className="mt-3">
            <MiniInput
              label={t.integrations.envLabel}
              value={env}
              placeholder={t.integrations.envPlaceholder}
              onChange={setEnv}
              onCommit={() => saveRsshub()}
            />
          </div>
        </div>
      </section>

      <section>
        <div className="mb-2 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink">{t.integrations.routeParams}</h3>
          <Button
            size="sm"
            variant="soft"
            icon={<Plus size={14} />}
            onClick={() => {
              setParamIndex(null);
              setParamOpen(true);
            }}
          >
            {t.integrations.addParam}
          </Button>
        </div>

        <p className="mb-3 text-2xs text-ink-2">{t.integrations.routeParamsHint}</p>

        {params.length === 0 ? (
          <p className="rounded-lg border border-dashed border-line px-4 py-3 text-center text-2xs text-ink-3">
            {t.integrations.noParams}
          </p>
        ) : (
          <div className="rounded-xl border border-line">
            <div className="flex items-center gap-2 border-b border-line px-4 py-2 text-2xs font-semibold text-ink-3">
              <span className="w-44">{t.integrations.colName}</span>
              <span className="flex-1">{t.integrations.colScope}</span>
              <span className="w-56">{t.integrations.colValue}</span>
              <span className="w-6" />
            </div>
            {params.map((param, index) => (
              <div
                key={`${param.name}-${index}`}
                className={`flex h-10 items-center gap-2 px-4 ${
                  index > 0 ? 'border-t border-line' : ''
                }`}
              >
                <span className="w-44 truncate text-xs font-medium text-ink">{param.name}</span>
                <span className="flex-1 truncate text-[11.5px] text-ink-2">{param.scope}</span>
                <span className="w-56 truncate text-[11.5px] text-ink-2">{param.value}</span>
                <button
                  type="button"
                  aria-label={t.integrations.edit}
                  onClick={() => {
                    setParamIndex(index);
                    setParamOpen(true);
                  }}
                  className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-ink-3 hover:bg-subtle hover:text-ink"
                >
                  <Pencil size={14} />
                </button>
              </div>
            ))}
          </div>
        )}

        <p className="mt-2 text-2xs text-ink-3">{t.integrations.paramsNote}</p>
      </section>

      <section>
        <h3 className="mb-2 text-sm font-semibold text-ink">{t.integrations.otherTitle}</h3>
        <div className="rounded-xl border border-line">
          <OtherRow
            kind="obsidian"
            title={t.integrations.obsidian}
            label={t.integrations.obsidianLabel}
            value={row('obsidian')?.obsidian?.vault_path ?? ''}
            placeholder={t.integrations.obsidianPlaceholder}
            onSave={(next) => update.mutate({ kind: 'obsidian', obsidian: { vault_path: next } })}
          />
          <OtherRow
            kind="feishu"
            title={t.integrations.feishu}
            label={t.integrations.feishuLabel}
            value={row('feishu')?.feishu?.webhook_url ?? ''}
            placeholder={t.integrations.feishuPlaceholder}
            onSave={(next) => update.mutate({ kind: 'feishu', feishu: { webhook_url: next } })}
          />
          <div className="flex h-10 items-center gap-3 border-t border-line px-4">
            <span className="w-32 shrink-0 text-xs font-medium text-ink">
              {t.integrations.customExport}
            </span>
            <span className="w-16 shrink-0 text-2xs text-ink-3">
              {t.integrations.customExportLabel}
            </span>
            <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-2">
              {row('custom_export')?.custom_export?.endpoint || '—'}
            </span>
            <button
              type="button"
              onClick={() => setExportOpen(true)}
              className="inline-flex h-7 shrink-0 items-center rounded-lg border border-line bg-surface px-3 text-xs font-semibold text-ink transition-colors hover:bg-subtle"
            >
              {t.integrations.edit}
            </button>
          </div>
        </div>
      </section>

      <ParamDialog
        open={paramOpen}
        onOpenChange={setParamOpen}
        index={paramIndex}
        param={paramIndex === null ? null : (params[paramIndex] ?? null)}
        onSave={(param: RsshubParam, index) => {
          const next =
            index === null
              ? [...params, param]
              : params.map((item, i) => (i === index ? param : item));
          saveRsshub({ params: next });
        }}
        onRemove={(index) => saveRsshub({ params: params.filter((_, i) => i !== index) })}
      />

      <CustomExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        config={
          row('custom_export')?.custom_export ?? { endpoint: '', schema_template: '' }
        }
      />
    </div>
  );
}

const MINI_INPUT =
  'h-[34px] w-full rounded-lg border border-line bg-surface px-2.5 text-[11.5px] text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-brand';

function MiniInput({
  label,
  value,
  placeholder,
  onChange,
  onCommit,
}: {
  label: string;
  value: string;
  placeholder: string;
  onChange: (next: string) => void;
  onCommit: () => void;
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-[10.5px] text-ink-3">{label}</span>
      <input
        value={value}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onCommit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') event.currentTarget.blur();
        }}
        className={MINI_INPUT}
      />
    </label>
  );
}

interface OtherRowProps {
  kind: string;
  title: string;
  label: string;
  value: string;
  placeholder: string;
  onSave: (next: string) => void;
}

function OtherRow({ title, label, value, placeholder, onSave }: OtherRowProps) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  useEffect(() => setDraft(value), [value]);

  const commit = () => {
    setEditing(false);
    if (draft.trim() !== value) onSave(draft.trim());
  };

  return (
    <div className="flex h-10 items-center gap-3 border-t border-line px-4 first:border-t-0">
      <span className="w-32 shrink-0 text-xs font-medium text-ink">{title}</span>
      <span className="w-16 shrink-0 text-2xs text-ink-3">{label}</span>
      {editing ? (
        <input
          autoFocus
          value={draft}
          placeholder={placeholder}
          onChange={(event) => setDraft(event.target.value)}
          onBlur={commit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') event.currentTarget.blur();
            if (event.key === 'Escape') {
              setDraft(value);
              setEditing(false);
            }
          }}
          className={`${MINI_INPUT} h-7 flex-1 text-xs`}
        />
      ) : (
        <>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-2">{value || '—'}</span>
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="inline-flex h-7 shrink-0 items-center rounded-lg border border-line bg-surface px-3 text-xs font-semibold text-ink transition-colors hover:bg-subtle"
          >
            {t.integrations.edit}
          </button>
        </>
      )}
    </div>
  );
}
