import { useT } from '../../lib/i18n';

/** AI / 集成 / 自动化 / 代理 四个 tab 的占位。本阶段不提供可用的假入口。 */
export function PlaceholderTab() {
  const t = useT();
  return (
    <div className="flex h-40 items-center justify-center rounded-xl border border-dashed border-line bg-page">
      <p className="text-center text-sm text-ink-3">
        <span className="mb-1 block font-medium text-ink-2">{t.settings.comingSoon}</span>
        {t.settings.comingSoonHint}
      </p>
    </div>
  );
}
