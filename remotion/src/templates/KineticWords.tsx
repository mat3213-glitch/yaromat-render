import React from 'react';
import {
  AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring,
} from 'remotion';
import {TemplateProps, rng} from '../contract';

/**
 * KineticWords — кинетическая типографика.
 * Каждое слово trackTitle влетает со стаггером (spring, снизу вверх, blur→sharp, fade-in).
 * Бренд появляется после заголовка. Вайб-арт — приглушённый фон с мягким дрейфом.
 */
export const KineticWords: React.FC<TemplateProps> = ({
  artUrl, trackTitle, brand, palette, seed,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const rand = rng(seed);

  const bg = palette[0] ?? '#0b0d10';
  const mid = palette[1] ?? '#1a2230';
  const accent = palette[2] ?? '#cfd6dd';

  const bgDir = rand() < 0.5 ? 1 : -1;
  const bgScale = interpolate(frame, [0, durationInFrames], [1.04, 1.12]);
  const bgPanX = interpolate(frame, [0, durationInFrames], [0, bgDir * 18]);
  const bgPanY = interpolate(frame, [0, durationInFrames], [0, bgDir * -8]);

  const words = trackTitle.split(/\s+/).filter(Boolean);
  const staggerBase = Math.round(fps * 0.18);
  const staggerJitter = Math.round(rand() * Math.round(fps * 0.08));
  const wordsStartFrame = Math.round(fps * 0.5);

  const wordEntries = words.map((w, i) => {
    const delay = wordsStartFrame + i * (staggerBase + (i % 2 === 0 ? staggerJitter : -staggerJitter));
    const s = spring({frame: frame - delay, fps, config: {damping: 18, stiffness: 120, mass: 0.8}});
    const y = interpolate(s, [0, 1], [44, 0]);
    const opacity = interpolate(s, [0, 1], [0, 1]);
    const blur = interpolate(s, [0, 1], [6, 0]);
    return {word: w, y, opacity, blur, index: i};
  });

  const lastWordDelay = wordsStartFrame + (words.length - 1) * (staggerBase + staggerJitter);
  const brandStart = lastWordDelay + Math.round(fps * 0.4);
  const brandOpacity = interpolate(frame, [brandStart, brandStart + Math.round(fps * 0.8)], [0, 0.7], {
    extrapolateLeft: 'clamp', extrapolateRight: 'clamp',
  });

  const swayPhase = frame / fps;
  const swayX = Math.sin(swayPhase * 0.4) * 2;
  const swayY = Math.cos(swayPhase * 0.3) * 1.5;

  return (
    <AbsoluteFill style={{backgroundColor: bg}}>
      <AbsoluteFill style={{transform: `scale(${bgScale}) translate(${bgPanX}px, ${bgPanY}px)`}}>
        <Img src={staticFile(artUrl)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </AbsoluteFill>

      <AbsoluteFill style={{background: `radial-gradient(ellipse at center, transparent 35%, ${bg}dd 100%)`}} />
      <AbsoluteFill style={{background: `linear-gradient(to top, ${bg}ee 0%, transparent 40%)`}} />

      <AbsoluteFill style={{
        justifyContent: 'center', alignItems: 'center',
        transform: `translate(${swayX}px, ${swayY}px)`,
      }}>
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          gap: height * 0.006,
        }}>
          {wordEntries.map(({word, y: wy, opacity: wo, blur: wb, index: idx}) => (
            <div key={idx} style={{
              color: accent,
              fontFamily: 'Georgia, serif',
              fontSize: words.length > 4 ? width * 0.06 : width * 0.078,
              fontWeight: 700,
              letterSpacing: 2,
              textShadow: `0 2px 20px ${mid}99`,
              opacity: wo,
              filter: `blur(${wb}px)`,
              transform: `translateY(${wy}px)`,
              lineHeight: 1.15,
              textAlign: 'center',
            }}>
              {word}
            </div>
          ))}

          <div style={{
            color: accent,
            opacity: brandOpacity,
            fontFamily: 'Georgia, serif',
            fontSize: width * 0.028,
            fontWeight: 400,
            marginTop: height * 0.02,
            letterSpacing: 3,
          }}>
            {brand}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
