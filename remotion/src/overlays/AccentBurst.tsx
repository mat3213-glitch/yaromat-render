import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate, spring} from 'remotion';
import {OverlayProps} from '../overlay_contract';

/**
 * AccentBurst — «взрыв» энергии на дропе. Короткие радиальные штрихи
 * выстреливают из центра, быстро появляются и гаснут. Резкий, ударный,
 * ~0.5с активной фазы. Без свечения-неона, приглушённый акцент.
 */
export const AccentBurst: React.FC<OverlayProps> = ({seed, palette, durationSec}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const accent = palette[0] ?? '#e8e2d6';
  const cx = width / 2;
  const cy = height / 2;

  // длительность активной фазы — 0.5с
  const burstFrames = Math.round(fps * 0.5);
  // общий fade-out к концу
  const fadeOut = interpolate(frame, [Math.round(fps * 0.3), burstFrames],
    [1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

  const numRays = 12;
  const rays: React.ReactNode[] = [];

  for (let i = 0; i < numRays; i++) {
    // угол луча + лёгкий сдвиг от seed для уникальности
    const angle = (i / numRays) * Math.PI * 2 + (seed % 100) * 0.01;
    // каскадная задержка: каждый третий луч стартует позже
    const delay = (i % 3) * 2;
    const raySpring = spring({
      frame: frame - delay,
      fps,
      config: {damping: 12, stiffness: 200, mass: 0.5},
    });
    // длина луча зависит от индекса — разноразмерность
    const len = interpolate(raySpring, [0, 1], [0, height * 0.18 + (i % 3) * 12]);
    // прозрачность: появление → пик → гашение
    const rayOpacity = interpolate(frame, [delay, delay + 4, burstFrames],
      [0, 0.7, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const thick = Math.max(2, Math.round(width * 0.004));

    rays.push(
      <div key={i} style={{
        position: 'absolute',
        left: cx,
        top: cy,
        width: len,
        height: thick,
        background: accent,
        borderRadius: thick,
        transform: `rotate(${angle}rad) translateX(${10}px)`,
        transformOrigin: '0 center',
        opacity: rayOpacity,
      }} />,
    );
  }

  return (
    <AbsoluteFill style={{opacity: fadeOut}}>
      {rays}
    </AbsoluteFill>
  );
};
