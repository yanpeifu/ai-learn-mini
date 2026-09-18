/** 结算页的星级图标（原型：薰衣草紫实心 + 墨黑描边；未点亮为米白）。 */
const STAR_PATH =
  'M12 2.6l2.9 5.9 6.5.95-4.7 4.6 1.1 6.5L12 17.5l-5.8 3.05 1.1-6.5-4.7-4.6 6.5-.95z'

export function starSvg(filled: boolean): string {
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">` +
    `<path d="${STAR_PATH}" fill="${filled ? '#B9A6F5' : '#F4EDE3'}" stroke="#33302E" ` +
    `stroke-width="1.6" stroke-linejoin="round"/></svg>`
  )
}
