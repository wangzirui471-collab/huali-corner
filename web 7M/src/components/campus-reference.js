/** 校园图集和两张地图选用用户提供的清晰原图，不拉伸旧缩略图。 */
export const referenceMaps = [
  {title:'手绘地图',photo:new URL('../../assets/home-mint/campus-hd/campus-map.jpg', import.meta.url).href},
  {title:'分区与图例',photo:new URL('../../assets/home-mint/campus-hd/campus-map-legend.jpg', import.meta.url).href},
];

export const referencePhotos = [
  {group:'learning',title:'自习室',photo:new URL('../../assets/home-mint/campus-hd/study-room.jpg', import.meta.url).href},
  {group:'learning',title:'自习区全景',photo:new URL('../../assets/home-mint/campus-hd/study-hall.jpg', import.meta.url).href},
  {group:'learning',title:'傍晚阅览室',photo:new URL('../../assets/home-mint/campus-hd/reading-room.jpg', import.meta.url).href},
  {group:'learning',title:'图书馆书架',photo:new URL('../../assets/home-mint/campus-hd/library-shelves.jpg', import.meta.url).href},
  {group:'buildings',title:'校园鸟瞰',photo:new URL('../../assets/home-mint/campus-hd/campus-overview.png', import.meta.url).href},
  {group:'buildings',title:'校园正门',photo:new URL('../../assets/home-mint/campus-hd/campus-gate.jpg', import.meta.url).href},
  {group:'buildings',title:'草坪前的文体楼',photo:new URL('../../assets/home-mint/campus-hd/lawn-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'文体楼侧面',photo:new URL('../../assets/home-mint/campus-hd/hall-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'高层楼宇',photo:new URL('../../assets/home-mint/campus-hd/tower-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'日落下的校园',photo:new URL('../../assets/home-mint/campus-hd/sunset-facade.jpg', import.meta.url).href},
  {group:'buildings',title:'夕阳下的图书馆',photo:new URL('../../assets/home-mint/campus-hd/sunlit-library.jpg', import.meta.url).href},
  {group:'buildings',title:'图书馆正面',photo:new URL('../../assets/home-mint/campus-hd/library-plaza.jpg', import.meta.url).href},
  {group:'buildings',title:'第五教学楼入口',photo:new URL('../../assets/home-mint/campus-hd/fifth-entrance.jpg', import.meta.url).href},
  {group:'buildings',title:'实验楼外景',photo:new URL('../../assets/home-mint/campus-hd/laboratory.jpg', import.meta.url).href},
  {group:'buildings',title:'宿舍楼群',photo:new URL('../../assets/home-mint/campus-hd/dorm-buildings.jpg', import.meta.url).href},
  {group:'scenery',title:'树荫与水景',photo:new URL('../../assets/home-mint/campus-hd/shaded-garden.jpg', import.meta.url).href},
  {group:'scenery',title:'校园晚霞',photo:new URL('../../assets/home-mint/campus-hd/sunset-view.jpg', import.meta.url).href},
  {group:'scenery',title:'石边花池',photo:new URL('../../assets/home-mint/campus-hd/rock-pond.jpg', import.meta.url).href},
  {group:'scenery',title:'园林雕塑',photo:new URL('../../assets/home-mint/campus-hd/garden-sculpture.jpg', import.meta.url).href},
  {group:'scenery',title:'湖畔建筑',photo:new URL('../../assets/home-mint/campus-hd/lakefront.jpg', import.meta.url).href},
  {group:'scenery',title:'湖与球场航拍',photo:new URL('../../assets/home-mint/campus-hd/lake-aerial.jpg', import.meta.url).href},
  {group:'scenery',title:'湖畔教学区',photo:new URL('../../assets/home-mint/campus-hd/lake-teaching.jpg', import.meta.url).href},
  {group:'life',title:'宿舍内景',photo:new URL('../../assets/home-mint/campus-hd/dorm-room.jpg', import.meta.url).href},
  {group:'life',title:'带阳台的宿舍',photo:new URL('../../assets/home-mint/campus-hd/dorm-balcony.png', import.meta.url).href},
  {group:'life',title:'上床下桌宿舍',photo:new URL('../../assets/home-mint/campus-hd/dorm-bunk.png', import.meta.url).href},
  {group:'life',title:'室内球馆',photo:new URL('../../assets/home-mint/campus-hd/indoor-court.png', import.meta.url).href},
  {group:'life',title:'健身房',photo:new URL('../../assets/home-mint/campus-hd/fitness-room.jpg', import.meta.url).href},
  {group:'life',title:'卫浴参考',photo:new URL('../../assets/home-mint/campus-hd/washroom.jpg', import.meta.url).href},
];

// 按参考图能辨认的湖、南北通道和红砖街区重画地形。各区内的楼栋几何仅用于表现体量。
export const mapBlocks = [
  {x:19,y:26,w:8,h:16},{x:27,y:46,w:10,h:10},{x:17,y:59,w:9,h:16},
  {x:17,y:78,w:20,h:8},{x:38,y:54,w:9,h:18},{x:44,y:78,w:9,h:8},
  {x:61,y:19,w:9,h:14},{x:66,y:41,w:10,h:9},{x:79,y:42,w:9,h:14},
  {x:89,y:54,w:6,h:12},{x:49,y:30,w:5,h:11},{x:8,y:63,w:5,h:15},
];
