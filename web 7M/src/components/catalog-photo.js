/** 只识别明确的同源演示编号，不替换私密媒体或外站图片。 @param {boolean} simulation 是否示例。 @param {string} source 配图路径。 @returns {number|null} 固定拼图编号。 */
export function demoPhotoIndex(simulation, source) {
  if (!simulation) return null;
  const book = /^\/assets\/book([0-5])\.svg$/.exec(source);
  if (book) return Number(book[1]);
  const item = /^\/assets\/item([0-2])\.svg$/.exec(source);
  return item ? [6, 7, 8][Number(item[1])] : null;
}
