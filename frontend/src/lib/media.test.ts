import { describe, expect, it } from 'vitest';

import { mediaUrl, resolveMediaUrl } from './media';

const IMG = 'https://cdn.example.com/a.png';

describe('mediaUrl', () => {
  it('routes absolute images through the cache', () => {
    expect(mediaUrl(IMG)).toBe(`/api/media?url=${encodeURIComponent(IMG)}`);
  });

  it('keeps data uris as-is', () => {
    const data = 'data:image/gif;base64,R0lGODlhAQABAAAAACw=';
    expect(mediaUrl(data)).toBe(data);
  });

  it('leaves relative paths alone (the caller must resolve them first)', () => {
    expect(mediaUrl('/img/a.png')).toBe('/img/a.png');
  });

  it('handles empty input', () => {
    expect(mediaUrl('')).toBe('');
    expect(mediaUrl(null)).toBe('');
    expect(mediaUrl(undefined)).toBe('');
  });
});

describe('resolveMediaUrl', () => {
  it('passes absolute urls straight to the cache', () => {
    expect(resolveMediaUrl(IMG)).toBe(mediaUrl(IMG));
  });

  it('resolves protocol-relative urls', () => {
    expect(resolveMediaUrl('//cdn.example.com/a.png', 'https://blog.example.com/post/1')).toBe(
      mediaUrl('https://cdn.example.com/a.png'),
    );
  });

  it('resolves root-relative urls against the article url', () => {
    expect(resolveMediaUrl('/img/a.png', 'https://blog.example.com/post/1')).toBe(
      mediaUrl('https://blog.example.com/img/a.png'),
    );
  });

  it('resolves path-relative urls', () => {
    expect(resolveMediaUrl('img/a.png', 'https://blog.example.com/post/1')).toBe(
      mediaUrl('https://blog.example.com/post/img/a.png'),
    );
  });

  it('returns empty when a relative url has no base', () => {
    expect(resolveMediaUrl('/img/a.png')).toBe('');
    expect(resolveMediaUrl('/img/a.png', null)).toBe('');
  });

  it('rejects non-http schemes', () => {
    expect(resolveMediaUrl('javascript:alert(1)', 'https://blog.example.com')).toBe('');
    expect(resolveMediaUrl('ftp://x.com/a.png', 'https://blog.example.com')).toBe('');
  });

  it('keeps data uris', () => {
    const data = 'data:image/png;base64,AAAA';
    expect(resolveMediaUrl(data)).toBe(data);
  });

  it('encodes the url so query params inside it survive', () => {
    const withQuery = 'https://cdn.example.com/a.png?w=800&h=600';
    const out = resolveMediaUrl(withQuery);
    expect(out).toContain(encodeURIComponent(withQuery));
    expect(out.split('?').length).toBe(2); // 只有我们自己的一个 ?
  });
});
