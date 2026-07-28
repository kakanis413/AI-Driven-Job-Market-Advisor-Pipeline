/** Tiny shared glyphs reused across several unrelated dismiss buttons (the
 *  advisor panel, the mobile preview sheet, ShareCard's dialog, the school
 *  chip in Chat). Same path everywhere — only size/weight vary by call site —
 *  so this is the one place to change the shape. */

export function CloseIcon({
  size = 12,
  strokeWidth = 1.6,
}: {
  size?: number
  strokeWidth?: number
}) {
  return (
    <svg width={size} height={size} viewBox="0 0 13 13" fill="none" aria-hidden>
      <path d="M2 2l9 9M11 2l-9 9" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" />
    </svg>
  )
}
