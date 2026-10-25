/** @typedef {{x:number,y:number}} PetPosition 视口 CSS 像素坐标。 */
/** 视口尺寸变化时夹紧浮层，手机底部额外留出五槽导航及安全区。
 * @param {PetPosition} point 期望坐标。 @param {{width:number,height:number}} viewport 视口。
 * @param {{width:number,height:number}} size 浮层尺寸。 @returns {PetPosition} 可达坐标。
 */
export function clampPetPosition(point, viewport, size) {
  const bottom = viewport.width <= 760 ? 96 : 12;
  return {
    x: Math.max(12, Math.min(point.x, viewport.width - size.width - 12)),
    y: Math.max(12, Math.min(point.y, viewport.height - size.height - bottom)),
  };
}
/** 管理单指针拖动；阈值区分点击，结束时向调用方返回是否应屏蔽合成点击。 */
export function createPointerDrag() {
  let current = /** @type {{id:number,x:number,y:number,origin:PetPosition,moved:boolean}|null} */ (
    null
  );
  return {
    /** 开始一次拖动。 @param {number} id 指针编号。 @param {number} x 起点横坐标。 @param {number} y 起点纵坐标。 @param {PetPosition} origin 元素起点。 */
    start(id, x, y, origin) {
      current = { id, x, y, origin: { ...origin }, moved: false };
    },
    /** 仅跟踪活动指针。 @param {number} id 指针编号。 @param {number} x 横坐标。 @param {number} y 纵坐标。 */
    move(id, x, y) {
      if (!current || current.id !== id) return null;
      const dx = x - current.x,
        dy = y - current.y;
      current.moved ||= Math.hypot(dx, dy) > 6;
      return { x: current.origin.x + dx, y: current.origin.y + dy };
    },
    /** 释放或取消指针。 @param {number} id 指针编号。 */
    end(id) {
      if (!current || current.id !== id) return false;
      const moved = current.moved;
      current = null;
      return moved;
    },
  };
}
