import {staticFile, delayRender, continueRender} from 'remotion';

/**
 * Брендовые шрифты — БАНДЛ в remotion/public/fonts/ (в репо, не на ЯД).
 * Раннер получает их вместе с checkout → рендер детерминирован на любой машине
 * (не зависит от того, какой шрифт случайно стоит на раннере).
 *
 * Загрузка через FontFace + delayRender (ядро remotion, без доп. зависимостей):
 * рендер ждёт, пока шрифт реально загрузится, потом снимает кадры.
 */
function load(family: string, file: string) {
  const handle = delayRender(`font:${family}`);
  const face = new FontFace(family, `url(${staticFile('fonts/' + file)}) format('truetype')`);
  face
    .load()
    .then((loaded) => {
      document.fonts.add(loaded);
      continueRender(handle);
    })
    .catch(() => continueRender(handle)); // не вешать рендер, если шрифт не подгрузился
}

load('Lora', 'Lora.ttf');
load('Caveat', 'Caveat.ttf');

// TITLE_FONT — чистый serif для титров/названий. HAND_FONT — рукописный бренд-акцент.
export const TITLE_FONT = "'Lora', Georgia, serif";
export const HAND_FONT = "'Caveat', cursive";
