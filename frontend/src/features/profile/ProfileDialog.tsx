import { Lock, Upload } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import {
  exportUserData,
  useDeleteAvatar,
  useUpdateProfile,
  useUploadAvatar,
} from '../../api/hooks';
import { Avatar } from '../../components/Avatar';
import { Button } from '../../components/Button';
import { Field, TextInput } from '../../components/Field';
import { Modal } from '../../components/Modal';
import { AVATAR_COLORS } from '../../lib/format';
import { useT } from '../../lib/i18n';
import type { User } from '../../types';

const MAX_BYTES = 3 * 1024 * 1024;
const HEX_COLORS = ['#4F46E5', '#0EA5E9', '#10B981', '#F59E0B', '#EC4899'];

interface ProfileDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  user: User | null;
}

export function ProfileDialog({ open, onOpenChange, user }: ProfileDialogProps) {
  const t = useT();
  const [username, setUsername] = useState(user?.username ?? '');
  const [color, setColor] = useState(user?.avatar_color ?? HEX_COLORS[0]);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const updateProfile = useUpdateProfile();
  const uploadAvatar = useUploadAvatar();
  const deleteAvatar = useDeleteAvatar();

  useEffect(() => {
    if (!open) return;
    setUsername(user?.username ?? '');
    setColor(user?.avatar_color ?? HEX_COLORS[0]);
    setError(null);
  }, [open, user?.username, user?.avatar_color]);

  const onPickFile = (file: File | undefined) => {
    setError(null);
    if (!file) return;
    if (file.size > MAX_BYTES) {
      setError(t.profile.tooLarge);
      return;
    }
    if (!/image\/(png|jpe?g)/i.test(file.type)) {
      setError(t.profile.badImage);
      return;
    }
    uploadAvatar.mutate(file, {
      onError: (cause) => setError(cause instanceof Error ? cause.message : t.error),
    });
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={t.profile.title}
      width={480}
      footer={
        <>
          <Button variant="outline" className="w-[198px]" onClick={() => onOpenChange(false)}>
            {t.cancel}
          </Button>
          <Button
            variant="solid"
            className="w-[198px]"
            disabled={updateProfile.isPending || username.trim() === ''}
            onClick={() =>
              updateProfile.mutate(
                { username: username.trim(), avatar_color: color },
                { onSuccess: () => onOpenChange(false) },
              )
            }
          >
            {t.save}
          </Button>
        </>
      }
    >
      <div className="flex flex-col items-center gap-4">
        <Avatar
          name={username || user?.username || '?'}
          color={color}
          imageUrl={user?.avatar_url}
          size={88}
        />

        <div className="flex items-center gap-3">
          {HEX_COLORS.map((hex, index) => (
            <button
              key={hex}
              type="button"
              aria-label={t.profile.colorHint}
              onClick={() => {
                setColor(hex);
                updateProfile.mutate({ avatar_color: hex, avatar_type: 'letter' });
              }}
              style={{ background: AVATAR_COLORS[index] }}
              className={`h-7 w-7 rounded-full transition-transform ${
                color === hex ? 'ring-2 ring-ink ring-offset-2 ring-offset-surface' : ''
              }`}
            />
          ))}
        </div>

        <div className="flex flex-col items-center gap-1.5">
          <Button
            variant="soft"
            size="sm"
            icon={<Upload size={14} />}
            onClick={() => fileInput.current?.click()}
          >
            {t.profile.upload}
          </Button>
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg"
            hidden
            onChange={(event) => {
              onPickFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          {user?.avatar_url ? (
            <button
              type="button"
              className="text-xs text-ink-2 underline underline-offset-2"
              onClick={() => deleteAvatar.mutate()}
            >
              {t.profile.removeImage}
            </button>
          ) : null}
          <p className="text-2xs text-ink-3">{t.profile.uploadHint}</p>
        </div>

        {error ? (
          <p className="w-full rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger-ink">
            {error}
          </p>
        ) : null}
      </div>

      <div className="mt-5 space-y-4">
        <Field label={t.profile.username} hint={t.profile.colorHint}>
          <TextInput
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            maxLength={60}
          />
        </Field>

        <Field label={t.profile.email} hint={t.profile.emailLocked}>
          <div className="relative">
            <TextInput value={user?.email ?? ''} readOnly disabled className="pr-9" />
            <Lock
              size={14}
              className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 text-ink-3"
            />
          </div>
        </Field>

        <button
          type="button"
          className="text-xs text-brand-ink underline underline-offset-2"
          onClick={exportUserData}
        >
          {t.profile.exportData}
        </button>
      </div>
    </Modal>
  );
}
