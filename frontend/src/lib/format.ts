/** 时间、数字与文本格式化。 */

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;

function pad(value: number): string {
  return value.toString().padStart(2, '0');
}

/** 列表里的相对时间：刚刚 / N 分钟前 / N 小时前 / 昨天 / M月D日 / YYYY年M月D日 */
export function relativeTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';

  const diff = now.getTime() - date.getTime();
  if (diff < 0) return '刚刚';
  if (diff < MINUTE) return '刚刚';
  if (diff < HOUR) return `${Math.floor(diff / MINUTE)} 分钟前`;

  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  if (date.getTime() >= startOfToday) return `${Math.floor(diff / HOUR)} 小时前`;
  if (date.getTime() >= startOfToday - 24 * HOUR) return '昨天';
  if (date.getFullYear() === now.getFullYear()) return `${date.getMonth() + 1} 月 ${date.getDate()} 日`;
  return `${date.getFullYear()} 年 ${date.getMonth() + 1} 月 ${date.getDate()} 日`;
}

/** 阅读区里显示完整时间：2024-09-02 16:00 */
export function absoluteTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

export function thousands(value: number): string {
  return value.toLocaleString('zh-CN');
}

/** 按中文阅读速度 400 字/分钟估算。 */
export function readingMinutes(wordCount: number): number {
  return Math.max(1, Math.round(wordCount / 400));
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
