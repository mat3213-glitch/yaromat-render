import React from 'react';
import {Composition} from 'remotion';
import {templatePropsSchema, TemplateProps, FPS, PREVIEW_SEC, FORMAT_DIMS} from './contract';
import {KineticCard} from './templates/KineticCard';
import {KineticWords} from './templates/KineticWords';

/**
 * Реестр шаблонов. mimo ДОБАВЛЯЕТ сюда РОВНО одну строку на свой новый шаблон
 * (import выше + объект в массиве). Это единственное место вне templates/, куда он пишет.
 */
const TEMPLATES: {id: string; component: React.FC<TemplateProps>}[] = [
  {id: 'KineticCard', component: KineticCard},
  {id: 'KineticWords', component: KineticWords},
];

const DEFAULT_PROPS: TemplateProps = {
  artUrl: 'testart.jpg',
  trackTitle: 'sky is in my hands',
  brand: 'yaromat',
  palette: ['#0b0d10', '#1a2230', '#cfd6dd'],
  seed: 42,
  format: 'vertical',
};

export const RemotionRoot: React.FC = () => {
  return (
    <>
      {TEMPLATES.map(({id, component}) => (
        <Composition
          key={id}
          id={id}
          component={component as React.FC<Record<string, unknown>>}
          schema={templatePropsSchema}
          defaultProps={DEFAULT_PROPS}
          fps={FPS}
          durationInFrames={FPS * PREVIEW_SEC}
          width={FORMAT_DIMS.vertical.width}
          height={FORMAT_DIMS.vertical.height}
          calculateMetadata={({props}: {props: TemplateProps}) => {
            const dims = FORMAT_DIMS[props.format as 'square' | 'vertical'] ?? FORMAT_DIMS.vertical;
            const durationInFrames = props.durationSec
              ? Math.round(props.durationSec * FPS)
              : FPS * PREVIEW_SEC;
            return {width: dims.width, height: dims.height, fps: FPS, durationInFrames};
          }}
        />
      ))}
    </>
  );
};
