// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { I18nProvider, bundles, detectLocale, isLocale, stringsFor, useT } from './index';
import { en } from './en';
import { zhCN } from './zh-CN';

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

function Probe() {
  const t = useT();
  return (
    <div>
      <span data-testid="all">{t.nav.all}</span>
      <span data-testid="summary">{t.list.unreadSummary(3, 2)}</span>
      <span data-testid="progress">{t.article.progress(1240, 3800)}</span>
    </div>
  );
}

describe('isLocale / detectLocale', () => {
  it('accepts only supported locales', () => {
    expect(isLocale('zh-CN')).toBe(true);
    expect(isLocale('en')).toBe(true);
    expect(isLocale('en-US')).toBe(false);
    expect(isLocale(null)).toBe(false);
    expect(isLocale('fr')).toBe(false);
  });

  it('prefers a stored choice over the browser language', () => {
    window.localStorage.setItem('rss-tool:locale', 'en');
    expect(detectLocale()).toBe('en');
  });

  it('falls back to the browser language', () => {
    Object.defineProperty(window.navigator, 'language', { value: 'zh-TW', configurable: true });
    expect(detectLocale()).toBe('zh-CN');

    Object.defineProperty(window.navigator, 'language', { value: 'fr-FR', configurable: true });
    expect(detectLocale()).toBe('en');
  });

  it('ignores a corrupted stored value', () => {
    window.localStorage.setItem('rss-tool:locale', 'klingon');
    Object.defineProperty(window.navigator, 'language', { value: 'zh-CN', configurable: true });
    expect(detectLocale()).toBe('zh-CN');
  });

  it('reads integers out of the corrupted value', () => {
    expect(stringsFor('en').list.unreadSummary(3, 2)).toBe('3 unread · 2 feeds');
    expect(stringsFor('zh-CN').list.unreadSummary(3, 2)).toBe('3 篇未读 · 2 个订阅源');
  });
});

describe('bundles', () => {
  it('exposes exactly the supported locales', () => {
    expect(Object.keys(bundles).sort()).toEqual(['en', 'zh-CN']);
    expect(bundles['zh-CN']).toBe(zhCN);
    expect(bundles.en).toBe(en);
  });
});

describe('useT', () => {
  it('defaults to Chinese without a provider', () => {
    render(<Probe />);
    expect(screen.getByTestId('all').textContent).toBe('全部');
  });

  it('follows the provider locale', () => {
    render(
      <I18nProvider initialLocale="en">
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId('all').textContent).toBe('All');
    expect(screen.getByTestId('summary').textContent).toBe('3 unread · 2 feeds');
    expect(screen.getByTestId('progress').textContent).toBe('Progress 1,240 / 3,800 words');
  });

  it('formats numbers per locale', () => {
    render(
      <I18nProvider initialLocale="zh-CN">
        <Probe />
      </I18nProvider>,
    );
    expect(screen.getByTestId('progress').textContent).toBe('阅读进度 1,240 / 3,800 字');
  });

  it('sets the document language', () => {
    render(
      <I18nProvider initialLocale="en">
        <Probe />
      </I18nProvider>,
    );
    expect(document.documentElement.lang).toBe('en');
  });
});
