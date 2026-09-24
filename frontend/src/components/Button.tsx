import type { ButtonHTMLAttributes, ReactNode } from 'react';

type Variant = 'ghost' | 'soft' | 'solid' | 'outline' | 'danger';
type Size = 'sm' | 'md';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  ghost: 'bg-transparent text-ink-2 hover:bg-subtle hover:text-ink',
  soft: 'bg-soft text-on-soft hover:brightness-95',
  solid: 'bg-brand text-white hover:bg-brand-hover',
  outline: 'border border-line bg-surface text-ink hover:bg-subtle',
  danger: 'bg-danger-soft text-danger-ink hover:brightness-95',
};

const SIZES: Record<Size, string> = {
  sm: 'h-8 gap-1.5 px-3 text-xs',
  md: 'h-10 gap-2 px-4 text-base',
};

export function Button({
  variant = 'outline',
  size = 'md',
  icon,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type="button"
      {...rest}
      className={`inline-flex items-center justify-center rounded-lg font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANTS[variant]} ${SIZES[size]} ${className}`}
    >
      {icon}
      {children}
    </button>
  );
}

interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  label: string;
  active?: boolean;
  size?: number;
}

/** 28×28 图标按钮（设计稿的 list-refresh / list-read / list-unread 等）。 */
export function IconButton({
  label,
  active = false,
  size = 28,
  className = '',
  children,
  ...rest
}: IconButtonProps) {
  return (
    <button
      type="button"
      title={label}
      aria-label={label}
      {...rest}
      style={{ width: size, height: size }}
      className={`inline-flex items-center justify-center rounded-md transition-colors disabled:opacity-40 ${
        active ? 'bg-soft text-on-soft' : 'text-ink-3 hover:bg-subtle hover:text-ink'
      } ${className}`}
    >
      {children}
    </button>
  );
}
