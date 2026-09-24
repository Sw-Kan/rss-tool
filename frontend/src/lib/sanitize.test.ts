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
    expect(out).toContain('src="https://x.com/a.png"');
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
