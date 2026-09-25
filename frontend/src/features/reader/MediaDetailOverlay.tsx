import * as Dialog from '@radix-ui/react-dialog';

import { useT } from '../../lib/i18n';
import type { ReaderSearch } from '../../types';
import { ArticlePane } from './ArticlePane';

interface MediaDetailOverlayProps {
  itemId: string | null;
  search: ReaderSearch;
  onNavigate: (itemId: string) => void;
  onClose: () => void;
}

/**
 * pictures / videos 两个模式的详情弹层。
 *
 * 这两个模式的形态是整块内容区（瀑布流 / 网格），把正文挤成右栏会把 6 列压到 2–3 列，
 * 所以详情改用灯箱：墙和网格保持全宽，点条目在弹层里看。内容直接复用 ArticlePane。
 * 选中态只由 URL 的 `item=` 决定，因此可以分享、刷新、前进后退。
 */
export function MediaDetailOverlay({
  itemId,
  search,
  onNavigate,
  onClose,
}: MediaDetailOverlayProps) {
  const t = useT();

  return (
    <Dialog.Root
      open={Boolean(itemId)}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40" style={{ background: 'var(--overlay)' }} />
        <Dialog.Content
          // 标题用屏读专用，视觉上的标题在正文里；不写的话 Radix 会警告缺 Title
          aria-describedby={undefined}
          className="fixed top-1/2 left-1/2 z-50 flex h-[760px] max-h-[calc(100vh-64px)] w-[960px] max-w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl bg-surface shadow-[var(--shadow-card)]"
        >
          <Dialog.Title className="sr-only">{t.article.detail}</Dialog.Title>
          <ArticlePane
            itemId={itemId}
            search={search}
            onNavigate={onNavigate}
            variant="overlay"
            onClose={onClose}
          />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
