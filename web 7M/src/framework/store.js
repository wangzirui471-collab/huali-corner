/** Pinia 唯一实例；旧页面读写的 state 与 Vue 组件共享同一份业务状态。 */
import {createPinia, defineStore} from 'pinia';
import {ref, shallowRef} from 'vue';
import {readSessionToken} from '../core/session.js';

export const pinia = createPinia();

/** 创建业务字段与运行时句柄；不持久化用户资料、密码或第二份令牌。 */
export const useSiteStore = defineStore('site', () => ({
  token: ref(window.HUALI_STATIC_DEMO ? '' : readSessionToken()),
  me: ref(null),
  config: ref({}),
  filter: ref({category: '', q: '', sort: ''}),
  poll: shallowRef(null),
  poll2: shallowRef(null),
  renderId: ref(0),
  cart: ref([]),
  freeShelf: ref(false),
  homeLimit: ref(40),
  homeView: shallowRef(null),
  postsFeed: ref([]),
  messageCursor: ref(0),
  pendingWant: ref(null),
  mediaURLs: shallowRef(new Set()),
}));
