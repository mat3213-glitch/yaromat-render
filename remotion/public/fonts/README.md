# Шрифты TSX-движка

**Боевые шрифты (Lora=TITLE_FONT, Caveat=HAND_FONT)** грузятся через `@remotion/google-fonts`
(см. `remotion/src/fonts.ts`) — официальный загрузчик Remotion, корректно держит загрузку через
весь рендер (многотабовая concurrency), версия пиннута пакетом → детерминированно. Это npm-зависимость
(на GH), не ЯД.

**Эта папка** — под КАСТОМНЫЕ (не-Google) брендовые шрифты: положить `.ttf` сюда → грузить через
`@remotion/fonts` `loadFont({family, url: staticFile('fonts/X.ttf')})` в `fonts.ts`. Только OFL/свободная
лицензия (репо публичный). Раннер берёт их checkout'ом — на ЯД не кладём.

(Ручной FontFace+delayRender НЕ использовать — расится при concurrency, проверено: timeout на длинном клипе.)
