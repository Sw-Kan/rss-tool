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
  it('round-trips a folder + feed search', () => {
    const search: ReaderSearch = {
      kind: 'video',
      fav: false,
      folder: 'f1',
      feed: 'n1',
      state: 'unread',
      item: 'a1',
    };
    expect(parseSearch(toSearchParams(search))).toEqual(search);
  });

  it('round-trips a favorites search（收藏在二级，不带目录/源）', () => {
    const search: ReaderSearch = {
      kind: 'video',
      fav: true,
      folder: null,
      feed: null,
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

  it('drops fav when a folder is present（旧书签 / 后退不能重现目录里的收藏）', () => {
    const parsed = parseSearch(new URLSearchParams('kind=picture&fav=1&folder=tech'));
    expect(parsed).toMatchObject({ kind: 'picture', fav: false, folder: 'tech' });
    expect(apiParams(parsed)).toEqual({ kind: 'picture', folder_id: 'tech' });
  });

  it('drops fav when a feed is present', () => {
    expect(parseSearch(new URLSearchParams('fav=1&feed=sspai'))).toMatchObject({
      fav: false,
      feed: 'sspai',
    });
  });

  it('keeps fav on its own', () => {
    expect(parseSearch(new URLSearchParams('fav=1'))).toMatchObject({
      fav: true,
      folder: null,
      feed: null,
    });
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

  it('keeps the selected folder and the favorite flag', () => {
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

  it('keeps fav across kind switches（收藏只受一级路由影响）', () => {
    const favorites = applyNav('favorites', applyNav('pictures', defaultSearch()));
    expect(apiParams(applyNav('essays', favorites))).toEqual({
      kind: 'article',
      favorite: 'true',
    });
  });

  it('toggles fav off when the favorites entry is clicked again', () => {
    const favorites = applyNav('favorites', applyNav('pictures', defaultSearch()));
    expect(applyNav('favorites', favorites)).toMatchObject({ fav: false, kind: 'picture' });
  });

  it('entering favorites leaves the folder（收藏与目录同级）', () => {
    const inFolder = applyFolder('tech', applyNav('pictures', defaultSearch()));
    const favorites = applyNav('favorites', inFolder);
    expect(favorites.folder).toBeNull();
    expect(apiParams(favorites)).toEqual({ kind: 'picture', favorite: 'true' });
  });
});

describe('applyFolder / applyFeed / applyState / applyItem', () => {
  it('composes kind and folder as AND', () => {
    const base = applyNav('videos', defaultSearch());
    const scoped = applyFolder('tech', base);
    expect(apiParams(scoped)).toEqual({ kind: 'video', folder_id: 'tech' });
  });

  it('leaves the favorites view when a folder is picked（点收藏再点目录 = 目录本身）', () => {
    const favorites = applyNav('favorites', applyNav('pictures', defaultSearch()));
    const folder = applyFolder('tech', favorites);
    expect(folder.fav).toBe(false);
    expect(apiParams(folder)).toEqual({ kind: 'picture', folder_id: 'tech' });
  });

  it('leaves the favorites view when a feed is picked', () => {
    const favorites = applyNav('favorites', defaultSearch());
    expect(applyFeed('sspai', favorites).fav).toBe(false);
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
  it('reflects the kind row', () => {
    expect(activeNav(defaultSearch())).toBe('all');
    expect(activeNav(applyNav('videos', defaultSearch()))).toBe('videos');
  });

  it('keeps the kind row highlighted while favorites is on（两行同时高亮）', () => {
    const search = applyNav('favorites', applyNav('videos', defaultSearch()));
    expect(activeNav(search)).toBe('videos');
    expect(search.fav).toBe(true);
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

  it('says 收藏 for favorites, whatever the kind', () => {
    const search = applyNav('favorites', applyNav('pictures', defaultSearch()));
    expect(viewTitle(search, null)).toBe('收藏');
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
