import * as ContextMenu from '@radix-ui/react-context-menu';
import {
  Bookmark,
  ChevronDown,
  ChevronRight,
  FileText,
  FolderPlus,
  Image as ImageIcon,
  LayoutGrid,
  Pencil,
  Plus,
  Rss,
  Search,
  Trash2,
  Video,
} from 'lucide-react';
import { useMemo, useState, type PointerEvent as ReactPointerEvent } from 'react';

import {
  useCreateFolder,
  useDeleteFolder,
  useFeeds,
  useFolders,
  useRenameFolder,
  useSidebarSummary,
  useUpdateFeed,
} from '../../api/hooks';
import { Avatar, SourceLogo } from '../../components/Avatar';
import { IconButton } from '../../components/Button';
import { ConfirmDialog } from '../../components/ConfirmDialog';
import { SectionLabel, TextInput } from '../../components/Field';
import { useLongPressDrag } from '../../hooks/useLongPressDrag';
import { useReaderSearch } from '../../hooks/useReaderSearch';
import { useT } from '../../lib/i18n';
import { UNGROUPED, applyFeed, applyFolder, applyNav, activeNav } from '../../lib/scope';
import type { Feed, NavKey, ReaderSearch, User } from '../../types';
import { ProfileMenu } from './ProfileMenu';

const NAV_ICONS: Record<NavKey, typeof LayoutGrid> = {
  all: LayoutGrid,
  essays: FileText,
  pictures: ImageIcon,
  videos: Video,
  favorites: Bookmark,
};

const MENU_ITEM =
  'flex cursor-pointer items-center gap-2.5 rounded-md px-2.5 py-2 text-sm text-ink outline-none data-[highlighted]:bg-subtle data-[disabled]:opacity-40';

interface SidebarProps {
  user: User | null;
  search: ReaderSearch;
  onOpenSettings: () => void;
}

export function Sidebar({ user, search, onOpenSettings }: SidebarProps) {
  const t = useT();
  const { update } = useReaderSearch();

  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [renaming, setRenaming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<{ id: string; name: string } | null>(null);

  const summary = useSidebarSummary();
  const folders = useFolders();
  const feeds = useFeeds(null);
  const createFolder = useCreateFolder();
  const renameFolder = useRenameFolder();
  const deleteFolder = useDeleteFolder();
  const { mutate: updateFeed } = useUpdateFeed();

  const counts = summary.data;
  const current = activeNav(search);
  const folderList = folders.data?.items ?? [];

  const navLabels: Record<NavKey, string> = {
    all: t.nav.all,
    essays: t.nav.essays,
    pictures: t.nav.pictures,
    videos: t.nav.videos,
    favorites: t.nav.favoritesItem,
  };

  const feedsByFolder = useMemo(() => {
    const map = new Map<string, Feed[]>();
    for (const feed of feeds.data?.items ?? []) {
      const key = feed.folder_id ?? UNGROUPED;
      const bucket = map.get(key);
      if (bucket) bucket.push(feed);
      else map.set(key, [feed]);
    }
    return map;
  }, [feeds.data]);

  const needle = query.trim().toLowerCase();
  const matches = (value: string) => needle === '' || value.toLowerCase().includes(needle);

  const newFolder = () => {
    const name = window.prompt(t.folderMenu.promptName);
    if (name?.trim()) createFolder.mutate(name.trim());
  };

  const navCount = (key: NavKey): number => {
    if (key === 'favorites') return counts?.favorites ?? 0;
    if (key === 'all') return counts?.by_kind.all ?? 0;
    if (key === 'essays') return counts?.by_kind.article ?? 0;
    if (key === 'pictures') return counts?.by_kind.picture ?? 0;
    return counts?.by_kind.video ?? 0;
  };

  const ungroupedFeeds = feedsByFolder.get(UNGROUPED) ?? [];
  const allFeeds = feeds.data?.items ?? [];

  /** 拖到目录行 / 未分组区块就改订阅的 folder_id（后端 PATCH 已支持，无前端新接口）。 */
  const drag = useLongPressDrag({
    onDrop: (feedId, target) => {
      if (target === null) return;
      const feed = allFeeds.find((item) => item.id === feedId);
      if (!feed) return;
      if (target === UNGROUPED) {
        if (feed.folder_id !== null) updateFeed({ id: feedId, clearFolder: true });
        return;
      }
      if (feed.folder_id !== target) updateFeed({ id: feedId, folderId: target });
    },
  });
  const draggedFeed = allFeeds.find((feed) => feed.id === drag.draggingId) ?? null;

  return (
    <aside className="flex h-full flex-col bg-page">
      <header className="flex items-center gap-3 px-5 pt-5 pb-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-soft text-brand-ink">
          <Rss size={15} />
        </span>
        <span className="flex-1 text-lg font-bold text-ink">{t.appName}</span>
        <IconButton
          label={t.nav.searchPlaceholder}
          active={searching}
          onClick={() => {
            setSearching((value) => !value);
            setQuery('');
          }}
        >
          <Search size={15} />
        </IconButton>
      </header>

      {searching ? (
        <div className="px-4 pb-2">
          <TextInput
            autoFocus
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={t.nav.searchPlaceholder}
            className="h-9 text-sm"
          />
        </div>
      ) : null}

      <nav className="min-h-0 flex-1 overflow-y-auto px-4 pb-4">
        <ul className="space-y-1">
          {(['all', 'essays', 'pictures', 'videos'] as NavKey[]).map((key) => {
            const Icon = NAV_ICONS[key];
            const selected = current === key;
            return (
              <li key={key}>
                <button
                  type="button"
                  onClick={() => update(applyNav(key, search))}
                  className={`flex h-10 w-full items-center gap-3 rounded-lg px-3.5 text-base font-semibold transition-colors ${
                    selected ? 'bg-soft text-on-soft' : 'text-ink hover:bg-subtle'
                  }`}
                >
                  <Icon size={15} />
                  <span className="flex-1 text-left">{navLabels[key]}</span>
                  <span className="text-xs text-ink-3">{navCount(key)}</span>
                </button>
              </li>
            );
          })}
        </ul>

        <div className="mt-4 mb-2">
          <SectionLabel>{t.nav.favorites}</SectionLabel>
        </div>
        <button
          type="button"
          onClick={() => update(applyNav('favorites', search))}
          className={`flex h-[34px] w-full items-center gap-3 rounded-lg px-4 text-sm transition-colors ${
            search.fav ? 'bg-soft text-on-soft' : 'text-ink hover:bg-subtle'
          }`}
        >
          <Bookmark size={15} />
          <span className="flex-1 text-left">{t.nav.favoritesItem}</span>
          <span className="text-xs text-ink-3">{counts?.favorites ?? 0}</span>
        </button>

        {/* 整个「RSS 目录」区块都能右键：在空白处右键只给新建，在目录上右键给三项 */}
        <ContextMenu.Root>
          <ContextMenu.Trigger asChild>
            <div>
              <div className="mt-4 mb-2 flex items-center justify-between pr-2">
                <SectionLabel>{t.nav.folders}</SectionLabel>
                <IconButton label={t.nav.newFolder} size={22} onClick={newFolder}>
                  <Plus size={13} />
                </IconButton>
              </div>

              {folderList.length === 0 ? (
                <p className="px-4 py-2 text-xs text-ink-3">{t.nav.emptyFolders}</p>
              ) : null}

              <ul>
                {folderList
                  .filter((folder) => matches(folder.name))
                  .map((folder) => {
                    const isOpen = expanded.has(folder.id);
                    const selected = search.folder === folder.id;
                    const children = feedsByFolder.get(folder.id) ?? [];
                    return (
                      <li key={folder.id}>
                        <ContextMenu.Root>
                          <ContextMenu.Trigger asChild>
                            <div
                              data-drop={folder.id}
                              onPointerEnter={() => drag.handleTargetEnter(folder.id)}
                              onPointerLeave={() => drag.handleTargetLeave(folder.id)}
                              className={`flex h-[34px] items-center rounded-lg pr-1 ${
                                selected ? 'bg-soft' : ''
                              } ${
                                drag.overId === folder.id
                                  ? 'bg-soft ring-2 ring-brand'
                                  : 'hover:bg-subtle'
                              }`}
                            >
                              <IconButton
                                label={isOpen ? t.nav.collapseFolder : t.nav.expandFolder}
                                size={22}
                                className="ml-1"
                                onClick={() =>
                                  setExpanded((previous) => {
                                    const next = new Set(previous);
                                    if (next.has(folder.id)) next.delete(folder.id);
                                    else next.add(folder.id);
                                    return next;
                                  })
                                }
                              >
                                {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                              </IconButton>

                              {renaming === folder.id ? (
                                <input
                                  autoFocus
                                  defaultValue={folder.name}
                                  className="h-7 min-w-0 flex-1 rounded-md border border-line bg-surface px-2 text-sm outline-none"
                                  onBlur={(event) => {
                                    const name = event.target.value.trim();
                                    if (name && name !== folder.name) {
                                      renameFolder.mutate({ id: folder.id, name });
                                    }
                                    setRenaming(null);
                                  }}
                                  onKeyDown={(event) => {
                                    if (event.key === 'Enter') event.currentTarget.blur();
                                    if (event.key === 'Escape') setRenaming(null);
                                  }}
                                />
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => update(applyFolder(folder.id, search))}
                                  className={`min-w-0 flex-1 truncate text-left text-sm ${
                                    selected ? 'text-on-soft' : 'text-ink'
                                  }`}
                                >
                                  {folder.name}
                                </button>
                              )}

                              <span className="px-2 text-xs text-ink-3">
                                {counts?.folders[folder.id] ?? 0}
                              </span>
                            </div>
                          </ContextMenu.Trigger>
                          <FolderMenu
                            onNew={newFolder}
                            onRename={() => setRenaming(folder.id)}
                            onDelete={() => setDeleting(folder)}
                          />
                        </ContextMenu.Root>

                        {isOpen ? (
                          <ul className="mt-0.5 mb-1 space-y-0.5 pl-8">
                            {children.length === 0 ? (
                              <li className="px-2 py-1 text-xs text-ink-3">{t.nav.emptyFolder}</li>
                            ) : null}
                            {children
                              .filter((feed) => matches(feed.title))
                              .map((feed) => (
                                <li key={feed.id}>
                                  <FeedItem
                                    feed={feed}
                                    count={counts?.feeds[feed.id] ?? 0}
                                    selected={search.feed === feed.id}
                                    dragging={drag.draggingId === feed.id}
                                    className="px-2"
                                    onDragStart={(event) => drag.handlePointerDown(feed.id, event)}
                                    onSelect={() => {
                                      if (drag.takeSwallowedClick()) return;
                                      update(applyFeed(feed.id, applyFolder(folder.id, search)));
                                    }}
                                  />
                                </li>
                              ))}
                          </ul>
                        ) : null}
                      </li>
                    );
                  })}
              </ul>
            </div>
          </ContextMenu.Trigger>
          <FolderMenu onNew={newFolder} />
        </ContextMenu.Root>

        {/* 「未分组源」整块都是落点：把源从目录里拖出来就是放到这里 */}
        <div
          data-drop={UNGROUPED}
          onPointerEnter={() => drag.handleTargetEnter(UNGROUPED)}
          onPointerLeave={() => drag.handleTargetLeave(UNGROUPED)}
          className={`mt-4 rounded-lg pb-1 ${
            drag.overId === UNGROUPED ? 'bg-soft ring-2 ring-brand' : ''
          }`}
        >
          <div className="mb-2">
            <SectionLabel>{t.nav.ungrouped}</SectionLabel>
          </div>
          {ungroupedFeeds.length === 0 ? (
            <p className="px-4 py-1 text-xs text-ink-3">{t.nav.noUngrouped}</p>
          ) : null}
          <ul className="space-y-0.5">
            {ungroupedFeeds
              .filter((feed) => matches(feed.title))
              .map((feed) => (
                <li key={feed.id}>
                  <FeedItem
                    feed={feed}
                    count={counts?.feeds[feed.id] ?? 0}
                    selected={search.feed === feed.id}
                    dragging={drag.draggingId === feed.id}
                    className="px-4"
                    onDragStart={(event) => drag.handlePointerDown(feed.id, event)}
                    onSelect={() => {
                      if (drag.takeSwallowedClick()) return;
                      update(applyFeed(feed.id, applyFolder(null, search)));
                    }}
                  />
                </li>
              ))}
          </ul>
        </div>

        <div className="mt-4 mb-1">
          <SectionLabel>{t.nav.stats}</SectionLabel>
        </div>
        <p className="px-4 text-xs text-ink-3">
          {t.nav.folderStats(folderList.length, ungroupedFeeds.length)}
        </p>
      </nav>

      <footer className="shrink-0 border-t border-line px-4 py-3">
        <ProfileMenu user={user} onOpenSettings={onOpenSettings}>
          <button
            type="button"
            className="flex h-16 w-full items-center gap-3 rounded-lg px-2 text-left transition-colors hover:bg-subtle"
          >
            <Avatar
              name={user?.username ?? '?'}
              color={user?.avatar_type === 'letter' ? user.avatar_color : undefined}
              imageUrl={user?.avatar_url}
              size={40}
            />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-base font-medium text-ink">
                {user?.username ?? ''}
              </span>
              <span className="block truncate text-xs text-ink-3">{user?.email ?? ''}</span>
            </span>
            <ChevronDown size={15} className="text-ink-3" />
          </button>
        </ProfileMenu>
      </footer>

      {/* 拖影：跟着指针走的源行副本（fixed，不受侧边栏滚动裁剪） */}
      {draggedFeed && drag.point ? (
        <div
          style={{ left: drag.point.x, top: drag.point.y }}
          className="pointer-events-none fixed z-50 flex h-8 max-w-[240px] items-center gap-2.5 rounded-lg border border-line bg-surface px-2.5 text-sm text-ink shadow-[var(--shadow-pop)]"
        >
          <SourceLogo name={draggedFeed.title} iconUrl={draggedFeed.icon_url} size={18} />
          <span className="min-w-0 flex-1 truncate">{draggedFeed.title}</span>
        </div>
      ) : null}

      <ConfirmDialog
        open={deleting !== null}
        onOpenChange={(open) => {
          if (!open) setDeleting(null);
        }}
        title={t.folderMenu.deleteTitle}
        body={deleting ? t.folderMenu.deleteBody(deleting.name) : ''}
        pending={deleteFolder.isPending}
        onConfirm={() => {
          if (deleting) deleteFolder.mutate(deleting.id);
          setDeleting(null);
        }}
      />
    </aside>
  );
}

/** 源行：点击切源；鼠标长按可拖到别的目录（见 `useLongPressDrag`）。 */
function FeedItem({
  feed,
  count,
  selected,
  dragging,
  className,
  onDragStart,
  onSelect,
}: {
  feed: Feed;
  count: number;
  selected: boolean;
  dragging: boolean;
  className?: string;
  onDragStart: (event: ReactPointerEvent) => void;
  onSelect: () => void;
}) {
  const t = useT();
  return (
    <button
      type="button"
      // 拖拽是隐藏手势，用原生 title 做一次发现性提示（文案走 i18n）
      title={t.nav.dragHint}
      onPointerDown={onDragStart}
      onClick={onSelect}
      className={`flex h-8 w-full items-center gap-2.5 rounded-lg text-left text-sm transition-colors ${className ?? ''} ${
        selected ? 'bg-soft text-on-soft' : 'text-ink hover:bg-subtle'
      } ${dragging ? 'cursor-grabbing opacity-50' : ''}`}
    >
      <SourceLogo name={feed.title} iconUrl={feed.icon_url} size={18} />
      <span className="min-w-0 flex-1 truncate">{feed.title}</span>
      <span className="text-xs text-ink-3">{count}</span>
    </button>
  );
}

/** 目录右键菜单。空白处右键时只给「新建目录」，重命名/删除置灰。 */
function FolderMenu({
  onNew,
  onRename,
  onDelete,
}: {
  onNew: () => void;
  onRename?: () => void;
  onDelete?: () => void;
}) {
  const t = useT();
  return (
    <ContextMenu.Portal>
      <ContextMenu.Content className="z-50 min-w-[176px] rounded-[10px] border border-line bg-surface p-1 shadow-[var(--shadow-pop)]">
        <ContextMenu.Item onSelect={onNew} className={MENU_ITEM}>
          <FolderPlus size={15} className="text-ink-3" />
          {t.folderMenu.newFolder}
        </ContextMenu.Item>
        <ContextMenu.Item onSelect={onRename} disabled={!onRename} className={MENU_ITEM}>
          <Pencil size={15} className="text-ink-3" />
          {t.folderMenu.renameFolder}
        </ContextMenu.Item>
        <ContextMenu.Separator className="my-1 h-px bg-line" />
        <ContextMenu.Item onSelect={onDelete} disabled={!onDelete} className={`${MENU_ITEM} text-danger-ink`}>
          <Trash2 size={15} className="text-danger" />
          {t.folderMenu.deleteFolder}
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Portal>
  );
}
