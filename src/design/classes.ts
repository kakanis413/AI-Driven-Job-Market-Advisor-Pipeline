/** Shared Tailwind class STRINGS (as opposed to tokens.ts's raw values) — kept
 *  as full literal exports, never built with template interpolation, because
 *  Tailwind's build-time scanner only finds class names it can read as text.
 *  Three variants, not one: the ring-offset color has to match the surface the
 *  button sits on (`--surface` vs `--page`), and a couple of very small
 *  icon-only buttons omit the offset entirely because there's no room for it. */

export const FOCUS_RING =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-surface'

export const FOCUS_RING_ON_PAGE =
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-page'

export const FOCUS_RING_TIGHT = 'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent'
