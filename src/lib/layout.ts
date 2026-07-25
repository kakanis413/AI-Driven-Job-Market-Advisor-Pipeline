/** Treemap layout — a pure function. D3 computes; React renders. */

import { hierarchy, treemap, treemapResquarify } from 'd3-hierarchy'
import { FAMILY_ORDER } from '../design/tokens'
import type { Family, Major } from '../types'

export interface Rect {
  x: number
  y: number
  w: number
  h: number
}

export interface Tile extends Rect {
  major: Major
}

export interface Band extends Rect {
  family: Family
}

interface HDatum {
  family?: Family
  major?: Major
  children?: HDatum[]
}

/** Two-level treemap (family → major), tiles sized by completions.
 *  `spotlightCip` triples that major's weight so the layout physically
 *  re-flows around it — the find-your-major spotlight is a re-layout,
 *  not a zoom hack. `resquarify` keeps other tiles stable while it moves. */
export function layoutTreemap(
  majors: Major[],
  width: number,
  height: number,
  spotlightCip?: string | null,
): { tiles: Tile[]; bands: Band[] } {
  const root: HDatum = {
    children: FAMILY_ORDER.map((family) => ({
      family,
      children: majors.filter((m) => m.family === family).map((major) => ({ major })),
    })).filter((f) => f.children.length > 0),
  }

  // Tile sizing: rank by graduates, but gently compress the range. Raw grad
  // counts span ~4000x (a huge major vs a tiny one), which makes small families
  // (Trades) vanish and the biggest tiles swallow the map. A power transform
  // keeps the ranking (more grads = bigger tile) and every tile distinct — so
  // the map stays big/medium/small, NOT a uniform grid — while lifting the
  // smallest enough to be seen. Layout-only; never mutates the data. Lower the
  // exponent to lift small families further; 1.0 = exact graduate area.
  const SIZE_EXPONENT = 0.6
  const weight = (m: Major) => Math.pow(m.completions || 0, SIZE_EXPONENT)

  const h = hierarchy(root, (d) => d.children)
    .sum((d) =>
      d.major ? (d.major.cip === spotlightCip ? weight(d.major) * 3 : weight(d.major)) : 0,
    )
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))

  const laid = treemap<HDatum>()
    .tile(treemapResquarify)
    .size([Math.max(1, width), Math.max(1, height)])
    // Tile gaps tuned for a tight mosaic: family blocks stay separated (6px),
    // but majors WITHIN a family sit close (1.5px) so each family reads as one
    // solid region instead of scattered chips. Pairs with the 1px tile stroke,
    // which becomes the crisp, uniform "grout" line between adjacent tiles.
    .paddingInner((n) => (n.depth === 0 ? 6 : 1.5))
    .paddingTop((n) => (n.depth === 1 ? 22 : 0))(h)

  const tiles: Tile[] = laid
    .leaves()
    .filter((n) => n.data.major)
    .map((n) => ({
      major: n.data.major as Major,
      x: n.x0,
      y: n.y0,
      w: Math.max(0, n.x1 - n.x0),
      h: Math.max(0, n.y1 - n.y0),
    }))

  const bands: Band[] = (laid.children ?? []).map((n) => ({
    family: n.data.family as Family,
    x: n.x0,
    y: n.y0,
    w: Math.max(0, n.x1 - n.x0),
    h: Math.max(0, n.y1 - n.y0),
  }))

  return { tiles, bands }
}
