import { useEffect, useState } from 'react';

import { initialOf, swatchFor } from '../lib/format';

interface AvatarProps {
  name: string;
  /** 字母头像背景色；不传则按名字稳定取色 */
  color?: string;
  imageUrl?: string | null;
  size?: number;
  className?: string;
}

/** 用户头像：优先图片，否则「首字母 + 纯色背景」。 */
export function Avatar({ name, color, imageUrl, size = 40, className = '' }: AvatarProps) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [imageUrl]);

  const swatch = swatchFor(name);
  const style = {
    width: size,
    height: size,
    background: color ?? swatch.bg,
    color: color ? 'var(--on-strong)' : swatch.ink,
    fontSize: Math.max(10, Math.round(size * 0.4)),
  } as const;

  if (imageUrl && !broken) {
    return (
      <img
        src={imageUrl}
        alt={name}
        width={size}
        height={size}
        className={`shrink-0 rounded-full object-cover ${className}`}
        onError={() => setBroken(true)}
      />
    );
  }

  return (
    <span
      aria-hidden
      style={style}
      className={`flex shrink-0 items-center justify-center rounded-full font-semibold ${className}`}
    >
      {initialOf(name)}
    </span>
  );
}

interface SourceLogoProps {
  name: string;
  iconUrl?: string | null;
  size?: number;
}

/** 订阅源 logo：20px 圆形，加载失败回退到首字母色块。 */
export function SourceLogo({ name, iconUrl, size = 20 }: SourceLogoProps) {
  const [broken, setBroken] = useState(false);
  useEffect(() => setBroken(false), [iconUrl]);

  if (iconUrl && !broken) {
    return (
      <img
        src={iconUrl}
        alt=""
        width={size}
        height={size}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setBroken(true)}
        className="shrink-0 rounded-full object-cover"
      />
    );
  }

  const swatch = swatchFor(name);
  return (
    <span
      aria-hidden
      style={{
        width: size,
        height: size,
        background: swatch.bg,
        color: swatch.ink,
        fontSize: Math.max(9, Math.round(size * 0.5)),
      }}
      className="flex shrink-0 items-center justify-center rounded-full font-semibold"
    >
      {initialOf(name)}
    </span>
  );
}
