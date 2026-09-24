/**
 * 小程序端不能直接写 <svg> 标签（WXML 不支持），
 * 所以把 SVG 转成 data URI，用 background-image 渲染 —— weapp 与 H5 都支持。
 */
export function svgToDataUri(svg: string): string {
  const compact = svg.replace(/\s+/g, ' ').trim()
  return `data:image/svg+xml,${encodeURIComponent(compact)}`
}
