import { useEffect, useState } from 'react';

import { useCreateFeed, useFolders } from '../../api/hooks';
import { Button } from '../../components/Button';
import { Field, Segmented, Select, TextInput } from '../../components/Field';
import { Modal } from '../../components/Modal';
import { useT } from '../../lib/i18n';
import type { KindChoice } from '../../types';

interface AddSourceDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 从某个目录进来时预选它（未分组用 null） */
  defaultFolderId?: string | null;
}

export function AddSourceDialog({ open, onOpenChange, defaultFolderId = null }: AddSourceDialogProps) {
  const t = useT();
  const folders = useFolders(open);
  const createFeed = useCreateFeed();

  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [kind, setKind] = useState<KindChoice>('auto');
  const [folderId, setFolderId] = useState<string>(defaultFolderId ?? '');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setUrl('');
    setTitle('');
    setKind('auto');
    setFolderId(defaultFolderId ?? '');
    setError(null);
  }, [open, defaultFolderId]);

  const submit = () => {
    if (!url.trim()) return;
    setError(null);
    createFeed.mutate(
      {
        url: url.trim(),
        title: title.trim() || undefined,
        kind,
        folder_id: folderId || null,
      },
      {
        onSuccess: () => onOpenChange(false),
        onError: (cause) => setError(cause instanceof Error ? cause.message : t.error),
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={t.addSource.title}
      subtitle={t.addSource.subtitle}
      width={480}
      footer={
        <>
          <Button variant="outline" className="w-[180px]" onClick={() => onOpenChange(false)}>
            {t.cancel}
          </Button>
          <Button
            variant="solid"
            className="w-[180px]"
            disabled={createFeed.isPending || url.trim() === ''}
            onClick={submit}
          >
            {t.addSource.submit}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={t.addSource.url} hint={t.addSource.urlHint}>
          <TextInput
            autoFocus
            value={url}
            placeholder={t.addSource.urlPlaceholder}
            onChange={(event) => setUrl(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') submit();
            }}
          />
        </Field>

        <Field label={t.addSource.name}>
          <TextInput
            value={title}
            placeholder={t.addSource.namePlaceholder}
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>

        <div>
          <span className="mb-1 block text-xs font-medium text-ink-2">{t.addSource.kind}</span>
          <Segmented
            label={t.addSource.kind}
            value={kind}
            onChange={setKind}
            options={[
              { value: 'auto', label: t.addSource.kindAuto },
              { value: 'article', label: t.addSource.kindArticle },
              { value: 'picture', label: t.addSource.kindPicture },
              { value: 'video', label: t.addSource.kindVideo },
            ]}
          />
          <span className="mt-1 block text-xs text-ink-3">{t.addSource.kindHint}</span>
        </div>

        <Field label={t.addSource.folder} hint={t.addSource.folderHint}>
          <Select value={folderId} onChange={(event) => setFolderId(event.target.value)}>
            <option value="">{t.settings.ungroupedOption}</option>
            {(folders.data?.items ?? []).map((folder) => (
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
