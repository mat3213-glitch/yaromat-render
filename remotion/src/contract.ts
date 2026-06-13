import {z} from 'zod';

/**
 * КОНТРАКТ TSX-шаблона. КАЖДЫЙ шаблон (в т.ч. написанный субагентом mimo) ОБЯЗАН
 * принимать ровно эти props и ничего больше из внешнего мира. Это граница песочницы:
 * шаблон — чистая функция (props → кадры), без сети, без файловой системы, без секретов.
 *
 * Бренд/вайб-правила (незыблемо):
 *   • brand = 'yaromat' ВСЕГДА строчными латиницей (feedback_brand_name)
 *   • НИКАКОГО неона (feedback_no_neon) — палитра приглушённая, плёночная
 *   • вайб = внутренняя глубина, не одиночество; без масок/лиц/эзотерики (feedback_vibe_inner_depth)
 */
export const templatePropsSchema = z.object({
  // staticFile-путь вайб-арта (лежит в remotion/public/), напр. "testart.jpg"
  artUrl: z.string(),
  // название трека, напр. "sky is in my hands"
  trackTitle: z.string(),
  // бренд — всегда 'yaromat' строчными
  brand: z.string().default('yaromat'),
  // приглушённая палитра (НЕ неон): [bg, mid, accent-light]
  palette: z.array(z.string()).default(['#0b0d10', '#1a2230', '#cfd6dd']),
  // per-track seed — детерминизм (square=vertical одного трека = один seed)
  seed: z.number().default(42),
  // формат кадра
  format: z.enum(['square', 'vertical']).default('vertical'),
});

export type TemplateProps = z.infer<typeof templatePropsSchema>;

export const FPS = 30;
export const PREVIEW_SEC = 6; // длина песочничного превью

export const FORMAT_DIMS = {
  square: {width: 1080, height: 1080},
  vertical: {width: 1080, height: 1920},
} as const;

// Детерминированный ГПСЧ от seed (mulberry32) — чтобы рандом в шаблоне был воспроизводим.
export function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
