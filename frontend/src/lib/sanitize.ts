/** 正文 HTML 清洗。信任边界，不可省：feed 内容来自第三方。
 *
 *  - 白名单标签 / 属性（DOMPurify 默认放行 style 属性与 class，这里显式排除）
 *  - 禁 script / iframe / style / form / object / embed，以及所有 on* 事件属性
 *  - 外链补 target/rel，图片补 loading/referrerpolicy
 */

import DOMPurify from 'dompurify';

import { resolveMediaUrl } from './media';

const ALLOWED_TAGS = [
  'p', 'br', 'hr', 'div', 'span',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  'blockquote', 'pre', 'code', 'kbd', 'samp',
  'em', 'strong', 'b', 'i', 'u', 's', 'del', 'ins', 'mark', 'small', 'sub', 'sup',
  'a', 'img', 'figure', 'figcaption', 'picture', 'source',
  'video', 'audio',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption', 'colgroup', 'col',
  // 语义容器：feed 正文与 readability 抽取结果都会用到（F5）
  'article', 'section', 'main', 'time',
];

// 故意不放 srcset / sizes：它们会绕过图片缓存直连原站，在防盗链的源上必坏
const ALLOWED_ATTR = [
  'href', 'src', 'alt', 'title', 'width', 'height',
  'datetime', 'cite', 'colspan', 'rowspan', 'scope', 'controls', 'poster', 'type', 'media',
];

/** `baseUrl` 用来解析正文里的相对图片地址（通常是文章原文地址）。 */
export function sanitizeHtml(html: string, baseUrl?: string | null): string {
  if (!html) return '';

  // 先把相对的图片地址绝对化，再交给 DOMPurify —— 否则它那条严格的 URI 白名单
  // 会直接把 `/img/a.png` 这种 src 丢掉，后面就没机会解析了。
  const clean = DOMPurify.sanitize(absolutizeImages(html, baseUrl), {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    FORBID_TAGS: ['script', 'iframe', 'style', 'form', 'input', 'button', 'object', 'embed', 'link'],
    FORBID_ATTR: ['style', 'class', 'id', 'onerror', 'onload', 'onclick'],
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:https?|mailto|data:image\/)/i,
  });

  return harden(clean, baseUrl);
}

/**
 * 用惰性 `<template>` 解析（不会发起任何网络请求），把相对图片地址按 baseUrl 补全。
 * 解析不出来的直接删掉节点：留着只会让浏览器按本站路径去取，必然 404。
 */
function absolutizeImages(html: string, baseUrl?: string | null): string {
  if (typeof document === 'undefined') return html;
  if (!html.includes('<img')) return html;

  const template = document.createElement('template');
  template.innerHTML = html;

  for (const image of template.content.querySelectorAll('img')) {
    const raw = image.getAttribute('src');
    if (!raw) {
      image.remove();
      continue;
    }
    if (/^data:/i.test(raw)) continue;
    if (/^https?:/i.test(raw)) continue;

    const resolved = baseUrl ? safeResolve(raw, baseUrl) : null;
    if (!resolved) {
      image.remove();
      continue;
    }
    image.setAttribute('src', resolved);
  }
  return template.innerHTML;
}

function safeResolve(src: string, baseUrl: string): string | null {
  try {
    const url = new URL(src, baseUrl);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
    return url.toString();
  } catch {
    return null;
  }
}

/** DOMPurify 之后再做属性加固，避免依赖字符串正则改写 HTML。 */
function harden(html: string, baseUrl?: string | null): string {
  if (typeof document === 'undefined') return html;

  const template = document.createElement('template');
  template.innerHTML = html;

  for (const anchor of template.content.querySelectorAll('a[href]')) {
    anchor.setAttribute('target', '_blank');
    anchor.setAttribute('rel', 'noopener noreferrer');
  }

  for (const image of template.content.querySelectorAll('img')) {
    const resolved = resolveMediaUrl(image.getAttribute('src'), baseUrl);
    if (!resolved) {
      // 地址解析不出来（无基地址的相对路径、非 http 协议等）：宁可去掉也不要指向本页
      image.remove();
      continue;
    }
    image.setAttribute('src', resolved);
    image.setAttribute('loading', 'lazy');
    image.setAttribute('referrerpolicy', 'no-referrer');
  }
  return template.innerHTML;
}

/** 只保留用于纯文本预览的版本（列表 / 分享文案）。 */
export function toPlainText(html: string, limit = 200): string {
  const text = html
    .replace(/<[^>]*>/g, ' ')
    .replace(/&nbsp;/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return text.length > limit ? `${text.slice(0, limit)}…` : text;
}
