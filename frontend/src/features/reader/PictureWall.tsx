import { LayoutGrid, RefreshCw } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { useRefreshAll } from '../../api/hooks';
import { RemoteImage } from '../../components/RemoteImage';
import { IconButton } from '../../components/Button';
import { EmptyState } from '../../components/Field';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import { relativeTime } from '../../lib/format';
import { columnCount, distribute, estimateAspect, groupByColumn } from '../../lib/masonry';
import { useI18n, useT } from '../../lib/i18n';
import type { Item, ReaderSearch } from '../../types';

interface PictureWallProps {
  title: string;
  subtitle: string;
  items: Item[];
  search: ReaderSearch;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
}

const GAP = 18;

/** pictures：6 列瀑布流，条目高度由真实图片比例决定。 */
export function PictureWall({
  title,
  subtitle,
  items,
  search,
  hasMore,
  loadingMore,
  onLoadMore,
}: PictureWallProps) {
  const t = useT();
  const { locale } = useI18n();
  const surface = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(0);
  const sentinel = useInfiniteScroll(onLoadMore, { enabled: hasMore && !loadingMore });
  const refresh = useRefreshAll();

  useEffect(() => {
    const node = surface.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(entry.contentRect.width);
    });
    observer.observe(node);
    setWidth(node.clientWidth);
    return () => observer.disconnect();
  }, []);

  const columns = columnCount(Math.max(width, 320));
  const columnWidth = width > 0 ? (width - GAP * (columns - 1)) / columns : 0;

  const buckets = useMemo(() => {
    if (columnWidth <= 0) return [];
    const heights = items.map(
      (item) => columnWidth / estimateAspect(item.image_width, item.image_height) + 64,
    );
    return groupByColumn(items, distribute(heights, columns), columns);
  }, [items, columnWidth, columns]);

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
        <IconButton label={t.media.masonryLayout} active>
          <LayoutGrid size={15} />
        </IconButton>
      </header>

      <div ref={surface} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {items.length === 0 ? <EmptyState>{t.empty}</EmptyState> : null}

        <div className="flex items-start" style={{ gap: GAP }}>
          {buckets.map((column, columnIndex) => (
            <div key={columnIndex} className="flex flex-col" style={{ gap: GAP, flex: 1 }}>
              {column.map((item) => (
                <figure key={item.id} className="min-w-0">
                  {item.image_url ? (
                    <RemoteImage
                      src={item.image_url}
                      alt={item.title}
                      width={item.image_width}
                      height={item.image_height}
                      fallbackSeed={item.feed_title}
                      className="rounded-lg"
                    />
                  ) : (
                    <div className="flex aspect-[4/3] items-center justify-center rounded-lg bg-subtle text-xs text-ink-3">
                      {t.media.noImage}
                    </div>
                  )}
                  <figcaption className="mt-2">
                    <a
                      href={item.url ?? '#'}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="line-clamp-2 text-sm font-medium text-ink hover:text-brand-ink"
                    >
                      {item.title}
                    </a>
                    <p className="mt-0.5 text-2xs text-ink-3">
                      {relativeTime(item.published_at, locale)}
                    </p>
                  </figcaption>
                </figure>
              ))}
            </div>
          ))}
        </div>

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
