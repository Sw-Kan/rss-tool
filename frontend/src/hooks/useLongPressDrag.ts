import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from 'react';

/** 长按多久进入拖拽。比单击慢一点，但不用刻意长按。 */
const HOLD_MS = 250;
/** 长按期间指针移动超过这个距离就当成「不是长按」（滚动、划过）。 */
const MOVE_TOLERANCE = 6;
/** 拖影相对指针的偏移，免得被指针挡住。 */
const GHOST_OFFSET = 12;

interface LongPressDragOptions {
  /** 松手时回调：target 为 null 表示没落在任何落点上（调用方忽略即可）。 */
  onDrop: (id: string, target: string | null) => void;
}

/**
 * 鼠标长按后拖拽，松手时把「谁拖到了哪个落点」交给调用方。
 *
 * 用 pointer 事件自己实现，不引拖拽库、也不用 HTML5 DnD：后者要求 `draggable` 在按下之前
 * 就为真，而这里得先等长按判定。落点靠 `handleTargetEnter/Leave`（`onPointerEnter`）标记，
 * 所以不需要命中检测——jsdom 里没有布局，`elementFromPoint` 测不了。
 *
 * 触摸端不参与（`pointerType === 'touch'` 直接返回）：抢侧边栏的滚动手势得不偿失，
 * 改目录在「设置 → 订阅源 → 编辑」里仍然可以。
 */
export function useLongPressDrag({ onDrop }: LongPressDragOptions) {
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);
  const [point, setPoint] = useState<{ x: number; y: number } | null>(null);

  const pending = useRef<{ id: string; x: number; y: number } | null>(null);
  const active = useRef<string | null>(null);
  const over = useRef<string | null>(null);
  const timer = useRef<number | null>(null);
  /** 长按判定成立后，紧接着的那次 click 要吃掉（否则松手会顺带切到那个源）。 */
  const swallowClick = useRef(false);

  const clearTimer = () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = null;
  };

  const endDrag = useCallback(() => {
    clearTimer();
    pending.current = null;
    active.current = null;
    over.current = null;
    setDraggingId(null);
    setOverId(null);
    setPoint(null);
  }, []);

  const handlePointerDown = useCallback((id: string, event: ReactPointerEvent) => {
    // 只认左键 + 鼠标：触摸留给滚动，右键留给菜单
    if (event.button !== 0 || event.pointerType !== 'mouse') return;
    swallowClick.current = false;
    pending.current = { id, x: event.clientX, y: event.clientY };
    clearTimer();
    timer.current = window.setTimeout(() => {
      const start = pending.current;
      if (!start) return;
      timer.current = null;
      active.current = start.id;
      swallowClick.current = true;
      setDraggingId(start.id);
      setPoint({ x: start.x, y: start.y });
    }, HOLD_MS);
  }, []);

  const handleTargetEnter = useCallback((targetId: string) => {
    if (active.current === null) return;
    over.current = targetId;
    setOverId(targetId);
  }, []);

  const handleTargetLeave = useCallback((targetId: string) => {
    if (over.current !== targetId) return;
    over.current = null;
    setOverId(null);
  }, []);

  /** 拖拽刚结束的那次 click 返回 true（只吃一次，下一次点击照常生效）。 */
  const takeSwallowedClick = useCallback(() => {
    if (!swallowClick.current) return false;
    swallowClick.current = false;
    return true;
  }, []);

  useEffect(() => {
    const onMove = (event: PointerEvent) => {
      if (active.current === null) {
        const start = pending.current;
        if (!start) return;
        if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > MOVE_TOLERANCE) {
          clearTimer();
          pending.current = null;
        }
        return;
      }
      setPoint({ x: event.clientX, y: event.clientY });
    };

    const onUp = () => {
      const id = active.current;
      if (id === null) {
        clearTimer();
        pending.current = null;
        return;
      }
      onDrop(id, over.current);
      endDrag();
    };

    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') endDrag();
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      window.removeEventListener('keydown', onKey);
    };
  }, [endDrag, onDrop]);

  return {
    draggingId,
    overId,
    /** 拖影位置（视口坐标）；没在拖时为 null。 */
    point: point ? { x: point.x + GHOST_OFFSET, y: point.y + GHOST_OFFSET } : null,
    handlePointerDown,
    handleTargetEnter,
    handleTargetLeave,
    takeSwallowedClick,
  };
}
