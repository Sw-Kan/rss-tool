import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';

import { useT } from '../lib/i18n';

interface ModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
  /** 设计稿：设置 960×760，个人资料 480×560 */
  width?: number;
  /** 固定高度。给定时弹窗不随内容变化，切 tab 外壳不动、只换内容区（设计稿如此） */
  height?: number;
  /** 设置弹窗用左右两栏布局 */
  sidebar?: ReactNode;
  /**
   * 替换左右两栏的包裹层。用于让同一个 Tabs.Root 同时包住侧栏（Tabs.List）
   * 与主区（Tabs.Content）——否则 aria-controls 会指向不存在的 id。
   */
  container?: (slots: { sidebar: ReactNode; panel: ReactNode }) => ReactNode;
}

export function Modal({
  open,
  onOpenChange,
  title,
  subtitle,
  children,
  footer,
  width = 480,
  height,
  sidebar,
  container,
}: ModalProps) {
  const t = useT();

  const sidebarSlot = sidebar ? (
    <div className="flex w-60 shrink-0 flex-col bg-page">{sidebar}</div>
  ) : null;

  const panelSlot = (
    <div className="flex min-w-0 flex-1 flex-col">
      <header className="flex items-start justify-between gap-4 border-b border-line px-8 pt-6 pb-4">
        <div className="min-w-0">
          <Dialog.Title className="text-xl font-bold text-ink">{title}</Dialog.Title>
          {subtitle ? (
            <Dialog.Description className="mt-0.5 text-xs text-ink-3">
              {subtitle}
            </Dialog.Description>
          ) : null}
        </div>
        <Dialog.Close
          aria-label={t.close}
          className="-mt-1 -mr-1 inline-flex h-7 w-7 items-center justify-center rounded-md text-ink-3 transition-colors hover:bg-subtle hover:text-ink"
        >
          <X size={16} />
        </Dialog.Close>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-8 py-5">{children}</div>

      {footer ? (
        <footer className="flex justify-end gap-3 border-t border-line px-8 py-4">{footer}</footer>
      ) : null}
    </div>
  );

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40" style={{ background: 'var(--overlay)' }} />
        <Dialog.Content
          style={{
            width,
            height,
            maxWidth: 'calc(100vw - 32px)',
            maxHeight: 'calc(100vh - 64px)',
          }}
          className="fixed top-1/2 left-1/2 z-50 flex -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl bg-surface shadow-[var(--shadow-card)]"
        >
          {container ? (
            container({ sidebar: sidebarSlot, panel: panelSlot })
          ) : (
            <div className="flex min-h-0 flex-1">
              {sidebarSlot}
              {panelSlot}
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
