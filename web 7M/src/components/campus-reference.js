/** 用户提供的低分辨率参考图，重复照片只收录一次。 */
export const referenceMaps = [
  {title:'手绘地图',photo:new URL('../../assets/home-mint/campus-reference/campus-map.jpg', import.meta.url).href},
  {title:'分区与图例',photo:new URL('../../assets/home-mint/campus-reference/campus-map-legend.jpg', import.meta.url).href},
];

export const referencePhotos = [
  {group:'learning',title:'阶梯教室',photo:new URL('../../assets/home-mint/campus-reference/classroom.jpg', import.meta.url).href},
  {group:'learning',title:'窗边自习',photo:new URL('../../assets/home-mint/campus-reference/study-corner.jpg', import.meta.url).href},
  {group:'learning',title:'阅览室',photo:new URL('../../assets/home-mint/campus-reference/reading-room.jpg', import.meta.url).href},
  {group:'learning',title:'图书馆书架',photo:new URL('../../assets/home-mint/campus-reference/library-shelves.jpg', import.meta.url).href},
  {group:'buildings',title:'校园鸟瞰',photo:new URL('../../assets/home-mint/campus-reference/campus-overview.jpg', import.meta.url).href},
  {group:'buildings',title:'红砖楼群',photo:new URL('../../assets/home-mint/campus-reference/red-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'草坪前的楼宇',photo:new URL('../../assets/home-mint/campus-reference/lawn-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'广场前的楼宇',photo:new URL('../../assets/home-mint/campus-reference/square-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'高层楼宇',photo:new URL('../../assets/home-mint/campus-reference/tower-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'日落下的校园',photo:new URL('../../assets/home-mint/campus-reference/sunset-facade.jpg', import.meta.url).href},
  {group:'scenery',title:'树荫与水景',photo:new URL('../../assets/home-mint/campus-reference/shaded-garden.jpg', import.meta.url).href},
  {group:'scenery',title:'校园晚霞',photo:new URL('../../assets/home-mint/campus-reference/sunset-view.jpg', import.meta.url).href},
  {group:'scenery',title:'石边花池',photo:new URL('../../assets/home-mint/campus-reference/rock-pond.jpg', import.meta.url).href},
  {group:'scenery',title:'园林雕塑',photo:new URL('../../assets/home-mint/campus-reference/garden-sculpture.jpg', import.meta.url).href},
  {group:'scenery',title:'湖畔建筑',photo:new URL('../../assets/home-mint/campus-reference/lakefront.jpg', import.meta.url).href},
  {group:'scenery',title:'湖与球场航拍',photo:new URL('../../assets/home-mint/campus-reference/lake-aerial.jpg', import.meta.url).href},
  {group:'life',title:'室内球馆',photo:new URL('../../assets/home-mint/campus-reference/indoor-court.jpg', import.meta.url).href},
  {group:'life',title:'卫浴参考',photo:new URL('../../assets/home-mint/campus-reference/washroom.jpg', import.meta.url).href},
  {group:'buildings',title:'夕阳下的红砖楼',photo:new URL('../../assets/home-mint/campus-reference/sunlit-building.jpg', import.meta.url).href},
  {group:'buildings',title:'红砖楼入口',photo:new URL('../../assets/home-mint/campus-reference/red-brick-entry.jpg', import.meta.url).href},
];

// 按参考图能辨认的湖、南北通道和红砖街区重画地形。各区内的楼栋几何仅用于表现体量。
export const mapBlocks = [
  {x:19,y:26,w:8,h:16},{x:27,y:46,w:10,h:10},{x:17,y:59,w:9,h:16},
  {x:17,y:78,w:20,h:8},{x:38,y:54,w:9,h:18},{x:44,y:78,w:9,h:8},
  {x:61,y:19,w:9,h:14},{x:66,y:41,w:10,h:9},{x:79,y:42,w:9,h:14},
  {x:89,y:54,w:6,h:12},{x:49,y:30,w:5,h:11},{x:8,y:63,w:5,h:15},
];
