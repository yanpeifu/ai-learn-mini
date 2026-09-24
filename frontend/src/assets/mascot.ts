/**
 * 颜宝（原创吉祥物 · 方案 A 小橘团）的 8 个表情。
 * 造型与配色**完全照搬原型**（原型-1/2/3 与《UI设计风格方案》v1.2 已定稿）：
 * 橘色圆身 + 墨黑描边 + 两点式眼睛 + 呆毛，表情只靠眉毛/嘴型/腮红变化。
 */

export type YanbaoMood =
  | 'happy' // 期待：首页等待输入
  | 'think' // 思考：生成中 / 引导问题 / 退出确认
  | 'star' // 惊喜：答对
  | 'shy' // 挠头：答错 / 尴尬
  | 'cheer' // 欢呼：连对 / 通关
  | 'peek' // 探头：空状态
  | 'sad' // 委屈：网络错误 / 生成失败
  | 'go' // 加油：连续答错时鼓励

const ORANGE = '#FFA85C'
const INK = '#33302E'
const CORAL = '#FF9A9A'
const PAPER = '#FFFCF7'
const LAVENDER = '#B9A6F5'
const MOUTH = '#C4564F'

const BODY = (cy: number, r: number) =>
  `<circle cx="60" cy="${cy}" r="${r}" fill="${ORANGE}" stroke="${INK}" stroke-width="3"/>`

const AHOOGE = (d: string) =>
  `<path d="${d}" fill="none" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>`

const BLUSH = (opacity: string, radius = 6, cy = 74) =>
  `<circle cx="37" cy="${cy}" r="${radius}" fill="${CORAL}" opacity="${opacity}"/>` +
  `<circle cx="83" cy="${cy}" r="${radius}" fill="${CORAL}" opacity="${opacity}"/>`

const HAIR = 'M60 30 C57 20 63 15 68 12'

export const MASCOT_SVG: Record<YanbaoMood, string> = {
  happy:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    BODY(66, 38) +
    AHOOGE(HAIR) +
    `<circle cx="47" cy="62" r="4.5" fill="${INK}"/><circle cx="73" cy="62" r="4.5" fill="${INK}"/>` +
    `<circle cx="48.6" cy="60" r="1.6" fill="${PAPER}"/><circle cx="74.6" cy="60" r="1.6" fill="${PAPER}"/>` +
    AHOOGE('M53 76 Q60 82 67 76') +
    BLUSH('0.7') +
    `</svg>`,
  think:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    BODY(66, 38) +
    AHOOGE(HAIR) +
    AHOOGE('M42 62 Q47 57 52 62') +
    AHOOGE('M68 62 Q73 57 78 62') +
    AHOOGE('M55 78 Q60 73 65 78') +
    BLUSH('0.7') +
    `</svg>`,
  star:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    BODY(66, 38) +
    AHOOGE(HAIR) +
    `<path d="M47 56 L49 62 L55 64 L49 66 L47 72 L45 66 L39 64 L45 62 Z" fill="${INK}"/>` +
    `<path d="M73 56 L75 62 L81 64 L75 66 L73 72 L71 66 L65 64 L71 62 Z" fill="${INK}"/>` +
    AHOOGE('M52 76 Q60 86 68 76') +
    BLUSH('0.7') +
    `</svg>`,
  shy:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    BODY(66, 38) +
    AHOOGE(HAIR) +
    AHOOGE('M42 64 Q47 58 52 64') +
    AHOOGE('M68 64 Q73 58 78 64') +
    `<path d="M56 78 L64 78" stroke="${INK}" stroke-width="3" stroke-linecap="round"/>` +
    `<circle cx="36" cy="75" r="7.5" fill="${CORAL}" opacity="0.8"/>` +
    `<circle cx="84" cy="75" r="7.5" fill="${CORAL}" opacity="0.8"/>` +
    `<path d="M92 40 Q99 34 104 42" fill="none" stroke="${INK}" stroke-width="2.6" stroke-linecap="round" opacity="0.7"/>` +
    `</svg>`,
  cheer:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    BODY(66, 38) +
    AHOOGE(HAIR) +
    AHOOGE('M42 60 Q47 53 52 60') +
    AHOOGE('M68 60 Q73 53 78 60') +
    `<path d="M50 74 Q60 88 70 74 Z" fill="${MOUTH}" stroke="${INK}" stroke-width="3" stroke-linejoin="round"/>` +
    `<circle cx="36" cy="73" r="7" fill="${CORAL}" opacity="0.75"/>` +
    `<circle cx="84" cy="73" r="7" fill="${CORAL}" opacity="0.75"/>` +
    `<path d="M18 34 L24 30 M18 44 L24 48 M102 34 L96 30 M102 44 L96 48" stroke="${LAVENDER}" stroke-width="3" stroke-linecap="round"/>` +
    `</svg>`,
  peek:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    BODY(70, 38) +
    AHOOGE('M60 34 C57 26 62 21 66 18') +
    `<circle cx="48" cy="66" r="4.5" fill="${INK}"/>` +
    AHOOGE('M69 66 Q74 61 79 66') +
    AHOOGE('M54 80 Q60 85 66 80') +
    `<circle cx="38" cy="78" r="6" fill="${CORAL}" opacity="0.7"/>` +
    `</svg>`,
  sad:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    BODY(68, 38) +
    AHOOGE('M60 32 C58 24 63 20 66 17') +
    AHOOGE('M43 66 Q48 71 53 66') +
    AHOOGE('M67 66 Q72 71 77 66') +
    AHOOGE('M53 84 Q60 76 67 84') +
    `<circle cx="38" cy="78" r="5.5" fill="${CORAL}" opacity="0.55"/>` +
    `<circle cx="82" cy="78" r="5.5" fill="${CORAL}" opacity="0.55"/>` +
    `</svg>`,
  go:
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">` +
    AHOOGE('M26 78 Q20 62 30 54') +
    AHOOGE('M94 78 Q100 62 90 54') +
    BODY(68, 36) +
    AHOOGE('M60 34 C57 25 63 20 67 17') +
    `<circle cx="48" cy="64" r="4.5" fill="${INK}"/><circle cx="72" cy="64" r="4.5" fill="${INK}"/>` +
    `<circle cx="49.6" cy="62" r="1.6" fill="${PAPER}"/><circle cx="73.6" cy="62" r="1.6" fill="${PAPER}"/>` +
    `<path d="M54 78 L66 78" stroke="${INK}" stroke-width="3.4" stroke-linecap="round"/>` +
    `<circle cx="38" cy="76" r="6" fill="${CORAL}" opacity="0.7"/>` +
    `<circle cx="82" cy="76" r="6" fill="${CORAL}" opacity="0.7"/>` +
    `</svg>`
}

export const MASCOT_ALT: Record<YanbaoMood, string> = {
  happy: '开心',
  think: '思考',
  star: '惊喜',
  shy: '挠头',
  cheer: '欢呼',
  peek: '探头',
  sad: '委屈',
  go: '加油'
}
