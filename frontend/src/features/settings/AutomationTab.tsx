import { ChevronDown, Clock, Play, Plus, Target, Trash2, Zap } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';

import { useCreateRule, useDeleteRule, useRules, useUpdateRule } from '../../api/hooks';
import { Button } from '../../components/Button';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { Switch } from '../../components/Field';
import { useT, type Strings } from '../../lib/i18n';
import type { Rule, RuleActionType, RuleCondition, RuleTrigger } from '../../types';

const TRIGGERS: RuleTrigger[] = ['item_arrived', 'video_arrived', 'picture_arrived', 'schedule'];
const ACTIONS: RuleActionType[] = [
  'favorite',
  'mark_read',
  'mark_unread',
  'feishu',
  'obsidian',
  'custom_export',
];

/** 条件预设。顺序即菜单顺序，`value-less` 的项选中后直接落到输入框。 */
const CONDITION_PRESETS: { field: RuleCondition['field']; op: RuleCondition['op'] }[] = [
  { field: 'title', op: 'contains' },
  { field: 'title', op: 'eq' },
  { field: 'word_count', op: 'gt' },
  { field: 'word_count', op: 'lt' },
  { field: 'channel', op: 'eq' },
  { field: 'feed', op: 'contains' },
  { field: 'kind', op: 'eq' },
  { field: 'favorite', op: 'eq' },
  { field: 'read', op: 'eq' },
];

/** 值固定为「是 / 否」的条件，UI 用两格选择器而不是文本输入。 */
const BOOLEAN_FIELDS: RuleCondition['field'][] = ['favorite', 'read'];

/** 只列出真的返回字符串的文案键：否则 t.auto[key] 会带上函数类型的键。 */
type ConditionHeadKey =
  | 'condTitleContains'
  | 'condTitleEq'
  | 'condChannelEq'
  | 'condFeedContains'
  | 'condWordGt'
  | 'condWordLt'
  | 'condKindEq'
  | 'condFavorite'
  | 'condRead';

const CONDITION_HEADS: Record<string, ConditionHeadKey> = {
  'title:contains': 'condTitleContains',
  'title:eq': 'condTitleEq',
  'channel:eq': 'condChannelEq',
  'feed:contains': 'condFeedContains',
  'word_count:gt': 'condWordGt',
  'word_count:lt': 'condWordLt',
  'kind:eq': 'condKindEq',
  'favorite:eq': 'condFavorite',
  'read:eq': 'condRead',
};

function triggerLabel(t: Strings, rule: { trigger: RuleTrigger; schedule_time: string | null }): string {
  if (rule.trigger === 'schedule') {
    return `${t.auto.scheduleAt} ${rule.schedule_time ?? '08:00'}`;
  }
  return {
    item_arrived: t.auto.triggerItem,
    video_arrived: t.auto.triggerVideo,
    picture_arrived: t.auto.triggerPicture,
    schedule: t.auto.triggerSchedule,
  }[rule.trigger];
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
  return (
    { article: t.auto.kindArticle, picture: t.auto.kindPicture, video: t.auto.kindVideo }[value] ??
    value
  );
}

/** 条件的完整描述，例如「标题包含 “Rust”」「字数大于 3000」「属于收藏 是」。 */
export function conditionLabel(t: Strings, condition: RuleCondition): string {
  const key = CONDITION_HEADS[`${condition.field}:${condition.op}`];
  if (!key) return t.auto.editValue;
  const head = t.auto[key];

  if (!condition.value) return head;
  if (BOOLEAN_FIELDS.includes(condition.field)) {
    const word = condition.value === 'true' ? t.auto.valueOn : t.auto.valueOff;
    return `${head} ${word}`;
  }
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
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [confirming, setConfirming] = useState(false);

  useEffect(() => setName(rule.name), [rule.name]);
  useEffect(() => setEditing(null), [rule.conditions.length]);

  const patch = (body: Partial<Rule>) => update.mutate({ id: rule.id, ...body });

  const setCondition = (index: number, next: RuleCondition) =>
    patch({ conditions: rule.conditions.map((item, i) => (i === index ? next : item)) });

  const addCondition = () => {
    const next = [...rule.conditions, { field: 'title' as const, op: 'contains' as const, value: '' }];
    patch({ conditions: next });
    setEditing(next.length - 1);
    setDraft('');
  };

  const removeCondition = (index: number) =>
    patch({ conditions: rule.conditions.filter((_, i) => i !== index) });

  return (
    <div className="rounded-xl border border-line bg-page px-4 py-3">
      <div className="flex items-center gap-2">
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
          onClick={() => setConfirming(true)}
          className="inline-flex h-6 w-6 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-subtle hover:text-danger-ink"
        >
          <Trash2 size={15} />
        </button>
      </div>

      <div className="mt-3 space-y-2">
        <Row label={t.auto.when}>
          <TriggerBox rule={rule} onPick={(trigger) => patch({ trigger })} />
        </Row>

        <Row label={t.auto.if}>
          <div className="space-y-2">
            {rule.conditions.map((condition, index) => (
              <div key={index}>
                {index > 0 ? (
                  <button
                    type="button"
                    aria-label={rule.join === 'and' ? t.auto.joinAnd : t.auto.joinOr}
                    onClick={() => patch({ join: rule.join === 'and' ? 'or' : 'and' })}
                    className="mb-2 inline-flex h-6 items-center gap-1 rounded-full bg-soft px-3 text-[11px] font-semibold text-on-soft"
                  >
                    {rule.join === 'and' ? t.auto.joinAnd : t.auto.joinOr}
                    <ChevronDown size={12} />
                  </button>
                ) : null}

                <div className="flex items-center gap-2">
                  {editing === index ? (
                    BOOLEAN_FIELDS.includes(condition.field) ? (
                      <div className="flex h-10 flex-1 items-center gap-1 rounded-lg bg-subtle p-1">
                        {[
                          { value: 'true', label: t.auto.valueOn },
                          { value: 'false', label: t.auto.valueOff },
                        ].map((option) => (
                          <button
                            key={option.value}
                            type="button"
                            aria-pressed={condition.value === option.value}
                            onClick={() => {
                              setCondition(index, { ...condition, value: option.value });
                              setEditing(null);
                            }}
                            className={`h-8 flex-1 rounded-md text-xs ${
                              condition.value === option.value
                                ? 'bg-surface font-semibold text-ink'
                                : 'font-medium text-ink-2 hover:text-ink'
                            }`}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <input
                        autoFocus
                        value={draft}
                        placeholder={t.auto.editValue}
                        onChange={(event) => setDraft(event.target.value)}
                        onBlur={() => {
                          setEditing(null);
                          setCondition(index, { ...condition, value: draft.trim() });
                        }}
                        onKeyDown={(event) => {
                          if (event.key === 'Enter') event.currentTarget.blur();
                          if (event.key === 'Escape') setEditing(null);
                        }}
                        className="h-10 min-w-0 flex-1 rounded-lg border border-line bg-surface px-3 text-xs text-ink outline-none focus:border-brand"
                      />
                    )
                  ) : (
                    <div className="min-w-0 flex-1">
                      <SelectBox
                        icon={<Target size={15} />}
                        text={conditionLabel(t, condition)}
                        options={CONDITION_PRESETS.map((preset) => ({
                          key: `${preset.field}:${preset.op}`,
                          label: conditionLabel(t, { ...preset, value: '' }),
                          selected:
                            preset.field === condition.field && preset.op === condition.op,
                          onSelect: () => {
                            const sameField = preset.field === condition.field;
                            setCondition(index, {
                              field: preset.field,
                              op: preset.op,
                              // 换字段就清值：保留旧值容易出现「频道 = Rust」这种怪组合
                              value: sameField ? condition.value : '',
                            });
                            setDraft(sameField ? condition.value : '');
                            setEditing(index);
                          },
                        }))}
                      />
                    </div>
                  )}

                  {rule.conditions.length > 1 ? (
                    <button
                      type="button"
                      aria-label={t.auto.removeCondition}
                      onClick={() => removeCondition(index)}
                      className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-ink-3 hover:bg-subtle hover:text-danger-ink"
                    >
                      <Trash2 size={14} />
                    </button>
                  ) : (
                    <span className="w-6 shrink-0" />
                  )}
                </div>
              </div>
            ))}

            <button
              type="button"
              onClick={addCondition}
              className="text-[11px] font-semibold text-brand-ink"
            >
              {t.auto.addCondition}
            </button>
          </div>
        </Row>

        <Row label={t.auto.then}>
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
        </Row>
      </div>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={t.auto.deleteTitle}
        body={t.auto.deleteBody(rule.name)}
        pending={remove.isPending}
        onConfirm={() => {
          remove.mutate(rule.id);
          setConfirming(false);
        }}
      />
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <span className="mb-1 block text-[10px] font-semibold tracking-[0.5px] text-ink-3">
        {label}
      </span>
      {children}
    </div>
  );
}

/** 「当」控件：定时触发时行内直接给一个时间输入，读数与设计稿一致（每天 08:00）。 */
function TriggerBox({ rule, onPick }: { rule: Rule; onPick: (trigger: RuleTrigger) => void }) {
  const t = useT();
  const update = useUpdateRule();
  const [open, setOpen] = useState(false);

  const commitTime = (value: string) => {
    if (value && value !== rule.schedule_time) {
      update.mutate({ id: rule.id, schedule_time: value });
    }
  };

  return (
    <div className="relative">
      <div className="flex h-10 w-full items-center gap-2 rounded-lg border border-line bg-surface px-3">
        <Clock size={15} className="shrink-0 text-ink-3" />
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="min-w-0 flex-1 truncate text-left text-xs text-ink"
        >
          {triggerLabel(t, rule)}
        </button>
        {rule.trigger === 'schedule' ? (
          <input
            type="time"
            aria-label={t.auto.scheduleAt}
            value={rule.schedule_time ?? '08:00'}
            onChange={(event) => commitTime(event.target.value)}
            className="h-6 w-[76px] shrink-0 rounded border border-line bg-page px-1 text-[11px] text-ink outline-none focus:border-brand"
          />
        ) : null}
        <ChevronDown size={12} className="shrink-0 text-ink-3" />
      </div>

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
            className="absolute top-[44px] left-0 z-50 w-full rounded-lg border border-line bg-surface p-1 shadow-[var(--shadow-pop)]"
          >
            {TRIGGERS.map((trigger) => (
              <button
                key={trigger}
                type="button"
                role="option"
                aria-selected={trigger === rule.trigger}
                onClick={() => {
                  onPick(trigger);
                  setOpen(false);
                }}
                className={`block w-full truncate rounded-md px-2.5 py-2 text-left text-xs transition-colors hover:bg-subtle ${
                  trigger === rule.trigger ? 'font-semibold text-brand-ink' : 'text-ink'
                }`}
              >
                {triggerLabel(t, { trigger, schedule_time: rule.schedule_time })}
              </button>
            ))}
          </div>
        </>
      ) : null}
    </div>
  );
}

interface Option {
  key: string;
  label: string;
  selected: boolean;
  onSelect: () => void;
}

/** 40px 的下拉：收起时显示的是一句完整描述。 */
export function SelectBox({
  icon,
  text,
  options,
}: {
  icon: ReactNode;
  text: string;
  options: Option[];
}) {
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
