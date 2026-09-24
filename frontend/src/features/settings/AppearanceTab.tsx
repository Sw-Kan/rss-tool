import { Moon, Sun } from 'lucide-react';

import { useSettings, useUpdateSettings } from '../../api/hooks';
import { strings } from '../../lib/strings';
import type { TextStyle, Theme } from '../../types';

const THEMES: { id: Theme; label: string; icon: typeof Sun }[] = [
  { id: 'light', label: strings.settings.themeLight, icon: Sun },
  { id: 'dark', label: strings.settings.themeDark, icon: Moon },
];

const TEXT_STYLES: { id: TextStyle; label: string; sample: string }[] = [
  { id: 'small', label: strings.settings.textSmall, sample: '13.5px' },
  { id: 'comfortable', label: strings.settings.textComfortable, sample: '14.5px' },
  { id: 'large', label: strings.settings.textLarge, sample: '16px' },
];

export function AppearanceTab() {
  const settings = useSettings();
  const update = useUpdateSettings();

  if (!settings.data) {
    return <p className="text-sm text-ink-3">{strings.loading}</p>;
  }

  const { theme, text_style, auto_refresh_enabled, refresh_interval_minutes, language } =
    settings.data;

  return (
    <div className="space-y-7">
      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{strings.settings.theme}</h3>
        <div className="flex gap-5">
          {THEMES.map(({ id, label, icon: Icon }) => {
            const active = theme === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => update.mutate({ theme: id })}
                aria-pressed={active}
                className={`flex h-[116px] w-[200px] flex-col items-center justify-center gap-3 rounded-xl border-2 bg-surface transition-colors ${
                  active ? 'border-brand' : 'border-line hover:border-line-strong'
                }`}
              >
                <Icon size={22} className={active ? 'text-brand-ink' : 'text-ink-3'} />
                <span className={`text-sm font-medium ${active ? 'text-ink' : 'text-ink-2'}`}>
                  {label}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{strings.settings.language}</h3>
        <div className="inline-flex rounded-lg bg-subtle p-1">
          <span className="inline-flex h-8 items-center rounded-md bg-surface px-5 text-xs font-semibold text-ink">
            中文
          </span>
          <span
            title={strings.settings.comingSoon}
            className="inline-flex h-8 items-center rounded-md px-5 text-xs font-medium text-ink-3"
          >
            English
          </span>
        </div>
        <p className="mt-2 text-xs text-ink-3">
          当前版本固定 {language}；多语言见 docs/roadmap.md（F7）。
        </p>
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{strings.settings.textStyle}</h3>
        <div className="inline-flex rounded-lg bg-subtle p-1">
          {TEXT_STYLES.map(({ id, label }) => {
            const active = text_style === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => update.mutate({ text_style: id })}
                aria-pressed={active}
                className={`h-8 rounded-md px-5 text-xs ${
                  active
                    ? 'bg-surface font-semibold text-ink'
                    : 'font-medium text-ink-2 hover:text-ink'
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </section>

      <section className="border-t border-line pt-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-semibold text-ink">{strings.settings.refresh}</h3>
            <p className="mt-0.5 text-xs text-ink-3">{strings.settings.refreshHint}</p>
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={auto_refresh_enabled}
            onClick={() => update.mutate({ auto_refresh_enabled: !auto_refresh_enabled })}
            className={`relative h-5 w-10 shrink-0 rounded-full transition-colors ${
              auto_refresh_enabled ? 'bg-brand' : 'bg-line-strong'
            }`}
          >
            <span
              className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-[left] ${
                auto_refresh_enabled ? 'left-[22px]' : 'left-0.5'
              }`}
            />
          </button>
        </div>

        <label className="mt-4 flex items-center gap-3">
          <span className="text-sm text-ink-2">{strings.settings.refreshInterval}</span>
          <input
            type="number"
            min={5}
            max={1440}
            value={refresh_interval_minutes}
            disabled={!auto_refresh_enabled}
            onChange={(event) => {
              const value = Number.parseInt(event.target.value, 10);
              if (Number.isFinite(value) && value >= 5 && value <= 1440) {
                update.mutate({ refresh_interval_minutes: value });
              }
            }}
            className="h-9 w-24 rounded-lg border border-line bg-surface px-3 text-sm text-ink outline-none focus:border-brand disabled:opacity-50"
          />
        </label>
      </section>
    </div>
  );
}
