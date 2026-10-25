import { expect, it } from 'vitest';
import { clampPetPosition, createPointerDrag } from './pet-position.js';

/** 缩小视口后宠物和对话窗不能遮挡手机五槽导航或掉出屏幕。 */
it('位置夹紧到手机导航上方并为大于视口的面板保留可达标题', () => {
  expect(
    clampPetPosition({ x: 900, y: 900 }, { width: 390, height: 844 }, { width: 100, height: 120 }),
  ).toEqual({ x: 278, y: 628 });
  expect(
    clampPetPosition({ x: -50, y: -50 }, { width: 320, height: 400 }, { width: 380, height: 500 }),
  ).toEqual({ x: 12, y: 12 });
});
/** 仅移动超过阈值才认定拖拽，取消也必须结束本次手势。 */
it('拖后抑制点击，只接受当前指针，取消后不再移动', () => {
  const drag = createPointerDrag();
  drag.start(7, 10, 20, { x: 100, y: 100 });
  expect(drag.move(8, 300, 300)).toBeNull();
  expect(drag.move(7, 13, 22)).toEqual({ x: 103, y: 102 });
  expect(drag.end(7)).toBe(false);
  drag.start(7, 10, 20, { x: 100, y: 100 });
  expect(drag.move(7, 40, 60)).toEqual({ x: 130, y: 140 });
  expect(drag.end(7)).toBe(true);
  expect(drag.move(7, 90, 90)).toBeNull();
});
