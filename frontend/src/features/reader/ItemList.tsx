import { Check, Eye, EyeOff, Plus, RefreshCw } from 'lucide-react';
import { useBulkRead, useRefreshAll } from '../../api/hooks';
import { SourceLogo } from '../../components/Avatar';
import { IconButton } from '../../components/Button';
import { Chip, EmptyState } from '../../components/Field';
import { useInfiniteScroll } from '../../hooks/useInfiniteScroll';
import { relativeTime } from '../../lib/format';
import { useI18n, useT } from '../../lib/i18n';
import type { Item, ReaderSearch, ReadState } from '../../types';

interface ItemListProps {
  title: string;
  subtitle: string;
  items: Item[];
  search: ReaderSearch;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onState: (state: ReadState) => void;
  hasMore: boolean;
  loadingMore: boolean;
  onLoadMore: () => void;
  listWidth: number;
  onAddSource: () => void;
}

export function ItemList({
  title,
  subtitle,
  items,
  search,
  selectedId,
  onSelect,
  onState,
  hasMore,
  loadingMore,
  onLoadMore,
  listWidth,
  onAddSource,
}: ItemListProps) {
  const t = useT();
  const { locale } = useI18n();
  const sentinel = useInfiniteScroll(onLoadMore, { enabled: hasMore && !loadingMore });

  const refresh = useRefreshAll();
  const bulkRead = useBulkRead();

  const unreadIds = items.filter((item) => !item.is_read).map((item) => item.id);
  const readIds = items.filter((item) => item.is_read).map((item) => item.id);

  return (
    <section
      style={{ width: listWidth }}
      className="flex h-full shrink-0 flex-col border-r border-line bg-surface print:hidden"
    >
      <header className="shrink-0 px-4 pt-4">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold text-ink">{title}</h1>
            <p className="mt-0.5 truncate text-2xs text-ink-3">{subtitle}</p>
          </div>
          <div className="flex shrink-0 items-center gap-0.5">
            <IconButton label={t.addSource.listEntry} onClick={onAddSource}>
              <Plus size={15} />
            </IconButton>
            <IconButton
              label={t.list.refresh}
              onClick={() => refresh.mutate(search.folder === 'ungrouped' ? null : search.folder)}
              disabled={refresh.isPending}
            >
              <RefreshCw size={15} className={refresh.isPending ? 'animate-spin' : ''} />
            </IconButton>
            <IconButton
              label={t.list.markAllRead}
              disabled={unreadIds.length === 0 || bulkRead.isPending}
              onClick={() => bulkRead.mutate({ ids: unreadIds, is_read: true })}
            >
              <Eye size={15} />
            </IconButton>
            <IconButton
              label={t.list.markAllUnread}
              disabled={readIds.length === 0 || bulkRead.isPending}
              onClick={() => bulkRead.mutate({ ids: readIds, is_read: false })}
            >
              <EyeOff size={15} />
            </IconButton>
          </div>
        </div>

        <div className="mt-3 mb-2 flex items-center gap-1.5">
          {(['all', 'unread', 'read'] as ReadState[]).map((state) => (
            <Chip key={state} active={search.state === state} onClick={() => onState(state)}>
              {state === 'all'
                ? t.list.showAll
                : state === 'unread'
                  ? t.list.showUnread
                  : t.list.showRead}
            </Chip>
          ))}
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        {items.length === 0 ? <EmptyState>{t.empty}</EmptyState> : null}

        <ul className="space-y-1">
          {items.map((item) => {
            const selected = item.id === selectedId;
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => onSelect(item.id)}
                  className={`relative flex h-[84px] w-full flex-col justify-center gap-1 rounded-lg px-3 pr-2 text-left transition-colors ${
                    selected ? 'bg-soft' : 'hover:bg-subtle'
                  }`}
                >
                  {selected ? (
                    <span className="absolute top-2.5 bottom-2.5 left-0 w-[3px] rounded-xs bg-brand" />
                  ) : null}

                  <span className="flex items-center gap-2">
                    <SourceLogo name={item.feed_title} iconUrl={item.feed_icon_url} size={20} />
                    <span className="min-w-0 flex-1 truncate text-2xs text-ink-2">
                      {item.feed_title}
                    </span>
                    <span className="shrink-0 text-2xs text-ink-3">
                      {relativeTime(item.published_at, locale)}
                    </span>
                  </span>

                  <span className="flex items-center gap-2">
                    {item.is_read ? (
                      <Check size={13} className="shrink-0 text-ink-3" />
                    ) : null}
                    <span
                      className={`line-clamp-2 text-[13.5px] leading-[1.4] ${
                        selected
                          ? 'font-semibold text-on-soft'
                          : item.is_read
                            ? 'font-medium text-ink-2'
                            : 'font-medium text-ink'
                      }`}
                    >
                      {item.title}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>

        <div ref={sentinel} className="h-1" />
        {hasMore ? (
          <p className="py-3 text-center text-xs text-ink-3">{t.loading}</p>
        ) : items.length > 0 ? (
          <p className="py-3 text-center text-xs text-ink-3">{t.list.noMore}</p>
        ) : null}
      </div>
    </section>
  );
}
