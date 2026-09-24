import { useEffect, useState } from 'react';

import { swatchFor } from '../lib/format';

interface RemoteImageProps {
  src: string;
  alt: string;
  /** 已知比例时（来自 feed 的 width/height）用于占位，避免瀑布流抖动 */
  width?: number | null;
  height?: number | null;
  className?: string;
  /** 加载失败时用首字母色块兜底 */
  fallbackSeed?: string;
}

/**
 * 外链图片统一出口：
 *   - referrerpolicy="no-referrer" 绕开防盗链导致的 403
 *   - loading="lazy"
 *   - onError 兜底占位，避免出现破图
 */
export function RemoteImage({
  src,
  alt,
  width,
  height,
  className = '',
  fallbackSeed,
}: RemoteImageProps) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [src]);

  const ratio = width && height && width > 0 && height > 0 ? width / height : 4 / 3;
  const swatch = swatchFor(fallbackSeed ?? src);

  if (failed) {
    return (
      <div
        role="img"
        aria-label={alt}
        style={{ aspectRatio: `${ratio}`, background: swatch.bg, color: swatch.ink }}
        className={`flex items-center justify-center text-xs ${className}`}
      >
        图片加载失败
      </div>
    );
  }

  return (
    <img
      src={src}
      alt={alt}
      loading="lazy"
      decoding="async"
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
      style={{ background: 'var(--bg-subtle)' }}
      className={`block w-full object-cover ${className}`}
    />
  );
}
