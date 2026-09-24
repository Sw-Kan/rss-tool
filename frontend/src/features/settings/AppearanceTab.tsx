import { Moon, Sun } from 'lucide-react';

import { useSettings, useUpdateSettings } from '../../api/hooks';
import { Switch } from '../../components/Field';
import { LOCALES, LOCALE_LABELS, useI18n, useT } from '../../lib/i18n';
import type { TextStyle, Theme } from '../../types';

export function AppearanceTab() {
  const t = useT();
  const { locale, setLocale } = useI18n();
  const settings = useSettings();
  const update = useUpdateSettings();

  if (!settings.data) {
    return <p className="text-sm text-ink-3">{t.loading}</p>;
  }

  const themes: { id: Theme; label: string; icon: typeof Sun }[] = [
    { id: 'light', label: t.settings.themeLight, icon: Sun },
    { id: 'dark', label: t.settings.themeDark, icon: Moon },
  ];

  const textStyles: { id: TextStyle; label: string }[] = [
    { id: 'small', label: t.settings.textSmall },
    { id: 'comfortable', label: t.settings.textComfortable },
    { id: 'large', label: t.settings.textLarge },
  ];

  const { theme, text_style, auto_refresh_enabled, refresh_interval_minutes, language } =
    settings.data;

  return (
    <div className="space-y-7">
      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{t.settings.theme}</h3>
        <div className="flex gap-5">
          {themes.map(({ id, label, icon: Icon }) => {
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
        <h3 className="mb-3 text-sm font-semibold text-ink">{t.settings.language}</h3>
        <div className="inline-flex rounded-lg bg-subtle p-1">
          {LOCALES.map((option) => {
            const active = locale === option;
            return (
              <button
                key={option}
                type="button"
                aria-pressed={active}
                onClick={() => {
                  setLocale(option);
                  if (language !== option) update.mutate({ language: option });
                }}
                className={`h-8 rounded-md px-5 text-xs ${
                  active
                    ? 'bg-surface font-semibold text-ink'
                    : 'font-medium text-ink-2 hover:text-ink'
                }`}
              >
                {LOCALE_LABELS[option]}
              </button>
            );
          })}
        </div>
        <p className="mt-2 text-xs text-ink-3">{t.settings.languageHint}</p>
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{t.settings.textStyle}</h3>
        <div className="inline-flex rounded-lg bg-subtle p-1">
          {textStyles.map(({ id, label }) => {
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
            <h3 className="text-sm font-semibold text-ink">{t.settings.refresh}</h3>
            <p className="mt-0.5 text-xs text-ink-3">{t.settings.refreshHint}</p>
          </div>
          <Switch
            checked={auto_refresh_enabled}
            label={t.settings.refresh}
            onChange={(next) => update.mutate({ auto_refresh_enabled: next })}
          />
        </div>

        <label className="mt-4 flex items-center gap-3">
          <span className="text-sm text-ink-2">{t.settings.refreshInterval}</span>
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
