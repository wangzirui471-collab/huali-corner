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

/** 手绘原图的像素锚点，均按同一张 1080 × 540 图片核对。 */
export const campusMapSize = [1080, 540];
export const campusMapPoints = [
  {label:'A 区', name:'A1–A4 栋', x:109, y:194},
  {label:'B1–B4', name:'B1–B4 栋', x:652, y:112},
  {label:'B9', name:'B9 栋', x:550, y:52},
  {label:'C 区', name:'C1–C8 栋', x:916, y:224},
  {label:'D1', name:'D1 栋', x:872, y:74},
  {label:'D2 / D5 / D6', name:'D2、D5、D6 栋', x:222, y:181},
  {label:'G 区', name:'G1–G4 栋', x:117, y:403},
  {label:'L1–L9', name:'L1–L9 栋', x:404, y:299},
  {label:'L10–L13', name:'L10–L13 栋', x:172, y:258},
  {label:'L15–L18', name:'L15–L18 栋', x:535, y:445},
  {label:'华立湖', name:'华立湖', x:412, y:154, photo:'湖与球场航拍'},
  {label:'图书馆', name:'本科图书馆', x:755, y:275, photo:'图书馆正面'},
  {label:'五教', name:'第五教学楼', x:623, y:353, photo:'第五教学楼入口'},
  {label:'文体楼', name:'文体楼', x:627, y:272, photo:'文体楼侧面'},
  {label:'校门', name:'本科校门', x:751, y:491, photo:'校园正门'},
];
