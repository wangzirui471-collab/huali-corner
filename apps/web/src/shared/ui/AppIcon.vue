<script setup>
/** 共享描边 SVG 图标，避免不同系统字符图标形状不一致。 */
defineProps({
  name: { type: String, default: 'grid' },
  size: { type: Number, default: 20 },
});
/** @type {Record<string, string>} 图标名称到描边路径的固定字典。 */
const paths = {
  search: 'M21 21l-5-5M19 10a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  book: 'M4 3h12a3 3 0 0 1 3 3v15H6a3 3 0 0 1-3-3V4a1 1 0 0 1 1-1M3 17h16M7 7h8M7 11h5',
  sofa: 'M5 12V7a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v5M3 10a2 2 0 0 1 2 2v3h14v-3a2 2 0 0 1 4 0v7H1v-7a2 2 0 0 1 2-2M4 19v2m16-2v2',
  ball: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M5.5 5.5l13 13M5.5 18.5l13-13M3 12h18M12 3v18',
  laptop: 'M4 4h16v12H4zM2 20h20l-2-4H4zM9 8h6',
  gift: 'M3 9h18v4H3zM5 13v8h14v-8M12 9v12M12 9H8a3 3 0 1 1 3-3l1 3zm0 0h4a3 3 0 1 0-3-3l-1 3z',
  heart:
    'M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8',
  chat: 'M21 11a9 9 0 0 1-9 9H4l-3 3v-12a10 10 0 0 1 20 0M6 9h10M6 13h7',
  cart: 'M2 3h3l3 12h11l3-9H6M9 20h.01M18 20h.01',
  home: 'M2 11l10-9 10 9M5 9v12h14V9M9 21v-8h6v8',
  forum: 'M4 3h16v18H4zM8 7h8M8 11h8M8 15h5',
  plus: 'M12 5v14M5 12h14',
  user: 'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0M4 21v-2a8 8 0 0 1 16 0v2',
  arrow: 'M4 12h16M14 6l6 6-6 6',
  left: 'M15 5l-7 7 7 7',
  right: 'M9 5l7 7-7 7',
  pause: 'M9 5v14M15 5v14',
  play: 'M8 4l12 8-12 8z',
  bag: 'M5 7h14l2 14H3zM8 7V5a4 4 0 0 1 8 0v2',
  help: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M9 8a3 3 0 0 1 6 0c0 3-3 2-3 5M12 17h.01',
  pin: 'M19 9c0 6-7 13-7 13S5 15 5 9a7 7 0 0 1 14 0M15 9a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0M12 7v5l3 2',
  close: 'M6 6l12 12M6 18L18 6',
  grid: 'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
};
</script>
<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.65"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path :d="paths[name] || paths.grid" />
  </svg>
</template>
