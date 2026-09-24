import { useEffect, useState } from 'react';
import { Plus, Rss } from 'lucide-react';

import { flattenItems, useFeeds, useFolders, useItems, useSidebarSummary } from '../../api/hooks';
import { Resizer } from '../../components/Resizer';
import { useReaderSearch } from '../../hooks/useReaderSearch';
import { Button } from '../../components/Button';
import { activeNav, applyItem, applyState } from '../../lib/scope';
import { LIST_KEY, LIST_SPLIT, loadWidth } from '../../lib/split';
import { useT, type Strings } from '../../lib/i18n';
import type { NavKey, SidebarSummary } from '../../types';
import { AddSourceDialog } from './AddSourceDialog';
import { ArticlePane } from './ArticlePane';
import { ItemList } from './ItemList';
import { PictureWall } from './PictureWall';
import { VideoGrid } from './VideoGrid';

type Mode = 'list' | 'pictures' | 'videos';

export function ReaderPage() {
  const t = useT();
  const { search, update } = useReaderSearch();
  const [listWidth, setListWidth] = useState(() => loadWidth(LIST_KEY, LIST_SPLIT));
  const [addOpen, setAddOpen] = useState(false);

  const itemsQuery = useItems(search);
  const feeds = useFeeds(null);
  const folders = useFolders();
  const summary = useSidebarSummary();

  const items = flattenItems(itemsQuery.data?.pages);
  // 一个源都没有时，内容区给「添加订阅源」的空态（设计稿的首页）
  const noFeeds = summary.data ? summary.data.feed_count === 0 : false;
  const defaultFolderId = search.folder && search.folder !== 'ungrouped' ? search.folder : null;
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

  // 标题文案走 i18n（viewTitle 那种硬编码中文的会漏翻）
  const navTitles: Record<NavKey, string> = {
    all: t.nav.all,
    essays: t.nav.essays,
    pictures: t.nav.pictures,
    videos: t.nav.videos,
    favorites: t.nav.favoritesItem,
  };
  const title =
    feedTitle ??
    (search.folder ? (folderName ?? t.list.folderFallback) : undefined) ??
    (search.fav ? t.nav.favoritesItem : navTitles[activeNav(search)]);
  const subtitle = buildSubtitle(t, mode, search.fav, summary.data);

  if (itemsQuery.isPending) {
    return (
      <div className="flex h-full items-center justify-center bg-surface text-sm text-ink-3">
        {t.loading}
      </div>
    );
  }

  if (noFeeds && mode === 'list') {
    return (
      <>
        <ItemList
          title={title}
          subtitle={subtitle}
          items={[]}
          search={search}
          selectedId={null}
          onSelect={() => {}}
          onState={(state) => update(applyState(state, search))}
          hasMore={false}
          loadingMore={false}
          onLoadMore={() => {}}
          listWidth={listWidth}
          onAddSource={() => setAddOpen(true)}
        />
        <Resizer
          label={t.list.resizeList}
          width={listWidth}
          onChange={setListWidth}
          config={LIST_SPLIT}
          storageKey={LIST_KEY}
        />
        <div className="flex h-full min-w-0 flex-1 flex-col items-center justify-center bg-surface">
          <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-soft text-brand-ink">
            <Rss size={22} />
          </span>
          <p className="mt-5 text-xl font-bold text-ink">{t.addSource.emptyTitle}</p>
          <p className="mt-2 text-xs text-ink-2">{t.addSource.emptyHint}</p>
          <Button
            variant="solid"
            className="mt-6"
            icon={<Plus size={15} />}
            onClick={() => setAddOpen(true)}
          >
            {t.addSource.listEntry}
          </Button>
          <p className="mt-4 text-2xs text-ink-3">{t.addSource.emptyNote}</p>
        </div>
        <AddSourceDialog open={addOpen} onOpenChange={setAddOpen} defaultFolderId={defaultFolderId} />
      </>
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
        onAddSource={() => setAddOpen(true)}
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

      <AddSourceDialog open={addOpen} onOpenChange={setAddOpen} defaultFolderId={defaultFolderId} />
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
