import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { LogOut, Settings, User as UserIcon } from 'lucide-react';
import { useState, type ReactNode } from 'react';

import { useLogout } from '../../api/hooks';
import { useT } from '../../lib/i18n';
import type { User } from '../../types';
import { ProfileDialog } from '../profile/ProfileDialog';

interface ProfileMenuProps {
  user: User | null;
  onOpenSettings: () => void;
  children: ReactNode;
}

/** 向上弹出的资料菜单：个人资料 / 设置 / 退出登录。 */
export function ProfileMenu({ user, onOpenSettings, children }: ProfileMenuProps) {
  const t = useT();
  const [profileOpen, setProfileOpen] = useState(false);
  const logout = useLogout();

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>{children}</DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            side="top"
            align="start"
            sideOffset={8}
            className="z-50 w-56 rounded-xl border border-line bg-surface p-1.5 shadow-[var(--shadow-pop)]"
          >
            <DropdownMenu.Item
              onSelect={() => setProfileOpen(true)}
              className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-subtle"
            >
              <UserIcon size={15} className="text-ink-3" />
              <span className="text-sm text-ink">{t.profile.menuProfile}</span>
            </DropdownMenu.Item>

            <DropdownMenu.Item
              onSelect={onOpenSettings}
              className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-subtle"
            >
              <Settings size={15} className="text-ink-3" />
              <span className="text-sm text-ink">{t.profile.menuSettings}</span>
            </DropdownMenu.Item>

            <DropdownMenu.Separator className="my-1 h-px bg-line" />

            <DropdownMenu.Item
              onSelect={() => logout.mutate()}
              className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 outline-none data-[highlighted]:bg-subtle"
            >
              <LogOut size={15} className="text-danger" />
              <span className="text-sm text-danger-ink">{t.profile.menuLogout}</span>
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <ProfileDialog open={profileOpen} onOpenChange={setProfileOpen} user={user} />
    </>
  );
}
