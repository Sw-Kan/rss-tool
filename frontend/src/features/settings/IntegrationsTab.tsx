import { Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import { useIntegrations, useTestRsshub, useUpdateIntegration } from '../../api/hooks';
import { Button } from '../../components/Button';
import { Switch } from '../../components/Field';
import { useT } from '../../lib/i18n';
import type { RsshubConfig, RsshubParam } from '../../types';

const EMPTY_PARAM: RsshubParam = { name: '', scope: '', value: '', secret: false };

export function IntegrationsTab() {
  const t = useT();
  const integrations = useIntegrations();
  const update = useUpdateIntegration();
  const test = useTestRsshub();

  const [status, setStatus] = useState<string | null>(null);
  const [editing, setEditing] = useState<number | null>(null);
  const [editingOther, setEditingOther] = useState<string | null>(null);

  const row = (kind: string) => integrations.data?.items.find((item) => item.kind === kind);
  const rsshub = row('rsshub')?.rsshub;
  const params = rsshub?.params ?? [];
  const currentRsshub = (): RsshubConfig =>
    rsshub ?? { base_url: '', access_key: '', env: '', params: [] };

  // 本地草稿：密文字段后端只回传掩码，不能每次输入都立刻提交
  const [baseUrl, setBaseUrl] = useState('');
  const [accessKey, setAccessKey] = useState('');
  const [env, setEnv] = useState('');
  const [draft, setDraft] = useState<RsshubParam | null>(null);

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

  const commitParams = (params: RsshubParam[]) => saveRsshub({ params });

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
            <span className="text-[11.5px] text-ink-2">
              {status ?? (test.isPending ? t.integrations.testing : t.integrations.rsshubHint)}
            </span>
          </div>

          <div className="mt-3 grid grid-cols-[300px_1fr] gap-3">
            <MiniInput
              label={t.integrations.serviceUrl}
              value={baseUrl}
              placeholder={t.integrations.serviceUrlPlaceholder}
              onChange={setBaseUrl}
              onCommit={() => saveRsshub({})}
            />
            <MiniInput
              label={t.integrations.accessKey}
              value={accessKey}
              placeholder={t.integrations.accessKeyPlaceholder}
              onChange={setAccessKey}
              onCommit={() => saveRsshub({})}
            />
          </div>

          <div className="mt-3">
            <MiniInput
              label={t.integrations.envLabel}
              value={env}
              placeholder={t.integrations.envPlaceholder}
              onChange={setEnv}
              onCommit={() => saveRsshub({})}
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
              const next = [...params, EMPTY_PARAM];
              commitParams(next);
              setEditing(next.length - 1);
              setDraft(EMPTY_PARAM);
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
                key={index}
                className={`flex items-center gap-2 px-4 py-2.5 ${
                  index > 0 ? 'border-t border-line' : ''
                }`}
              >
                {editing === index && draft ? (
                  <>
                    <input
                      autoFocus
                      value={draft.name}
                      placeholder={t.integrations.namePlaceholder}
                      onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                      className={EDIT_INPUT}
                    />
                    <input
                      value={draft.scope}
                      placeholder={t.integrations.scopePlaceholder}
                      onChange={(event) => setDraft({ ...draft, scope: event.target.value })}
                      className={EDIT_INPUT}
                    />
                    <input
                      value={draft.value}
                      placeholder={t.integrations.valuePlaceholder}
                      onChange={(event) => setDraft({ ...draft, value: event.target.value })}
                      className={EDIT_INPUT}
                    />
                    <label className="flex shrink-0 items-center gap-1 text-2xs text-ink-3">
                      <input
                        type="checkbox"
                        checked={draft.secret}
                        onChange={(event) => setDraft({ ...draft, secret: event.target.checked })}
                      />
                      {t.integrations.markSecret}
                    </label>
                    <button
                      type="button"
                      className="shrink-0 text-2xs font-semibold text-brand-ink"
                      onClick={() => {
                        commitParams(params.map((item, i) => (i === index ? draft : item)));
                        setEditing(null);
                        setDraft(null);
                      }}
                    >
                      {t.integrations.save}
                    </button>
                  </>
                ) : (
                  <>
                    <span className="w-44 truncate text-xs font-medium text-ink">{param.name}</span>
                    <span className="flex-1 truncate text-[11.5px] text-ink-2">{param.scope}</span>
                    <span className="w-56 truncate text-[11.5px] text-ink-2">{param.value}</span>
                    <button
                      type="button"
                      aria-label={t.integrations.edit}
                      className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-ink-3 hover:bg-subtle hover:text-ink"
                      onClick={() => {
                        setEditing(index);
                        setDraft(param);
                      }}
                    >
                      <Pencil size={14} />
                    </button>
                    <button
                      type="button"
                      aria-label={t.integrations.removeRow}
                      className="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-ink-3 hover:bg-subtle hover:text-danger-ink"
                      onClick={() => commitParams(params.filter((_, i) => i !== index))}
                    >
                      <Trash2 size={14} />
                    </button>
                  </>
                )}
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
            editing={editingOther === 'obsidian'}
            onEdit={setEditingOther}
            onSave={(next) => {
              update.mutate({ kind: 'obsidian', obsidian: { vault_path: next } });
              setEditingOther(null);
            }}
          />
          <OtherRow
            kind="feishu"
            title={t.integrations.feishu}
            label={t.integrations.feishuLabel}
            value={row('feishu')?.feishu?.webhook_url ?? ''}
            placeholder={t.integrations.feishuPlaceholder}
            editing={editingOther === 'feishu'}
            onEdit={setEditingOther}
            onSave={(next) => {
              update.mutate({ kind: 'feishu', feishu: { webhook_url: next } });
              setEditingOther(null);
            }}
          />
          <OtherRow
            kind="custom_export"
            title={t.integrations.customExport}
            label={t.integrations.customExportLabel}
            value={row('custom_export')?.custom_export?.endpoint ?? ''}
            placeholder={t.integrations.customExportPlaceholder}
            editing={editingOther === 'custom_export'}
            onEdit={setEditingOther}
            onSave={(next) => {
              update.mutate({ kind: 'custom_export', custom_export: { endpoint: next } });
              setEditingOther(null);
            }}
          />
        </div>
      </section>
    </div>
  );
}

const EDIT_INPUT =
  'min-w-0 flex-1 rounded-md border border-line bg-surface px-2 py-1 text-[11.5px] text-ink outline-none focus:border-brand';

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
        className="h-[34px] w-full rounded-lg border border-line bg-surface px-2.5 text-[11.5px] text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-brand"
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
  editing: boolean;
  onEdit: (kind: string | null) => void;
  onSave: (next: string) => void;
}

function OtherRow({
  kind,
  title,
  label,
  value,
  placeholder,
  editing,
  onEdit,
  onSave,
}: OtherRowProps) {
  const t = useT();
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);

  return (
    <div className="flex h-10 items-center gap-3 border-t border-line px-4 first:border-t-0">
      <span className="w-32 shrink-0 text-xs font-medium text-ink">{title}</span>
      <span className="w-16 shrink-0 text-2xs text-ink-3">{label}</span>
      {editing ? (
        <>
          <input
            autoFocus
            value={draft}
            placeholder={placeholder}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') onSave(draft.trim());
              if (event.key === 'Escape') onEdit(null);
            }}
            className={EDIT_INPUT}
          />
          <button
            type="button"
            className="shrink-0 text-2xs font-semibold text-brand-ink"
            onClick={() => onSave(draft.trim())}
          >
            {t.integrations.save}
          </button>
        </>
      ) : (
        <>
          <span className="min-w-0 flex-1 truncate text-[11.5px] text-ink-2">
            {value || '—'}
          </span>
          <button
            type="button"
            onClick={() => onEdit(kind)}
            className="inline-flex h-7 shrink-0 items-center rounded-lg border border-line bg-surface px-3 text-xs font-semibold text-ink transition-colors hover:bg-subtle"
          >
            {t.integrations.edit}
          </button>
        </>
      )}
    </div>
  );
}
