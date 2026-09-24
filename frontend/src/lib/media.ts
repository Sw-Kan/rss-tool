/** F6：外链图片统一走后端缓存。
 *
 *  为什么不让浏览器直连：很多源做了防盗链（Referer 白名单），浏览器直连会 403；
 *  外链失效后旧文章也会永久丢图。走 `/api/media` 由服务端取一次并落盘，
 *  两个问题一起解决；服务端拉不到时会 302 回原地址，浏览器再去试。
 */

import { apiPath } from '../api/client';

const ABSOLUTE = /^https?:\/\//i;

/** 绝对 http(s) 地址才需要代理；data: 之类原样保留。 */
export function mediaUrl(src: string | null | undefined): string {
  if (!src) return '';
  if (src.startsWith('data:')) return src;
  if (!ABSOLUTE.test(src)) return src;
  return apiPath(`/api/media?url=${encodeURIComponent(src)}`);
}

/**
 * 把 feed 里的图片地址解析成绝对地址再走缓存。
 *
 * 相对地址（`/img/a.png`）必须按原文地址解析 —— 否则会被当成我们自己的站点路径，
 * 直接 404。拿不到基地址时返回空串，由调用方决定怎么兜底。
 */
export function resolveMediaUrl(src: string | null | undefined, baseUrl?: string | null): string {
  if (!src) return '';
  if (src.startsWith('data:')) return src;
  if (ABSOLUTE.test(src)) return mediaUrl(src);
  if (!baseUrl) return '';
  try {
    const absolute = new URL(src, baseUrl);
    if (absolute.protocol !== 'http:' && absolute.protocol !== 'https:') return '';
    return mediaUrl(absolute.toString());
  } catch {
    return '';
  }
}

/** 图片代理是否可用（关掉时前端就不该改写地址）。 */
export function mediaCacheEnabled(): boolean {
  return import.meta.env.VITE_MEDIA_CACHE !== 'off';
}
