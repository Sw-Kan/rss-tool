/** 极简 i18n：语言包 + React context。
 *
 *  语言来源：登录前用 localStorage / 浏览器语言；登录后以 `user_settings.language` 为准
 *  （AppShell 负责同步）。文案全部走 `useT()`，不在组件里硬编码。
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { en } from './en';
import { zhCN, type Strings } from './zh-CN';

export const LOCALES = ['zh-CN', 'en'] as const;
export type Locale = (typeof LOCALES)[number];

/** 语言自称，切换器里永远用本语言显示自己。 */
export const LOCALE_LABELS: Record<Locale, string> = {
  'zh-CN': '中文',
  en: 'English',
};

const STORAGE_KEY = 'rss-tool:locale';

export const bundles: Record<Locale, Strings> = {
  'zh-CN': zhCN,
  en,
};

export function isLocale(value: unknown): value is Locale {
  return typeof value === 'string' && (LOCALES as readonly string[]).includes(value);
}

/** localStorage → 浏览器语言 → 中文。 */
export function detectLocale(): Locale {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(stored)) return stored;
  } catch {
    // 隐私模式下读不到，忽略
  }
  const preferred = typeof navigator === 'undefined' ? '' : navigator.language;
  return preferred.toLowerCase().startsWith('zh') ? 'zh-CN' : 'en';
}

export function saveLocale(locale: Locale): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    // 写不进去就算了，下次按浏览器语言来
  }
}

export function stringsFor(locale: Locale): Strings {
  return bundles[locale];
}

interface I18nValue {
  locale: Locale;
  t: Strings;
  setLocale: (locale: Locale) => void;
}

/** 默认给中文：单测里不套 Provider 也能渲染，避免每个用例都要包一层。 */
const I18nContext = createContext<I18nValue>({
  locale: 'zh-CN',
  t: zhCN,
  setLocale: () => {},
});

export function I18nProvider({
  children,
  initialLocale,
}: {
  children: ReactNode;
  initialLocale?: Locale;
}) {
  const [locale, setLocaleState] = useState<Locale>(() => initialLocale ?? detectLocale());

  const setLocale = useCallback((next: Locale) => {
    setLocaleState(next);
    saveLocale(next);
  }, []);

  // 初次加载与切换都要同步 <html lang>，否则屏幕阅读器与字体回退会拿错语言
  useEffect(() => {
    if (typeof document !== 'undefined') document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo<I18nValue>(
    () => ({ locale, t: stringsFor(locale), setLocale }),
    [locale, setLocale],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nValue {
  return useContext(I18nContext);
}

/** 组件里只取文案：`const t = useT();` */
export function useT(): Strings {
  return useContext(I18nContext).t;
}

export type { Strings };
