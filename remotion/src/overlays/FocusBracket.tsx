import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {OverlayProps} from '../overlay_contract';

/**
 * FocusBracket — графический хук-акцент (АЛЬФА, без непрозрачного фона).
 * Угловые скобки «фокуса/видоискателя» снапаются внутрь + быстрый световой свип +
 * лёгкая пульсация на холде → акцентирует «смотри сюда», добавляет динамику на дропе.
 * Без неона, без текста. Композитится поверх клипа в ключевой момент.
 */
export const FocusBracket: React.FC<OverlayProps> = ({palette, durationSec}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const total = Math.round((durationSec || 2) * fps);
  const accent = palette[0] ?? '#e8e2d6';

  // снап скобок внутрь (spring), холд, затем общий fade-out
  const snap = spring({frame, fps, config: {damping: 14, stiffness: 140, mass: 0.7}});
  const offset = interpolate(snap, [0, 1], [70, 0]); // скобки въезжают из-за края
  const appear = interpolate(snap, [0, 1], [0, 1]);
  const fadeOut = interpolate(frame, [total - Math.round(fps * 0.4), total], [1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const pulse = 1 + Math.sin(frame / fps * 6) * 0.012; // едва заметное дыхание

  // световой свип — один проход поперёк в начале
  const sweepX = interpolate(frame, [Math.round(fps * 0.15), Math.round(fps * 0.6)],
    [-width * 0.3, width * 1.3], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  const sweepOp = interpolate(frame, [Math.round(fps * 0.15), Math.round(fps * 0.35), Math.round(fps * 0.6)],
    [0, 0.5, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const L = Math.round(Math.min(width, height) * 0.10); // длина плеча скобки
  const T = Math.max(3, Math.round(width * 0.006));      // толщина
  const m = Math.round(Math.min(width, height) * 0.14);  // отступ рамки от края
  const opacity = appear * fadeOut;

  const corner = (pos: React.CSSProperties, h: React.CSSProperties, v: React.CSSProperties): React.CSSProperties[] => [
    {position: 'absolute', background: accent, width: L, height: T, ...pos, ...h},
    {position: 'absolute', background: accent, width: T, height: L, ...pos, ...v},
  ];

  const corners: React.CSSProperties[] = [
    ...corner({top: m, left: m}, {}, {}),
    ...corner({top: m, right: m}, {}, {}),
    ...corner({bottom: m, left: m}, {}, {}),
    ...corner({bottom: m, right: m}, {}, {}),
  ];

  return (
    <AbsoluteFill style={{opacity}}>
      <AbsoluteFill style={{transform: `scale(${pulse})`, margin: offset}}>
        {corners.map((s, i) => (
          <div key={i} style={{...s, boxShadow: `0 0 14px ${accent}55`}} />
        ))}
      </AbsoluteFill>
      {/* световой свип */}
      <div style={{
        position: 'absolute', top: 0, bottom: 0, left: 0, width: width * 0.18,
        transform: `translateX(${sweepX}px) skewX(-12deg)`, opacity: sweepOp,
        background: `linear-gradient(90deg, transparent, ${accent}, transparent)`,
        filter: 'blur(6px)',
      }} />
    </AbsoluteFill>
  );
};
