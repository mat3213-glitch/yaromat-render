import React from 'react';
import {
  AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig, interpolate, spring,
} from 'remotion';
import {TemplateProps, rng} from '../contract';
import {TITLE_FONT} from '../fonts';

/**
 * KineticCard — РЕФЕРЕНСНЫЙ шаблон (образец контракта для mimo).
 * Техника: вайб-арт с мягким Ken-Burns + пружинный вход кинетической типографики
 * (название трека + бренд). Приглушённая палитра, виньетка, БЕЗ неона.
 * Это самый простой пример — mimo строит богаче (параллакс по depth, частицы, кинетика слов).
 */
export const KineticCard: React.FC<TemplateProps> = ({
  artUrl, trackTitle, brand, palette, seed,
}) => {
  const frame = useCurrentFrame();
  const {fps, durationInFrames, width, height} = useVideoConfig();
  const rand = rng(seed);
  const dir = rand() < 0.5 ? 1 : -1;

  const scale = interpolate(frame, [0, durationInFrames], [1.06, 1.14]);
  const panX = interpolate(frame, [0, durationInFrames], [0, dir * 28]);

  const titleIn = spring({frame: frame - Math.round(fps * 0.4), fps, config: {damping: 200}});
  const titleY = interpolate(titleIn, [0, 1], [40, 0]);

  const bg = palette[0] ?? '#0b0d10';
  const accent = palette[2] ?? '#cfd6dd';

  return (
    <AbsoluteFill style={{backgroundColor: bg}}>
      <AbsoluteFill style={{transform: `scale(${scale}) translateX(${panX}px)`}}>
        <Img src={staticFile(artUrl)} style={{width: '100%', height: '100%', objectFit: 'cover'}} />
      </AbsoluteFill>
      <AbsoluteFill
        style={{background: `radial-gradient(ellipse at center, transparent 45%, ${bg}cc 100%)`}}
      />
      <AbsoluteFill
        style={{justifyContent: 'flex-end', alignItems: 'center', paddingBottom: height * 0.12}}
      >
        <div style={{opacity: titleIn, transform: `translateY(${titleY}px)`, textAlign: 'center'}}>
          <div style={{
            color: accent, fontFamily: TITLE_FONT, fontSize: width * 0.072,
            fontWeight: 600, letterSpacing: 1, textShadow: '0 2px 18px rgba(0,0,0,0.55)',
          }}>
            {trackTitle}
          </div>
          <div style={{
            color: accent, opacity: 0.7, fontFamily: TITLE_FONT, fontSize: width * 0.034,
            marginTop: height * 0.012, letterSpacing: 3,
          }}>
            {brand}
          </div>
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
