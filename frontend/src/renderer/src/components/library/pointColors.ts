/** 合集 → 点色映射（VECTOR_GRAPH_PLAN.md §4）。
 * 同一合集跨会话稳定同色：全量合集名排序后按下标配 10 色板；
 * 点色取该条目排序后的第一个合集，未入合集为 zinc 灰。纯函数，可单测。 */

// 对齐暗色 aurora 主题的高亮 10 色板
export const PALETTE = [
  '#818cf8', // indigo-400
  '#c084fc', // purple-400
  '#22d3ee', // cyan-400
  '#34d399', // emerald-400
  '#fbbf24', // amber-400
  '#fb7185', // rose-400
  '#38bdf8', // sky-400
  '#e879f9', // fuchsia-400
  '#2dd4bf', // teal-400
  '#a3e635' // lime-400
] as const

export const UNCOLLECTED_COLOR = '#71717a' // zinc-500

/** 合集名列表 → 该合集的颜色（未收录/未合集返回灰色） */
export function collectionColor(allNames: string[], target: string | null): string {
  if (!target) return UNCOLLECTED_COLOR
  const sorted = [...allNames].sort((a, b) => a.localeCompare(b))
  const index = sorted.indexOf(target)
  if (index === -1) return UNCOLLECTED_COLOR
  return PALETTE[index % PALETTE.length]
}

/** 点的主色 = 条目合集排序后的第一个 */
export function pointColor(collections: string[], allNames: string[]): string {
  const primary = [...collections].sort((a, b) => a.localeCompare(b))[0]
  return collectionColor(allNames, primary ?? null)
}

/** 条目的主合集（排序后第一个；无合集返回 null） */
export function primaryCollection(collections: string[]): string | null {
  return [...collections].sort((a, b) => a.localeCompare(b))[0] ?? null
}
