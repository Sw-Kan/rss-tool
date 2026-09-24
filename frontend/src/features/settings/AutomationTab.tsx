import { ChevronDown, Clock, Play, Plus, Target, Trash2, Zap } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';

import { useCreateRule, useDeleteRule, useRules, useUpdateRule } from '../../api/hooks';
import { Button } from '../../components/Button';
import { Switch } from '../../components/Field';
import { useT, type Strings } from '../../lib/i18n';
import type { Rule, RuleActionType, RuleCondition, RuleTrigger } from '../../types';

const TRIGGERS: RuleTrigger[] = ['item_arrived', 'video_arrived', 'picture_arrived'];
const ACTIONS: RuleActionType[] = [
  'favorite',
  'mark_read',
  'mark_unread',
  'feishu',
  'obsidian',
  'custom_export',
];

/** 条件的预设：下拉里显示的就是「字段 + 运算符 + 值」的完整描述。 */
const CONDITION_PRESETS: { field: RuleCondition['field']; op: RuleCondition['op'] }[] = [
  { field: 'title', op: 'contains' },
  { field: 'title', op: 'eq' },
  { field: 'word_count', op: 'gt' },
  { field: 'word_count', op: 'lt' },
  { field: 'channel', op: 'eq' },
  { field: 'feed', op: 'contains' },
  { field: 'kind', op: 'eq' },
];

function triggerLabel(t: Strings, trigger: RuleTrigger): string {
  return {
    item_arrived: t.auto.triggerItem,
    video_arrived: t.auto.triggerVideo,
    picture_arrived: t.auto.triggerPicture,
  }[trigger];
}

function actionLabel(t: Strings, action: RuleActionType): string {
  return {
    favorite: t.auto.actionFavorite,
    mark_read: t.auto.actionMarkRead,
    mark_unread: t.auto.actionMarkUnread,
    feishu: t.auto.actionFeishu,
    obsidian: t.auto.actionObsidian,
    custom_export: t.auto.actionCustom,
  }[action];
}

function kindLabel(t: Strings, value: string): string {
  return { article: t.auto.kindArticle, picture: t.auto.kindPicture, video: t.auto.kindVideo }[
    value
  ] ?? value;
}

const CONDITION_HEADS: Record<string, keyof Strings['auto']> = {
  'title:contains': 'condTitleContains',
  'title:eq': 'condTitleEq',
  'channel:eq': 'condChannelEq',
  'feed:contains': 'condFeedContains',
  'word_count:gt': 'condWordGt',
  'word_count:lt': 'condWordLt',
  'kind:eq': 'condKindEq',
};

/** 条件的完整描述，例如「标题包含 “Rust”」「字数大于 3000」。 */
function conditionLabel(t: Strings, condition: RuleCondition): string {
  const key = CONDITION_HEADS[`${condition.field}:${condition.op}`];
  if (!key) return t.auto.editValue;
  const head = t.auto[key];
  if (!condition.value) return head;
  const value = condition.field === 'kind' ? kindLabel(t, condition.value) : condition.value;
  return `${head} “${value}”`;
}

export function AutomationTab() {
  const t = useT();
  const rules = useRules();
  const createRule = useCreateRule();

  const list = rules.data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold text-ink">{t.auto.title}</h3>
        <Button
          size="sm"
          variant="soft"
          icon={<Plus size={14} />}
          disabled={createRule.isPending}
          onClick={() => createRule.mutate({ name: t.auto.title })}
        >
          {t.auto.addRule}
        </Button>
      </div>

      <p className="text-2xs text-ink-2">{t.auto.hint}</p>

      {list.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line px-4 py-6 text-center text-xs text-ink-3">
          {t.auto.empty}
        </p>
      ) : null}

      <div className="space-y-4">
        {list.map((rule) => (
          <RuleCard key={rule.id} rule={rule} />
        ))}
      </div>
    </div>
  );
}

function RuleCard({ rule }: { rule: Rule }) {
  const t = useT();
  const update = useUpdateRule();
  const remove = useDeleteRule();

  const [name, setName] = useState(rule.name);
  const [editingValue, setEditingValue] = useState(false);
  const [value, setValue] = useState(rule.condition.value);

  useEffect(() => setName(rule.name), [rule.name]);
  useEffect(() => setValue(rule.condition.value), [rule.condition.value]);

  const patch = (body: Partial<Rule>) => update.mutate({ id: rule.id, ...body });

  return (
    <div className="rounded-xl border border-line bg-page px-4 py-3">
      <div className="group flex items-center gap-2">
        <Zap size={15} className="shrink-0 text-ink-3" />
        <input
          aria-label={t.auto.ruleName}
          value={name}
          onChange={(event) => setName(event.target.value)}
          onBlur={() => {
            const next = name.trim();
            if (next && next !== rule.name) patch({ name: next });
            else setName(rule.name);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter') event.currentTarget.blur();
          }}
          className="min-w-0 flex-1 bg-transparent text-sm font-semibold text-ink outline-none"
        />
        <Switch
          checked={rule.enabled}
          label={t.auto.ruleName}
          onChange={(enabled) => patch({ enabled })}
        />
        <button
          type="button"
          aria-label={t.auto.deleteRule}
          onClick={() => remove.mutate(rule.id)}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-subtle hover:text-danger-ink"
        >
          <Trash2 size={15} />
        </button>
      </div>

      <div className="mt-3 grid grid-cols-[1fr_1fr_176px] gap-5">
        <Column label={t.auto.when}>
          <SelectBox
            icon={<Clock size={15} />}
            text={triggerLabel(t, rule.trigger)}
            options={TRIGGERS.map((trigger) => ({
              key: trigger,
              label: triggerLabel(t, trigger),
              selected: trigger === rule.trigger,
              onSelect: () => patch({ trigger }),
            }))}
          />
        </Column>

        <Column label={t.auto.if}>
          {editingValue ? (
            <input
              autoFocus
              value={value}
              placeholder={t.auto.editValue}
              onChange={(event) => setValue(event.target.value)}
              onBlur={() => {
                setEditingValue(false);
                patch({ condition: { ...rule.condition, value: value.trim() } });
              }}
              onKeyDown={(event) => {
                if (event.key === 'Enter') event.currentTarget.blur();
                if (event.key === 'Escape') {
                  setValue(rule.condition.value);
                  setEditingValue(false);
                }
              }}
              className="h-10 w-full rounded-lg border border-line bg-surface px-3 text-xs text-ink outline-none focus:border-brand"
            />
          ) : (
            <SelectBox
              icon={<Target size={15} />}
              text={conditionLabel(t, rule.condition)}
              options={[
                ...CONDITION_PRESETS.map((preset) => ({
                  key: `${preset.field}:${preset.op}`,
                  label: conditionLabel(t, { ...preset, value: '' }),
                  selected:
                    preset.field === rule.condition.field && preset.op === rule.condition.op,
                  onSelect: () => {
                    patch({ condition: { ...rule.condition, field: preset.field, op: preset.op } });
                    setEditingValue(true);
                  },
                })),
              ]}
            />
          )}
        </Column>

        <Column label={t.auto.then}>
          <SelectBox
            icon={<Play size={15} />}
            text={actionLabel(t, rule.action.type)}
            options={ACTIONS.map((action) => ({
              key: action,
              label: actionLabel(t, action),
              selected: action === rule.action.type,
              onSelect: () => patch({ action: { type: action } }),
            }))}
          />
        </Column>
      </div>
    </div>
  );
}

function Column({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <span className="mb-1 block text-[10px] font-semibold tracking-[0.5px] text-ink-3">
        {label}
      </span>
      {children}
    </div>
  );
}

interface Option {
  key: string;
  label: string;
  selected: boolean;
  onSelect: () => void;
}

/** 40px 的下拉：收起时显示的是一句完整描述（设计稿的「标题包含 “Rust”」）。 */
function SelectBox({ icon, text, options }: { icon: ReactNode; text: string; options: Option[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex h-10 w-full items-center gap-2 rounded-lg border border-line bg-surface px-3 text-left text-xs text-ink transition-colors hover:border-line-strong"
      >
        <span className="shrink-0 text-ink-3">{icon}</span>
        <span className="min-w-0 flex-1 truncate">{text}</span>
        <ChevronDown size={12} className="shrink-0 text-ink-3" />
      </button>

      {open ? (
        <>
          <button
            type="button"
            aria-label="close"
            tabIndex={-1}
            className="fixed inset-0 z-40 cursor-default"
            onClick={() => setOpen(false)}
          />
          <div
            role="listbox"
            className="absolute top-[44px] left-0 z-50 max-h-64 w-full overflow-y-auto rounded-lg border border-line bg-surface p-1 shadow-[var(--shadow-pop)]"
          >
            {options.map((option) => (
              <button
                key={option.key}
                type="button"
                role="option"
                aria-selected={option.selected}
                onClick={() => {
                  option.onSelect();
                  setOpen(false);
                }}
                className={`block w-full truncate rounded-md px-2.5 py-2 text-left text-xs transition-colors hover:bg-subtle ${
                  option.selected ? 'font-semibold text-brand-ink' : 'text-ink'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}
