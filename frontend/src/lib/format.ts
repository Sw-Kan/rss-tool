/** 时间、数字与文本格式化。时间相关全部走 Intl，跟随当前语言。 */

import type { Locale } from './i18n';

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

function intlLocale(locale: Locale): string {
  return locale === 'en' ? 'en-US' : 'zh-CN';
}

/** 列表里的相对时间：刚刚 / N 分钟前 / N 小时前 / 昨天 / 9 月 2 日 / 2023 年 9 月 2 日 */
export function relativeTime(iso: string, locale: Locale = 'zh-CN', now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const tag = intlLocale(locale);
  const diff = now.getTime() - date.getTime();
  const relative = new Intl.RelativeTimeFormat(tag, { numeric: 'auto' });

  if (diff < MINUTE) return relative.format(0, 'second');
  if (diff < HOUR) return relative.format(-Math.floor(diff / MINUTE), 'minute');

  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (date.getTime() >= startOfToday) return relative.format(-Math.floor(diff / HOUR), 'hour');
  if (date.getTime() >= startOfToday - 24 * HOUR) return relative.format(-1, 'day');

  const sameYear = date.getFullYear() === now.getFullYear();
  return new Intl.DateTimeFormat(tag, {
    year: sameYear ? undefined : 'numeric',
    month: 'short',
    day: 'numeric',
  }).format(date);
}

/** 阅读区里显示完整时间。 */
export function absoluteTime(iso: string, locale: Locale = 'zh-CN'): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return new Intl.DateTimeFormat(intlLocale(locale), {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(date);
}

export function thousands(value: number, locale: Locale = 'zh-CN'): string {
  return value.toLocaleString(intlLocale(locale));
}

/** 按阅读速度估算分钟数：中文 400 字/分，英文 220 词/分。 */
export function readingMinutes(wordCount: number, locale: Locale = 'zh-CN'): number {
  const perMinute = locale === 'en' ? 220 : 400;
  return Math.max(1, Math.round(wordCount / perMinute));
}

/** 头像 / 源 logo 的字母：中文取首字，英文取首字母大写。 */
export function initialOf(name: string): string {
  const trimmed = name.trim();
  if (!trimmed) return '?';
  return trimmed.slice(0, 1).toUpperCase();
}

/** 用字符串稳定散列挑一个调色板下标，保证同一源颜色固定。 */
export function hashIndex(value: string, buckets: number): number {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) % 100000;
  }
  return Math.abs(hash) % buckets;
}

export function swatchFor(seed: string): { bg: string; ink: string } {
  const index = hashIndex(seed, 8);
  return { bg: `var(--swatch-${index})`, ink: `var(--swatch-${index}-ink)` };
}

export const AVATAR_COLORS = [
  'var(--avatar-0)',
  'var(--avatar-1)',
  'var(--avatar-2)',
  'var(--avatar-3)',
  'var(--avatar-4)',
];

export function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max)}…` : value;
}
