import { describe, expect, it } from 'vitest';

import type { ReaderSearch } from '../types';
import {
  activeNav,
  apiParams,
  applyFeed,
  applyFolder,
  applyItem,
  applyNav,
  applyState,
  defaultSearch,
  isSameSearch,
  parseSearch,
  queryKeyFor,
  toSearchParams,
  viewTitle,
} from './scope';

describe('parseSearch / toSearchParams', () => {
  it('round-trips a fully specified search', () => {
    const search: ReaderSearch = {
      kind: 'video',
      fav: true,
      folder: 'f1',
      feed: 'n1',
      state: 'unread',
      item: 'a1',
    };
    expect(parseSearch(toSearchParams(search))).toEqual(search);
  });

  it('omits defaults to keep the URL short', () => {
    expect(toSearchParams(defaultSearch()).toString()).toBe('');
  });

  it('falls back to defaults on invalid values', () => {
    const parsed = parseSearch(new URLSearchParams('kind=podcast&state=maybe&fav=0'));
    expect(parsed).toEqual(defaultSearch());
  });

  it('trims blank params', () => {
    const parsed = parseSearch(new URLSearchParams('folder=%20%20&item='));
    expect(parsed.folder).toBeNull();
    expect(parsed.item).toBeNull();
  });
});

describe('applyNav', () => {
  it('maps each nav entry to its kind', () => {
    expect(applyNav('all', defaultSearch()).kind).toBeNull();
    expect(applyNav('essays', defaultSearch()).kind).toBe('article');
    expect(applyNav('pictures', defaultSearch()).kind).toBe('picture');
    expect(applyNav('videos', defaultSearch()).kind).toBe('video');
    expect(applyNav('favorites', defaultSearch()).fav).toBe(true);
  });

  it('keeps the selected folder but drops feed and article', () => {
    const current: ReaderSearch = {
      ...defaultSearch(),
      folder: 'tech',
      feed: 'sspai',
      item: 'a1',
    };
    const next = applyNav('pictures', current);
    expect(next.folder).toBe('tech');
    expect(next.feed).toBeNull();
    expect(next.item).toBeNull();
    expect(next.kind).toBe('picture');
  });

  it('clears fav when leaving the favorites entry', () => {
    const favorites = applyNav('favorites', defaultSearch());
    expect(applyNav('all', favorites).fav).toBe(false);
  });
});

describe('applyFolder / applyFeed / applyState / applyItem', () => {
  it('composes kind and folder as AND', () => {
    const base = applyNav('videos', defaultSearch());
    const scoped = applyFolder('tech', base);
    expect(apiParams(scoped)).toEqual({ kind: 'video', folder_id: 'tech' });
  });

  it('keeps kind when switching folders', () => {
    const base = applyFolder('tech', applyNav('pictures', defaultSearch()));
    expect(applyFolder('design', base).kind).toBe('picture');
  });

  it('drops the article when the feed changes', () => {
    const base = applyItem('a1', applyFeed('sspai', defaultSearch()));
    expect(applyFeed('infoq', base)).toMatchObject({ feed: 'infoq', item: null });
  });

  it('state is orthogonal to everything else', () => {
    const base = applyFolder('tech', applyNav('essays', defaultSearch()));
    expect(applyState('unread', base)).toMatchObject({ state: 'unread', folder: 'tech' });
  });
});

describe('activeNav', () => {
  it('reflects kind and favorites', () => {
    expect(activeNav(defaultSearch())).toBe('all');
    expect(activeNav(applyNav('videos', defaultSearch()))).toBe('videos');
    expect(activeNav(applyNav('favorites', defaultSearch()))).toBe('favorites');
  });

  it('prefers favorites over kind (收藏的视频 高亮收藏)', () => {
    const search = applyNav('favorites', applyNav('videos', defaultSearch()));
    expect(activeNav(search)).toBe('favorites');
  });
});

describe('apiParams', () => {
  it('maps ungrouped folder to none', () => {
    expect(apiParams({ ...defaultSearch(), folder: 'ungrouped' })).toEqual({
      folder_id: 'none',
    });
  });

  it('emits favorite=true only when set', () => {
    expect(apiParams({ ...defaultSearch(), fav: true })).toEqual({ favorite: 'true' });
    expect(apiParams(defaultSearch())).toEqual({});
  });

  it('omits state=all', () => {
    expect(apiParams({ ...defaultSearch(), state: 'all' })).toEqual({});
    expect(apiParams({ ...defaultSearch(), state: 'read' })).toEqual({ state: 'read' });
  });
});

describe('viewTitle', () => {
  it('prefers the folder name', () => {
    const search = { ...defaultSearch(), folder: 'tech' };
    expect(viewTitle(search, '技术')).toBe('技术');
    expect(viewTitle(search, null)).toBe('目录');
  });

  it('falls back to the nav label', () => {
    expect(viewTitle(applyNav('pictures', defaultSearch()), null)).toBe('图片');
  });
});

describe('isSameSearch / queryKeyFor', () => {
  it('treats different orderings of the same filters as equal', () => {
    const a: ReaderSearch = { ...defaultSearch(), kind: 'picture', folder: 'tech' };
    const b: ReaderSearch = { ...defaultSearch(), folder: 'tech', kind: 'picture' };
    expect(isSameSearch(a, b)).toBe(true);
    expect(queryKeyFor(a)).toBe(queryKeyFor(b));
    expect(queryKeyFor(a)).toBe('kind=picture&folder_id=tech');
  });
});
