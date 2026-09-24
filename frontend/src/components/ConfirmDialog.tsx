import { AlertTriangle, Trash2 } from 'lucide-react';

import { Modal } from './Modal';
import { Button } from './Button';
import { useT } from '../lib/i18n';

interface ConfirmDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  body: string;
  confirmLabel?: string;
  danger?: boolean;
  pending?: boolean;
  onConfirm: () => void;
}

/**
 * 危险操作的确认弹窗。
 *
 * 之前用下拉菜单里的删除项，菜单定位出错时会飘到窗口左上角；改成弹窗后位置固定，
 * 也顺手把「不可撤销」的提示放在同一屏里。
 */
export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  body,
  confirmLabel,
  danger = true,
  pending = false,
  onConfirm,
}: ConfirmDialogProps) {
  const t = useT();
  const Icon = danger ? Trash2 : AlertTriangle;

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title=""
      width={420}
      container={({ panel }) => panel}
      footer={
        <>
          <Button variant="outline" className="w-[180px]" onClick={() => onOpenChange(false)}>
            {t.cancel}
          </Button>
          <Button
            variant={danger ? 'danger' : 'solid'}
            className="w-[180px]"
            disabled={pending}
            onClick={onConfirm}
          >
            {confirmLabel ?? t.remove}
          </Button>
        </>
      }
    >
      <div className="flex gap-4 pt-1">
        <span
          className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-[10px] ${
            danger ? 'bg-danger-soft text-danger-ink' : 'bg-soft text-on-soft'
          }`}
        >
          <Icon size={16} />
        </span>
        <div className="min-w-0">
          <p className="text-base font-bold text-ink">{title}</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-2">{body}</p>
        </div>
      </div>
    </Modal>
  );
}
