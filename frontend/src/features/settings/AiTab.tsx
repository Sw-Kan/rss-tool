import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { MoreHorizontal, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';

import {
  useAiConfig,
  useAiPresets,
  useAiUsage,
  useCreateAiProvider,
  useDeleteAiProvider,
  useUpdateAiProvider,
  useUpdateSettings,
} from '../../api/hooks';
import { Button } from '../../components/Button';
import { MiniField, Switch } from '../../components/Field';
import { thousands } from '../../lib/format';
import { strings } from '../../lib/strings';
import type { AiProvider } from '../../types';

export function AiTab() {
  const config = useAiConfig();
  const usage = useAiUsage();
  const presets = useAiPresets();
  const createProvider = useCreateAiProvider();
  const updateProvider = useUpdateAiProvider();
  const deleteProvider = useDeleteAiProvider();
  const updateSettings = useUpdateSettings();

  const [limitDraft, setLimitDraft] = useState<string | null>(null);

  const providers = config.data?.providers ?? [];
  const limit = config.data?.token_limit ?? 0;
  const used = usage.data?.month_tokens ?? 0;
  const ratio = limit > 0 ? Math.min(1, used / limit) : 0;

  return (
    <div className="space-y-7">
      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink">{strings.ai.providers}</h3>
          <DropdownMenu.Root>
            <DropdownMenu.Trigger asChild>
              <Button
                size="sm"
                variant="soft"
                icon={<Plus size={14} />}
                disabled={createProvider.isPending}
              >
                {strings.ai.addProvider}
              </Button>
            </DropdownMenu.Trigger>
            <DropdownMenu.Portal>
              <DropdownMenu.Content
                sideOffset={4}
                align="end"
                className="z-50 min-w-44 rounded-lg border border-line bg-surface p-1 text-sm shadow-[var(--shadow-pop)]"
              >
                {(presets.data ?? []).map((preset) => (
                  <DropdownMenu.Item
                    key={preset.key}
                    onSelect={() => createProvider.mutate(preset.key)}
                    className="cursor-pointer rounded-md px-2.5 py-2 text-ink outline-none data-[highlighted]:bg-subtle"
                  >
                    {preset.label}
                  </DropdownMenu.Item>
                ))}
              </DropdownMenu.Content>
            </DropdownMenu.Portal>
          </DropdownMenu.Root>
        </div>

        {providers.length === 0 ? (
          <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-xs text-ink-3">
            {strings.ai.noProviders}
          </p>
        ) : null}

        <div className="space-y-3">
          {providers.map((provider) => (
            <ProviderCard
              key={provider.id}
              provider={provider}
              onPatch={(patch) => updateProvider.mutate({ id: provider.id, ...patch })}
              onDelete={() => {
                if (window.confirm(strings.ai.deleteConfirm(provider.label))) {
                  deleteProvider.mutate(provider.id);
                }
              }}
            />
          ))}
        </div>

        {providers.filter((provider) => provider.enabled).length > 1 ? (
          <p className="mt-2 text-2xs text-ink-3">{strings.ai.firstProviderHint}</p>
        ) : null}
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{strings.ai.usageTitle}</h3>
        <div className="grid grid-cols-[1fr_200px] gap-6 rounded-xl border border-line bg-page px-4 py-4">
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink">
              {strings.ai.usageUsed} <span className="font-semibold">{thousands(used)}</span>
              {' / '}
              {limit > 0 ? (
                <span className="font-semibold">{thousands(limit)}</span>
              ) : (
                strings.ai.usageUnlimited
              )}{' '}
              {strings.ai.usageTokens}
            </p>
            <span className="mt-3 block h-1.5 w-full max-w-[400px] overflow-hidden rounded-full bg-line">
              <span
                className="block h-full rounded-full bg-brand transition-[width]"
                style={{ width: `${Math.round(ratio * 100)}%` }}
              />
            </span>
            <p className="mt-2 text-2xs text-ink-3">{strings.ai.usageHint}</p>
          </div>

          <label className="block">
            <span className="mb-1.5 block text-2xs text-ink-3">{strings.ai.limitLabel}</span>
            <input
              type="number"
              min={0}
              inputMode="numeric"
              value={limitDraft ?? (limit > 0 ? String(limit) : '')}
              placeholder={strings.ai.limitPlaceholder}
              onChange={(event) => setLimitDraft(event.target.value)}
              onBlur={() => {
                if (limitDraft === null) return;
                const parsed = Number.parseInt(limitDraft, 10);
                updateSettings.mutate({ ai_token_limit: Number.isFinite(parsed) && parsed > 0 ? parsed : 0 });
                setLimitDraft(null);
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') event.currentTarget.blur();
              }}
              className="h-9 w-full rounded-lg border border-line bg-surface px-3 text-sm text-ink outline-none transition-colors focus:border-brand"
            />
          </label>
        </div>

        {usage.data && usage.data.calls > 0 ? (
          <p className="mt-2 text-2xs text-ink-3">
            本月 {usage.data.calls} 次调用 · 累计 {thousands(usage.data.total_tokens)} tokens
          </p>
        ) : null}
      </section>
    </div>
  );
}

interface ProviderCardProps {
  provider: AiProvider;
  onPatch: (patch: {
    label?: string;
    base_url?: string;
    model?: string;
    enabled?: boolean;
    api_key?: string;
    clear_key?: boolean;
  }) => void;
  onDelete: () => void;
}

/** 656×~100 的供应商卡片：名称 + 开关 + 三列字段。 */
function ProviderCard({ provider, onPatch, onDelete }: ProviderCardProps) {
  const [label, setLabel] = useState(provider.label);
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [model, setModel] = useState(provider.model);
  const [key, setKey] = useState('');
  const [editingKey, setEditingKey] = useState(false);

  const commit = (field: 'label' | 'base_url' | 'model', value: string) => {
    const trimmed = value.trim();
    if (field === 'label' && !trimmed) {
      setLabel(provider.label);
      return;
    }
    if (trimmed === provider[field]) return;
    if (field === 'label') onPatch({ label: trimmed });
    else if (field === 'base_url') onPatch({ base_url: trimmed });
    else onPatch({ model: trimmed });
  };

  return (
    <div className="rounded-xl border border-line bg-page px-3 py-3">
      <div className="group flex h-5 items-center gap-2">
        <input
          aria-label="供应商名称"
          value={label}
          onChange={(event) => setLabel(event.target.value)}
          onBlur={(event) => commit('label', event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') event.currentTarget.blur();
          }}
          className="min-w-0 flex-1 truncate bg-transparent text-sm font-semibold text-ink outline-none"
        />

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              aria-label="供应商操作"
              className="hidden h-5 w-5 items-center justify-center rounded-md text-ink-3 hover:bg-subtle group-hover:flex"
            >
              <MoreHorizontal size={14} />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              sideOffset={4}
              align="end"
              className="z-50 min-w-32 rounded-lg border border-line bg-surface p-1 text-sm shadow-[var(--shadow-pop)]"
            >
              <DropdownMenu.Item
                onSelect={onDelete}
                className="flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 text-danger-ink outline-none data-[highlighted]:bg-subtle"
              >
                <Trash2 size={13} />
                删除
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        <Switch
          checked={provider.enabled}
          label={`${provider.label} 启用`}
          onChange={(next) => onPatch({ enabled: next })}
        />
      </div>

      <div className="mt-2.5 grid grid-cols-[1fr_1fr_120px] gap-3">
        <MiniField
          label={strings.ai.fieldUrl}
          value={baseUrl}
          placeholder="https://api.example.com/v1"
          onChange={(event) => setBaseUrl(event.target.value)}
          onBlur={(event) => commit('base_url', event.target.value)}
        />

        <MiniField
          label={strings.ai.fieldKey}
          type="text"
          value={editingKey ? key : provider.api_key_hint}
          placeholder={strings.ai.keyPlaceholder}
          autoComplete="off"
          onFocus={() => {
            setEditingKey(true);
            setKey('');
          }}
          onChange={(event) => setKey(event.target.value)}
          onBlur={(event) => {
            const value = event.target.value.trim();
            setEditingKey(false);
            if (value) onPatch({ api_key: value });
            setKey('');
          }}
        />

        <MiniField
          label={strings.ai.fieldModel}
          value={model}
          placeholder="gpt-4o-mini"
          onChange={(event) => setModel(event.target.value)}
          onBlur={(event) => commit('model', event.target.value)}
        />
      </div>
    </div>
  );
}
