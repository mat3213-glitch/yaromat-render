import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {OverlayProps} from '../overlay_contract';

/**
 * ShapeWipe — переход-вытеснение. Диагональная полоса в акцентном цвете
 * проходит через кадр: к середине длительности полностью перекрывает,
 * затем уходит, открывая. Чистая геометрия, без неона, альфа-хук.
 */
export const ShapeWipe: React.FC<OverlayProps> = ({palette, durationSec}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const total = Math.round((durationSec || 2) * fps);
  const mid = total / 2;
  const accent = palette[0] ?? '#e8e2d6';

  // ширина полосы — больше кадра, чтобы гарантированно перекрыть
  const barWidth = width * 1.6;
  // диагональный запас по высоте для наклона
  const diag = height * 0.6;

  // общий прогресс: 0→1 входит, 1→2 выходит
  const progress = interpolate(frame, [0, mid, total], [0, 1, 2],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  // фаза входа: полоса едет слева в центр
  const enterX = interpolate(progress, [0, 1], [-barWidth, width * 0.5],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  // фаза выхода: полоса едет из центра вправо за кадр
  const exitX = interpolate(progress, [1, 2], [width * 0.5, width + barWidth],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const x = progress <= 1 ? enterX : exitX;

  // масштаб полосы: расширяется к пику, сжимается на выходе
  const scaleX = interpolate(progress, [0, 0.5, 1, 1.5, 2],
    [0.3, 0.8, 1.2, 0.8, 0.3],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute',
        top: -diag,
        left: 0,
        width: barWidth,
        height: height + diag * 2,
        background: accent,
        transform: `translateX(${x}px) skewX(-18deg) scaleX(${scaleX})`,
        transformOrigin: 'center center',
      }} />
    </AbsoluteFill>
  );
};
