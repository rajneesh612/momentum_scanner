import type { EventCategory } from '../types'

// Color alone never carries category identity on its own — every marker
// is also reachable via click to see its text category name, and the
// legend always pairs color with a label.
export const EVENT_CATEGORIES: { id: EventCategory; label: string; color: string }[] = [
  { id: 'earnings', label: 'Earnings', color: '#a78bfa' },
  { id: 'dividend', label: 'Dividend', color: '#34d399' },
  { id: 'buyback', label: 'Buyback', color: '#f472b6' },
  { id: 'ma', label: 'M&A', color: '#fbbf24' },
  { id: 'order_win', label: 'Order win', color: '#38bdf8' },
  { id: 'regulatory', label: 'Regulatory', color: '#f87171' },
  { id: 'fundraising', label: 'Fundraising', color: '#2dd4bf' },
  { id: 'other', label: 'Other', color: '#94a3b8' },
]

const CATEGORY_MAP = new Map(EVENT_CATEGORIES.map((c) => [c.id, c]))

export function categoryColor(category: string): string {
  return CATEGORY_MAP.get(category as EventCategory)?.color ?? '#94a3b8'
}

export function categoryLabel(category: string): string {
  return CATEGORY_MAP.get(category as EventCategory)?.label ?? category
}
