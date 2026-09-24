import { Plus, Trash2 } from 'lucide-react';
import { useRef, useState, type ReactNode } from 'react';

import {
  exportOpml,
  exportUserData,
  useClearLocalData,
  useCreateFeed,
  useDeleteFeed,
  useFeeds,
  useFolders,
  useImportOpml,
  useUpdateFeed,
} from '../../api/hooks';
import { SourceLogo } from '../../components/Avatar';
import { Button } from '../../components/Button';
import { Badge, EmptyState, Field, Select, TextInput } from '../../components/Field';
import { Modal } from '../../components/Modal';
import { strings } from '../../lib/strings';
import type { Feed } from '../../types';

export function RssTab() {
  const feeds = useFeeds(null);
  const folders = useFolders();
  const importOpml = useImportOpml();
  const clearData = useClearLocalData();
  const deleteFeed = useDeleteFeed();

  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set());
  const [editing, setEditing] = useState<Feed | null>(null);
  const [importResult, setImportResult] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const list = feeds.data?.items ?? [];
  const folderList = folders.data?.items ?? [];
  const folderName = (id: string | null) =>
    folderList.find((folder) => folder.id === id)?.name ?? '未分组';

  const toggle = (id: string) =>
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const deleteSelected = () => {
    if (selected.size === 0) return;
    if (!window.confirm(strings.settings.deleteConfirm(selected.size))) return;
    for (const id of selected) deleteFeed.mutate(id);
    setSelected(new Set());
  };

  return (
    <div className="space-y-7">
      <section>
        <h3 className="mb-3 text-sm font-semibold text-ink">{strings.settings.dataManagement}</h3>
        <div className="divide-y divide-line rounded-xl border border-line">
          <DataRow
            title={strings.settings.exportOpml}
            hint={strings.settings.exportOpmlHint}
            action={
              <Button size="sm" className="w-24" onClick={exportOpml}>
                导出
              </Button>
            }
          />
          <DataRow
            title={strings.settings.importOpml}
            hint={importResult ?? strings.settings.importOpmlHint}
            action={
              <Button
                size="sm"
                className="w-24"
                disabled={importOpml.isPending}
                onClick={() => fileInput.current?.click()}
              >
                导入
              </Button>
            }
          />
          <DataRow
            title={strings.settings.exportRead}
            hint={strings.settings.exportReadHint}
            action={
              <Button size="sm" className="w-24" onClick={exportUserData}>
                导出
              </Button>
            }
          />
          <DataRow
            title={strings.settings.clearData}
            hint={strings.settings.clearDataHint}
            action={
              <Button
                size="sm"
                variant="danger"
                className="w-24"
                disabled={clearData.isPending}
                onClick={() => {
                  if (!window.confirm(strings.settings.clearConfirm)) return;
                  clearData.mutate(undefined, {
                    onSuccess: () => window.location.assign('/login'),
                  });
                }}
              >
                清空
              </Button>
            }
          />
        </div>

        <input
          ref={fileInput}
          type="file"
          accept=".opml,.xml,text/x-opml"
          hidden
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = '';
            if (!file) return;
            setImportResult(null);
            importOpml.mutate(file, {
              onSuccess: (result) => {
                const summary = strings.settings.importDone(result.imported, result.skipped);
                setImportResult(
                  result.errors.length > 0
                    ? `${summary}；有 ${result.errors.length} 个源抓取失败（${result.errors[0]}）`
                    : summary,
                );
              },
              onError: (cause) =>
                setImportResult(cause instanceof Error ? cause.message : strings.error),
            });
          }}
        />
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink">{strings.settings.manage}</h3>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="soft"
              icon={<Plus size={14} />}
              onClick={() => setEditing(blankFeed())}
            >
              {strings.settings.addFeed}
            </Button>
            <Button
              size="sm"
              disabled={selected.size !== 1}
              onClick={() => {
                const target = list.find((feed) => selected.has(feed.id));
                if (target) setEditing(target);
              }}
            >
              {strings.settings.editFeed}
            </Button>
            <Button
              size="sm"
              variant="danger"
              icon={<Trash2 size={14} />}
              disabled={selected.size === 0}
              onClick={deleteSelected}
            >
              {strings.settings.deleteSelected}
            </Button>
          </div>
        </div>

        {list.length === 0 ? (
          <EmptyState>{strings.settings.noFeeds}</EmptyState>
        ) : (
          <div className="overflow-hidden rounded-xl border border-line">
            <table className="w-full text-left">
              <thead className="bg-page text-2xs font-semibold text-ink-3">
                <tr>
                  <th className="w-10 px-3 py-2.5">
                    <input
                      type="checkbox"
                      aria-label={strings.settings.selectAll}
                      checked={selected.size === list.length && list.length > 0}
                      onChange={(event) =>
                        setSelected(
                          event.target.checked ? new Set(list.map((feed) => feed.id)) : new Set(),
                        )
                      }
                    />
                  </th>
                  <th className="px-3 py-2.5">{strings.settings.feedColSource}</th>
                  <th className="px-3 py-2.5">{strings.settings.feedColUrl}</th>
                  <th className="w-28 px-3 py-2.5">{strings.settings.feedColFolder}</th>
                  <th className="w-24 px-3 py-2.5">{strings.settings.feedColStatus}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {list.map((feed) => (
                  <tr key={feed.id} className="text-sm">
                    <td className="px-3 py-2.5">
                      <input
                        type="checkbox"
                        aria-label={feed.title}
                        checked={selected.has(feed.id)}
                        onChange={() => toggle(feed.id)}
                      />
                    </td>
                    <td className="px-3 py-2.5">
                      <span className="flex items-center gap-2.5">
                        <SourceLogo name={feed.title} iconUrl={feed.icon_url} size={20} />
                        <span className="truncate text-ink">{feed.title}</span>
                      </span>
                    </td>
                    <td className="max-w-0 truncate px-3 py-2.5 text-xs text-ink-2">{feed.url}</td>
                    <td className="px-3 py-2.5 text-xs text-ink-2">{folderName(feed.folder_id)}</td>
                    <td className="px-3 py-2.5">
                      <StatusBadge feed={feed} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <FeedDialog
        key={editing ? `${editing.id}:${editing.custom_title ?? ''}:${editing.folder_id ?? ''}` : 'closed'}
        feed={editing}
        folders={folderList}
        onClose={() => setEditing(null)}
      />
    </div>
  );
}

function StatusBadge({ feed }: { feed: Feed }) {
  if (feed.last_status === 'error') {
    return (
      <span title={feed.last_error ?? ''}>
        <Badge tone="danger">{strings.settings.statusError}</Badge>
      </span>
    );
  }
  if (feed.last_status === 'not_modified') {
    return <Badge tone="success">{strings.settings.statusEnabled}</Badge>;
  }
  return <Badge tone="success">{strings.settings.statusEnabled}</Badge>;
}

function DataRow({ title, hint, action }: { title: string; hint: string; action: ReactNode }) {
  return (
    <div className="flex items-center gap-4 px-4 py-3">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-ink">{title}</p>
        <p className="mt-0.5 truncate text-xs text-ink-3">{hint}</p>
      </div>
      {action}
    </div>
  );
}

/** id 为空的 Feed 代表「新增」。 */
function blankFeed(): Feed {
  return {
    id: '',
    url: '',
    site_url: null,
    title: '',
    description: null,
    icon_url: null,
    folder_id: null,
    custom_title: null,
    unread_count: 0,
    last_status: 'ok',
    last_error: null,
    last_fetched_at: null,
  };
}

interface FeedDialogProps {
  feed: Feed | null;
  folders: { id: string; name: string }[];
  onClose: () => void;
}

function FeedDialog({ feed, folders, onClose }: FeedDialogProps) {
  const createFeed = useCreateFeed();
  const updateFeed = useUpdateFeed();

  const isNew = feed !== null && feed.id === '';
  const [url, setUrl] = useState(feed?.url ?? '');
  const [title, setTitle] = useState(feed?.custom_title ?? '');
  const [folderId, setFolderId] = useState(feed?.folder_id ?? '');
  const [error, setError] = useState<string | null>(null);

  const submit = () => {
    setError(null);
    if (!feed) return;
    const onError = (cause: unknown) =>
      setError(cause instanceof Error ? cause.message : strings.error);

    if (isNew) {
      createFeed.mutate(
        { url: url.trim(), folder_id: folderId || null, title: title.trim() || undefined },
        { onSuccess: onClose, onError },
      );
      return;
    }
    updateFeed.mutate(
      {
        id: feed.id,
        title: title.trim(),
        folderId: folderId || null,
        clearFolder: folderId === '',
      },
      { onSuccess: onClose, onError },
    );
  };

  return (
    <Modal
      open={feed !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={isNew ? strings.settings.addFeed : strings.settings.editFeed}
      width={480}
      footer={
        <>
          <Button variant="outline" className="w-[198px]" onClick={onClose}>
            {strings.cancel}
          </Button>
          <Button
            variant="solid"
            className="w-[198px]"
            disabled={isNew ? url.trim() === '' : false}
            onClick={submit}
          >
            {strings.save}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={strings.settings.feedUrl}>
          <TextInput
            value={url}
            disabled={!isNew}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://example.com/feed.xml"
          />
        </Field>

        <Field label={strings.settings.feedTitle}>
          <TextInput
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="留空则使用源自带标题"
          />
        </Field>

        <Field label={strings.settings.feedColFolder}>
          <Select value={folderId} onChange={(event) => setFolderId(event.target.value)}>
            <option value="">未分组</option>
            {folders.map((folder) => (
              <option key={folder.id} value={folder.id}>
                {folder.name}
              </option>
            ))}
          </Select>
        </Field>

        {error ? (
          <p className="rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger-ink">{error}</p>
        ) : null}
      </div>
    </Modal>
  );
}
