import { LayoutGrid, RefreshCw } from 'lucide-react';

import { useRefreshAll } from '../../api/hooks';
import { IconButton } from '../../components/Button';
import { EmptyState } from '../../components/Field';
import { RemoteImage } from '../../components/RemoteImage';
import { SourceLogo } from '../../components/Avatar';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import { relativeTime } from '../../lib/format';
import { useI18n, useT } from '../../lib/i18n';
import type { Item, ReaderSearch } from '../../types';

interface VideoGridProps {
  title: string;
  subtitle: string;
  items: Item[];
  search: ReaderSearch;
  onSelect: (id: string) => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}

/** videos：响应式网格，≥1280px 固定 5 列，卡片 16:9。 */
export function VideoGrid({
  title,
  subtitle,
  items,
  search,
  onSelect,
  hasMore,
  loadingMore,
  onLoadMore,
}: VideoGridProps) {
  const t = useT();
  const { locale } = useI18n();
  const sentinel = useInfiniteScroll(onLoadMore, { enabled: hasMore && !loadingMore });
  const refresh = useRefreshAll();

  return (
    <div className="flex h-full flex-col bg-page">
      <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface px-6">
        <div className="min-w-0 flex-1">
          <h1 className="text-base font-semibold text-ink">{title}</h1>
          <p className="mt-0.5 text-2xs text-ink-3">{subtitle}</p>
        </div>
        <IconButton
          label={t.list.refresh}
          disabled={refresh.isPending}
          onClick={() => refresh.mutate(search.folder === 'ungrouped' ? null : search.folder)}
        >
          <RefreshCw size={15} className={refresh.isPending ? 'animate-spin' : ''} />
        </IconButton>
        <IconButton label={t.media.gridLayout} active>
          <LayoutGrid size={15} />
        </IconButton>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {items.length === 0 ? <EmptyState>{t.empty}</EmptyState> : null}

        <ul className="grid grid-cols-2 gap-x-[17px] gap-y-10 sm:grid-cols-3 lg:grid-cols-4 min-[1280px]:grid-cols-5">
          {items.map((item) => (
            <li key={item.id}>
              <button type="button" onClick={() => onSelect(item.id)} className="w-full text-left">
                {item.image_url ? (
                  <RemoteImage
                    src={item.image_url}
                    alt={item.title}
                    width={item.image_width ?? 16}
                    height={item.image_height ?? 9}
                    fallbackSeed={item.feed_title}
                    className="aspect-video rounded-lg"
                  />
                ) : (
                  <span className="flex aspect-video items-center justify-center rounded-lg bg-subtle text-xs text-ink-3">
                    {t.media.noCover}
                  </span>
                )}

                <span className="mt-2 line-clamp-2 block text-sm font-medium text-ink">
                  {item.title}
                </span>
                <span className="mt-1 block text-xs text-ink-2">
                  {item.channel_name ?? item.feed_title}
                </span>
                <span className="mt-0.5 flex items-center gap-1.5 text-2xs text-ink-3">
                  <SourceLogo name={item.feed_title} iconUrl={item.feed_icon_url} size={14} />
                  {item.feed_title} · {relativeTime(item.published_at, locale)}
                </span>
              </button>
            </li>
          ))}
        </ul>

        <div ref={sentinel} className="h-1" />
        {hasMore ? (
          <p className="py-4 text-center text-xs text-ink-3">{t.loading}</p>
        ) : items.length > 0 ? (
          <p className="py-4 text-center text-xs text-ink-3">{t.list.noMore}</p>
        ) : null}
      </div>
    </div>
  );
}
