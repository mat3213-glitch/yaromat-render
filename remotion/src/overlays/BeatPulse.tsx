import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate} from 'remotion';
import {OverlayProps} from '../overlay_contract';

/**
 * BeatPulse — ритм-пульс. Сдержанный элемент (тонкое кольцо) пульсирует
 * масштабом+непрозрачностью несколько раз за durationSec. Спокойное
 * «дыхание» поверх кадра. Фаза и число пульсов от seed.
 */
export const BeatPulse: React.FC<OverlayProps> = ({seed, palette, durationSec}) => {
  const frame = useCurrentFrame();
  const {fps, width, height} = useVideoConfig();
  const accent = palette[0] ?? '#e8e2d6';
  const total = Math.round((durationSec || 2) * fps);

  // количество пульсов определяется seed (3–5)
  const numPulses = 3 + (seed % 3);
  // лёгкий фазовый сдвиг для вариативности
  const phaseOffset = (seed % 10) * 0.1;

  // размер кольца — 35% от меньшей стороны
  const size = Math.min(width, height) * 0.35;
  const stroke = Math.max(2, Math.round(width * 0.005));

  let scale = 1;
  let opacity = 0;

  // суммируем вклад каждого пульса (волновая функция)
  for (let p = 0; p < numPulses; p++) {
    const t = frame / total;
    // центр текущего пульса на таймлайне
    const pulseCenter = (p + 0.5) / numPulses;
    const dist = Math.abs(t - pulseCenter);
    // ширина «окна» пульса — равномерно распределены
    const halfW = 0.5 / numPulses;
    const inPulse = dist < halfW;
    if (inPulse) {
      // локальная нормализация 0→1→0 внутри окна
      const local = 1 - dist / halfW;
      const wave = Math.sin(local * Math.PI);
      scale = Math.max(scale, 1 + wave * 0.12 + phaseOffset * 0.02);
      opacity = Math.max(opacity, wave * 0.6);
    }
  }

  return (
    <AbsoluteFill>
      <div style={{
        position: 'absolute',
        left: '50%',
        top: '50%',
        width: size,
        height: size,
        marginLeft: -size / 2,
        marginTop: -size / 2,
        borderRadius: '50%',
        border: `${stroke}px solid ${accent}`,
        transform: `scale(${scale})`,
        opacity,
      }} />
    </AbsoluteFill>
  );
};
