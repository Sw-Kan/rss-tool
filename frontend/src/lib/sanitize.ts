/** 正文 HTML 清洗。信任边界，不可省：feed 内容来自第三方。
 *
 *  - 白名单标签 / 属性（DOMPurify 默认放行 style 属性与 class，这里显式排除）
 *  - 禁 script / iframe / style / form / object / embed，以及所有 on* 事件属性
 *  - 外链补 target/rel，图片补 loading/referrerpolicy
 */

import DOMPurify from 'dompurify';

const ALLOWED_TAGS = [
  'p', 'br', 'hr', 'div', 'span',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li', 'dl', 'dt', 'dd',
  'blockquote', 'pre', 'code', 'kbd', 'samp',
  'em', 'strong', 'b', 'i', 'u', 's', 'del', 'ins', 'mark', 'small', 'sub', 'sup',
  'a', 'img', 'figure', 'figcaption', 'picture', 'source',
  'video', 'audio',
  'table', 'thead', 'tbody', 'tfoot', 'tr', 'td', 'th', 'caption', 'colgroup', 'col',
];

const ALLOWED_ATTR = [
  'href', 'src', 'srcset', 'sizes', 'alt', 'title', 'width', 'height',
  'datetime', 'cite', 'colspan', 'rowspan', 'scope', 'controls', 'poster', 'type', 'media',
];

export function sanitizeHtml(html: string): string {
  if (!html) return '';

  const clean = DOMPurify.sanitize(html, {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    FORBID_TAGS: ['script', 'iframe', 'style', 'form', 'input', 'button', 'object', 'embed', 'link'],
    FORBID_ATTR: ['style', 'class', 'id', 'onerror', 'onload', 'onclick'],
    ALLOW_DATA_ATTR: false,
    ALLOWED_URI_REGEXP: /^(?:https?|mailto|data:image\/)/i,
  });

  return harden(clean);
}

/** DOMPurify 之后再做属性加固，避免依赖字符串正则改写 HTML。 */
function harden(html: string): string {
  if (typeof document === 'undefined') return html;

  const template = document.createElement('template');
  template.innerHTML = html;

  for (const anchor of template.content.querySelectorAll('a[href]')) {
    anchor.setAttribute('target', '_blank');
    anchor.setAttribute('rel', 'noopener noreferrer');
  }
  for (const image of template.content.querySelectorAll('img')) {
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
