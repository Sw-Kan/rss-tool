import { useEffect, useState } from 'react';

import { flattenItems, useFeeds, useFolders, useItems, useSidebarSummary } from '../../api/hooks';
import { Resizer } from '../../components/Resizer';
import { useReaderSearch } from '../../hooks/useReaderSearch';
import { applyItem, applyState, viewTitle } from '../../lib/scope';
import { LIST_KEY, LIST_SPLIT, loadWidth } from '../../lib/split';
import { useT, type Strings } from '../../lib/i18n';
import type { SidebarSummary } from '../../types';
import { ArticlePane } from './ArticlePane';
import { ItemList } from './ItemList';
import { PictureWall } from './PictureWall';
import { VideoGrid } from './VideoGrid';

type Mode = 'list' | 'pictures' | 'videos';

export function ReaderPage() {
  const t = useT();
  const { search, update } = useReaderSearch();
  const [listWidth, setListWidth] = useState(() => loadWidth(LIST_KEY, LIST_SPLIT));

  const itemsQuery = useItems(search);
  const feeds = useFeeds(null);
  const folders = useFolders();
  const summary = useSidebarSummary();

  const items = flattenItems(itemsQuery.data?.pages);
  const canLoadMore = Boolean(itemsQuery.hasNextPage) && !itemsQuery.isFetchingNextPage;
  const loadMore = () => {
    if (canLoadMore) void itemsQuery.fetchNextPage();
  };

  const selectedId = search.item ?? items[0]?.id ?? null;

  // 过滤条件变化时回到阅读器顶部
  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [search.kind, search.feed, search.folder, search.state, search.fav]);

  const mode: Mode =
    search.kind === 'picture' ? 'pictures' : search.kind === 'video' ? 'videos' : 'list';

  const folderName =
    folders.data?.items.find((folder) => folder.id === search.folder)?.name ??
    (search.folder === 'ungrouped' ? t.nav.ungrouped : null);

  const feedTitle = search.feed
    ? feeds.data?.items.find((feed) => feed.id === search.feed)?.title
    : null;

  const title = feedTitle ?? viewTitle(search, folderName);
  const subtitle = buildSubtitle(t, mode, search.fav, summary.data);

  if (itemsQuery.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-surface text-sm text-ink-3">
        {t.loading}
      </div>
    );
  }

  if (mode === 'pictures') {
    return (
      <PictureWall
        title={title}
        subtitle={subtitle}
        items={items}
        search={search}
        hasMore={canLoadMore}
        loadingMore={itemsQuery.isFetchingNextPage}
        onLoadMore={loadMore}
      />
    );
  }

  if (mode === 'videos') {
    return (
      <VideoGrid
        title={title}
        subtitle={subtitle}
        items={items}
        search={search}
        onSelect={(id) => update(applyItem(id, search))}
        hasMore={canLoadMore}
        loadingMore={itemsQuery.isFetchingNextPage}
        onLoadMore={loadMore}
      />
    );
  }

  return (
    <div className="flex h-full">
      <ItemList
        title={title}
        subtitle={subtitle}
        items={items}
        search={search}
        selectedId={selectedId}
        onSelect={(id) => update(applyItem(id, search))}
        onState={(state) => update(applyState(state, search))}
        hasMore={canLoadMore}
        loadingMore={itemsQuery.isFetchingNextPage}
        onLoadMore={loadMore}
        listWidth={listWidth}
      />

      <Resizer
        label={t.list.resizeList}
        width={listWidth}
        onChange={setListWidth}
        config={LIST_SPLIT}
        storageKey={LIST_KEY}
      />

      <ArticlePane
        itemId={selectedId}
        search={search}
        onNavigate={(id) => update(applyItem(id, search), { replace: true })}
      />
    </div>
  );
}

function buildSubtitle(
  t: Strings,
  mode: Mode,
  favorite: boolean,
  summary: SidebarSummary | undefined,
): string {
  if (!summary) return '';
  if (favorite) return t.list.favoriteSummary(summary.favorites);
  if (mode === 'pictures') {
    return t.list.pictureSummary(summary.by_kind.picture ?? 0, summary.feed_count);
  }
  if (mode === 'videos') {
    return t.list.videoSummary(summary.by_kind.video ?? 0, summary.feed_count);
  }
  return t.list.unreadSummary(summary.total_unread, summary.feed_count);
}
