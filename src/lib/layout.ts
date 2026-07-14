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

  const h = hierarchy(root, (d) => d.children)
    .sum((d) =>
      d.major ? (d.major.cip === spotlightCip ? d.major.completions * 3 : d.major.completions) : 0,
    )
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0))

  const laid = treemap<HDatum>()
    .tile(treemapResquarify)
    .size([Math.max(1, width), Math.max(1, height)])
    .paddingInner((n) => (n.depth === 0 ? 8 : 3))
    .paddingTop((n) => (n.depth === 1 ? 24 : 0))(h)

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
