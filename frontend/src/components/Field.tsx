import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from 'react';

/** 26px pill chip（全部 / 未读 / 已读）。 */
export function Chip({
  active = false,
  children,
  ...rest
}: { active?: boolean; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      aria-pressed={active}
      {...rest}
      className={`inline-flex h-[26px] min-w-12 items-center justify-center rounded-full px-3 text-xs font-medium transition-colors ${
        active
          ? 'bg-strong text-on-strong'
          : 'bg-subtle text-ink-2 hover:text-ink'
      }`}
    >
      {children}
    </button>
  );
}

type BadgeTone = 'success' | 'neutral' | 'danger';

const TONES: Record<BadgeTone, string> = {
  success: 'bg-success-soft text-success-ink',
  neutral: 'bg-neutral-soft text-neutral-ink',
  danger: 'bg-danger-soft text-danger-ink',
};

export function Badge({ tone = 'neutral', children }: { tone?: BadgeTone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex h-6 items-center rounded-full px-2.5 text-2xs font-medium ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/** 11/600 追踪加宽的区块小标题（收藏夹 / RSS 目录 / 未分组源）。 */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-2 text-2xs font-semibold tracking-[0.6px] text-ink-3">{children}</div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="px-4 py-10 text-center text-sm text-ink-3">{children}</div>;
}

interface FieldProps {
  label: string;
  hint?: ReactNode;
  children: ReactNode;
}

export function Field({ label, hint, children }: FieldProps) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-ink-2">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-xs text-ink-3">{hint}</span> : null}
    </label>
  );
}

const CONTROL_CLASS =
  'w-full rounded-lg border border-line bg-surface px-3 text-base text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-brand';

export function TextInput({ className = '', ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...rest} className={`${CONTROL_CLASS} h-10 ${className}`} />;
}

/** 40×20 开关（设计稿 ai-toggle / 自动刷新用）。 */
export function Switch({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-5 w-10 shrink-0 rounded-full transition-colors ${
        checked ? 'bg-brand' : 'bg-line-strong'
      }`}
    >
      <span
        className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-[left] ${
          checked ? 'left-[22px]' : 'left-0.5'
        }`}
      />
    </button>
  );
}

/** 紧凑字段：标签 10.5px + 32px 输入框（设计稿供应商卡片里的三列字段）。 */
export function MiniField({
  label,
  className = '',
  ...rest
}: { label: string } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-[10.5px] text-ink-3">{label}</span>
      <input
        {...rest}
        className={`h-8 w-full rounded-lg border border-line bg-surface px-2.5 text-[11.5px] text-ink placeholder:text-ink-3 outline-none transition-colors focus:border-brand ${className}`}
      />
    </label>
  );
}

export function Select({
  className = '',
  children,
  ...rest
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select {...rest} className={`${CONTROL_CLASS} h-10 ${className}`}>
      {children}
    </select>
  );
}
