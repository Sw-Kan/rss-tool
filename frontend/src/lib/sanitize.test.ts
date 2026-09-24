// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';

import { sanitizeHtml, toPlainText } from './sanitize';

describe('sanitizeHtml', () => {
  it('strips script tags and their content', () => {
    const out = sanitizeHtml('<p>正文</p><script>alert(1)</script>');
    expect(out).toContain('正文');
    expect(out).not.toContain('script');
    expect(out).not.toContain('alert');
  });

  it('strips event handler attributes', () => {
    const out = sanitizeHtml('<img src="https://x.com/a.png" onerror="alert(1)">');
    expect(out).toContain(encodeURIComponent('https://x.com/a.png'));
    expect(out).not.toContain('onerror');
  });

  it('drops iframes, style blocks and inline style attributes', () => {
    const out = sanitizeHtml(
      '<iframe src="https://evil.test"></iframe><style>body{display:none}</style><p style="position:fixed">x</p>',
    );
    expect(out).not.toContain('iframe');
    expect(out).not.toContain('evil.test');
    expect(out).not.toContain('style');
    expect(out).toContain('x');
  });

  it('hardens links and images', () => {
    const out = sanitizeHtml('<a href="https://x.com">链接</a><img src="https://x.com/a.png">');
    expect(out).toContain('target="_blank"');
    expect(out).toContain('rel="noopener noreferrer"');
    // 图片 src 会被改写成缓存地址（见下面的 F6 用例）
    expect(out).toContain('loading="lazy"');
    expect(out).toContain('referrerpolicy="no-referrer"');
  });

  it('rejects javascript: urls', () => {
    const out = sanitizeHtml('<a href="javascript:alert(1)">点我</a>');
    expect(out).not.toContain('javascript:');
  });

  it('keeps ordinary article markup', () => {
    const out = sanitizeHtml('<h2>标题</h2><p>段落</p><ul><li>项</li></ul><blockquote>引</blockquote>');
    for (const fragment of ['<h2>', '<p>', '<li>', '<blockquote>']) {
      expect(out).toContain(fragment);
    }
  });

  it('keeps the semantic containers produced by full-text extraction', () => {
    const out = sanitizeHtml(
      '<article><h1>标题</h1><p>正文</p><section><time>2024-09-02</time></section></article>',
    );
    expect(out).toContain('<article>');
    expect(out).toContain('<section>');
    expect(out).toContain('<time>');
    expect(out).toContain('正文');
  });

  it('unwraps unknown containers but keeps their text', () => {
    const out = sanitizeHtml('<custom-widget><p>重要内容</p></custom-widget>');
    expect(out).toContain('重要内容');
    expect(out).not.toContain('custom-widget');
  });

  it('handles empty input', () => {
    expect(sanitizeHtml('')).toBe('');
  });
});

describe('toPlainText', () => {
  it('strips tags, collapses whitespace and truncates', () => {
    expect(toPlainText('<p>  你好   <b>世界</b> </p>')).toBe('你好 世界');
    expect(toPlainText(`<p>${'字'.repeat(50)}</p>`, 10)).toHaveLength(11);
  });
});

describe('图片缓存改写（F6）', () => {
  it('rewrites absolute images through the cache', () => {
    const out = sanitizeHtml('<img src="https://cdn.example.com/a.png">');
    expect(out).toContain('/api/media?url=');
    expect(out).toContain(encodeURIComponent('https://cdn.example.com/a.png'));
    expect(out).toContain('referrerpolicy="no-referrer"');
  });

  it('resolves relative images against the article url', () => {
    const out = sanitizeHtml('<img src="/img/a.png">', 'https://blog.example.com/post/1');
    expect(out).toContain(encodeURIComponent('https://blog.example.com/img/a.png'));
  });

  it('drops relative images when no base url is known', () => {
    // 否则浏览器会按本站路径去取，必然 404
    const out = sanitizeHtml('<p>正文</p><img src="/img/a.png">');
    expect(out).not.toContain('<img');
    expect(out).toContain('正文');
  });

  it('keeps data uris untouched', () => {
    const data = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
    const out = sanitizeHtml(`<img src="${data}">`);
    expect(out).toContain(data);
    expect(out).not.toContain('/api/media');
  });

  it('strips srcset so images cannot bypass the cache', () => {
    const out = sanitizeHtml(
      '<img src="https://cdn.example.com/a.png" srcset="https://cdn.example.com/a@2x.png 2x">',
    );
    expect(out).not.toContain('srcset');
    expect(out).not.toContain('a%402x');
  });
});
