import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import {
  Bookmark,
  ChevronDown,
  ChevronRight,
  FileText,
  Image as ImageIcon,
  LayoutGrid,
  MoreHorizontal,
  Pencil,
  Plus,
  Rss,
  Search,
  Trash2,
  Video,
} from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import {
  useCreateFolder,
  useDeleteFolder,
  useFeeds,
  useFolders,
  useRenameFolder,
  useSidebarSummary,
} from '../../api/hooks';
import { Avatar, SourceLogo } from '../../components/Avatar';
import { IconButton } from '../../components/Button';
import { SectionLabel, TextInput } from '../../components/Field';
import { useReaderSearch } from '../../hooks/useReaderSearch';
import { UNGROUPED, applyFeed, applyFolder, applyNav, activeNav } from '../../lib/scope';
import { strings } from '../../lib/strings';
import type { Feed, NavKey, ReaderSearch, User } from '../../types';
import { ProfileMenu } from './ProfileMenu';

const NAV_ICONS: Record<NavKey, typeof LayoutGrid> = {
  all: LayoutGrid,
  essays: FileText,
  pictures: ImageIcon,
  videos: Video,
  favorites: Bookmark,
};

const NAV_LABELS: Record<NavKey, string> = {
  all: strings.nav.all,
  essays: strings.nav.essays,
  pictures: strings.nav.pictures,
  videos: strings.nav.videos,
  favorites: strings.nav.favoritesItem,
};

interface SidebarProps {
  user: User | null;
  search: ReaderSearch;
  onOpenSettings: () => void;
}

export function Sidebar({ user, search, onOpenSettings }: SidebarProps) {
  const { update } = useReaderSearch();
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(new Set());
  const [renaming, setRenaming] = useState<string | null>(null);

  const summary = useSidebarSummary();
  const folders = useFolders();
  const feeds = useFeeds(null);
  const createFolder = useCreateFolder();
  const renameFolder = useRenameFolder();
  const deleteFolder = useDeleteFolder();

  const counts = summary.data;
  const current = activeNav(search);
  const folderList = folders.data?.items ?? [];

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

  const navCount = (key: NavKey): number => {
    if (key === 'favorites') return counts?.favorites ?? 0;
    if (key === 'all') return counts?.by_kind.all ?? 0;
    if (key === 'essays') return counts?.by_kind.article ?? 0;
    if (key === 'pictures') return counts?.by_kind.picture ?? 0;
    return counts?.by_kind.video ?? 0;
  };

  const ungroupedFeeds = feedsByFolder.get(UNGROUPED) ?? [];

  return (
    <aside className="flex h-full flex-col bg-page">
      <header className="flex items-center gap-3 px-5 pt-5 pb-3">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-soft text-brand-ink">
          <Rss size={15} />
        </span>
        <span className="flex-1 text-lg font-bold text-ink">{strings.appName}</span>
        <IconButton
          label={strings.nav.searchPlaceholder}
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
            placeholder={strings.nav.searchPlaceholder}
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
                  <span className="flex-1 text-left">{NAV_LABELS[key]}</span>
                  <span className="text-xs text-ink-3">{navCount(key)}</span>
                </button>
              </li>
            );
          })}
        </ul>

        <div className="mt-4 mb-2">
          <SectionLabel>{strings.nav.favorites}</SectionLabel>
        </div>
        <button
          type="button"
          onClick={() => update(applyNav('favorites', search))}
          className={`flex h-[34px] w-full items-center gap-3 rounded-lg px-4 text-sm transition-colors ${
            current === 'favorites' ? 'bg-soft text-on-soft' : 'text-ink hover:bg-subtle'
          }`}
        >
          <Bookmark size={15} />
          <span className="flex-1 text-left">{strings.nav.favoritesItem}</span>
          <span className="text-xs text-ink-3">{counts?.favorites ?? 0}</span>
        </button>

        <div className="mt-4 mb-2 flex items-center justify-between pr-2">
          <SectionLabel>{strings.nav.folders}</SectionLabel>
          <IconButton
            label={strings.nav.newFolder}
            size={22}
            onClick={() => {
              const name = window.prompt(strings.nav.folderName);
              if (name?.trim()) createFolder.mutate(name.trim());
            }}
          >
            <Plus size={13} />
          </IconButton>
        </div>

        {folderList.length === 0 ? (
          <p className="px-4 py-2 text-xs text-ink-3">{strings.nav.emptyFolders}</p>
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
                  <div
                    className={`group flex h-[34px] items-center rounded-lg pr-1 ${
                      selected ? 'bg-soft' : ''
                    }`}
                  >
                    <IconButton
                      label={isOpen ? '收起目录' : '展开目录'}
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

                    <DropdownMenu.Root>
                      <DropdownMenu.Trigger asChild>
                        <button
                          type="button"
                          aria-label="目录操作"
                          className="hidden h-6 w-6 items-center justify-center rounded-md text-ink-3 hover:bg-subtle group-hover:flex"
                        >
                          <MoreHorizontal size={14} />
                        </button>
                      </DropdownMenu.Trigger>
                      <DropdownMenu.Portal>
                        <DropdownMenu.Content
                          sideOffset={4}
                          className="z-50 min-w-36 rounded-lg border border-line bg-surface p-1 text-sm shadow-[var(--shadow-pop)]"
                        >
                          <MenuItem
                            icon={<Pencil size={13} />}
                            onSelect={() => setRenaming(folder.id)}
                          >
                            重命名
                          </MenuItem>
                          <MenuItem
                            danger
                            icon={<Trash2 size={13} />}
                            onSelect={() => deleteFolder.mutate(folder.id)}
                          >
                            删除目录
                          </MenuItem>
                        </DropdownMenu.Content>
                      </DropdownMenu.Portal>
                    </DropdownMenu.Root>
                  </div>

                  {isOpen ? (
                    <ul className="mt-0.5 mb-1 space-y-0.5 pl-8">
                      {children.length === 0 ? (
                        <li className="px-2 py-1 text-xs text-ink-3">目录为空</li>
                      ) : null}
                      {children
                        .filter((feed) => matches(feed.title))
                        .map((feed) => (
                          <li key={feed.id}>
                            <button
                              type="button"
                              onClick={() =>
                                update(applyFeed(feed.id, applyFolder(folder.id, search)))
                              }
                              className={`flex h-8 w-full items-center gap-2.5 rounded-lg px-2 text-left text-sm transition-colors ${
                                search.feed === feed.id
                                  ? 'bg-soft text-on-soft'
                                  : 'text-ink hover:bg-subtle'
                              }`}
                            >
                              <SourceLogo name={feed.title} iconUrl={feed.icon_url} size={18} />
                              <span className="min-w-0 flex-1 truncate">{feed.title}</span>
                              <span className="text-xs text-ink-3">
                                {counts?.feeds[feed.id] ?? 0}
                              </span>
                            </button>
                          </li>
                        ))}
                    </ul>
                  ) : null}
                </li>
              );
            })}
        </ul>

        <div className="mt-4 mb-2">
          <SectionLabel>{strings.nav.ungrouped}</SectionLabel>
        </div>
        {ungroupedFeeds.length === 0 ? (
          <p className="px-4 py-1 text-xs text-ink-3">没有未分组的源</p>
        ) : null}
        <ul className="space-y-0.5">
          {ungroupedFeeds
            .filter((feed) => matches(feed.title))
            .map((feed) => (
              <li key={feed.id}>
                <button
                  type="button"
                  onClick={() => update(applyFeed(feed.id, applyFolder(null, search)))}
                  className={`flex h-8 w-full items-center gap-2.5 rounded-lg px-4 text-left text-sm transition-colors ${
                    search.feed === feed.id ? 'bg-soft text-on-soft' : 'text-ink hover:bg-subtle'
                  }`}
                >
                  <SourceLogo name={feed.title} iconUrl={feed.icon_url} size={18} />
                  <span className="min-w-0 flex-1 truncate">{feed.title}</span>
                  <span className="text-xs text-ink-3">{counts?.feeds[feed.id] ?? 0}</span>
                </button>
              </li>
            ))}
        </ul>

        <div className="mt-4 mb-1">
          <SectionLabel>{strings.nav.stats}</SectionLabel>
        </div>
        <p className="px-4 text-xs text-ink-3">
          {folderList.length} 目录 · {ungroupedFeeds.length} 未分组源
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
    </aside>
  );
}

function MenuItem({
  icon,
  children,
  onSelect,
  danger = false,
}: {
  icon: ReactNode;
  children: ReactNode;
  onSelect: () => void;
  danger?: boolean;
}) {
  return (
    <DropdownMenu.Item
      onSelect={onSelect}
      className={`flex cursor-pointer items-center gap-2 rounded-md px-2.5 py-2 outline-none data-[highlighted]:bg-subtle ${
        danger ? 'text-danger-ink' : 'text-ink'
      }`}
    >
      {icon}
      {children}
    </DropdownMenu.Item>
  );
}
