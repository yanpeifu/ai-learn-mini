/**
 * 线性图标（统一 2px 描边 + 圆头端点，与原型「四 · 图标规范」一致）。
 * 原型明确要求：**禁止用 emoji 作为功能图标**。
 */

export type IconName =
  | 'home'
  | 'mine'
  | 'back'
  | 'share'
  | 'save'
  | 'retry'
  | 'delete'
  | 'report'
  | 'lock'
  | 'star'
  | 'clock'
  | 'chart'
  | 'book'
  | 'law'
  | 'language'
  | 'code'
  | 'edit'
  | 'bulb'
  | 'play'
  | 'close'
  | 'check'

const INK = '#33302E'

function wrap(paths: string, strokeWidth = 2): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" ` +
    `stroke="${INK}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round">` +
    paths +
    `</svg>`
  )
}

export const ICON_SVG: Record<IconName, string> = {
  home: wrap('<path d="M4 11 12 4l8 7v8a1 1 0 0 1-1 1h-5v-6h-4v6H5a1 1 0 0 1-1-1z"/>'),
  mine: wrap('<circle cx="12" cy="8" r="3.5"/><path d="M5 20c0-3.5 3.1-6 7-6s7 2.5 7 6"/>'),
  back: wrap('<path d="M15 5 8 12l7 7"/>'),
  share: wrap(
    '<circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><path d="m8.2 10.8 7.6-3.6M8.2 13.2l7.6 3.6"/>'
  ),
  save: wrap('<path d="M12 4v11m0 0 4-4m-4 4-4-4M5 19h14"/>'),
  retry: wrap('<path d="M20 12a8 8 0 1 1-2.3-5.7M20 4v5h-5"/>'),
  delete: wrap('<path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6"/>'),
  report: wrap('<path d="M6 21V4M6 5h11l-2.5 3.5L17 12H6"/>'),
  lock: wrap('<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'),
  star: wrap('<path d="m12 4 2.5 5 5.5.8-4 3.9.9 5.5-4.9-2.6-4.9 2.6.9-5.5-4-3.9 5.5-.8z"/>'),
  clock: wrap('<circle cx="12" cy="12" r="8.5"/><path d="M12 8v4.5l3 2"/>'),
  chart: wrap('<path d="M4 19V10M12 19V5M20 19v-6"/>'),
  book: wrap('<path d="M4 5a2 2 0 0 1 2-2h12v18H6a2 2 0 0 1-2-2z"/><path d="M8 3v18"/>'),
  law: wrap('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M9 8h6M9 12h6"/>'),
  language: wrap(
    '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.2 2.4 3.3 5.3 3.3 8.5S14.2 18.1 12 20.5c-2.2-2.4-3.3-5.3-3.3-8.5S9.8 5.9 12 3.5z"/>'
  ),
  code: wrap('<path d="m9 8-5 4 5 4M15 8l5 4-5 4"/>'),
  edit: wrap('<path d="M16 4l4 4-10 10H6v-4zM14 6l4 4"/>'),
  bulb: wrap(
    '<path d="M9 18h6M10 21h4M12 3a6 6 0 0 0-3.5 10.9c.5.4.9 1 .9 1.6V17h5.2v-1.5c0-.6.4-1.2.9-1.6A6 6 0 0 0 12 3z"/>'
  ),
  play: wrap('<path d="M8 5.5v13l11-6.5z"/>'),
  close: wrap('<path d="M6 6l12 12M18 6 6 18"/>'),
  check: wrap('<path d="M5 13l4 4L19 7"/>')
}
