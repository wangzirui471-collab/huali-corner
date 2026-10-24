<script setup>
import { computed, reactive, ref, watch } from 'vue';
import { useRouter, RouterLink } from 'vue-router';
import { ElInput } from 'element-plus';
import { session, readStorage, writeStorage } from '@/shared/legacy/session.js';
import { row, text, number } from '@/shared/legacy/dto.js';
import { ApiError } from '@/shared/http/client.js';
import { useAction } from '@/shared/legacy/use-task.js';
import { useLegacyApi } from '@/shared/legacy/use-task.js';
const api = useLegacyApi();
import { yuanToCents } from '@/features/trade/checkout.js';
import AppButton from '@/shared/ui/AppButton.vue';
import TaskFeedback from '@/shared/ui/TaskFeedback.vue';
const router = useRouter(),
  action = useAction(),
  uncertain = ref(false),
  progress = ref('');
const draftKey = `hc-vue-publish-${number(session.me, 'id')}`;
const defaults = {
  title: '',
  description: '',
  category: 'books',
  price: '',
  original_price: '',
  condition: '正常使用痕迹',
  delivery: 'both',
  delivery_fee: '0',
  region: '',
  edition: '',
  publisher: '',
  author: '',
  isbn: '',
  notes: '无笔记',
  missing: '无缺页',
  accessories: '无附件',
  course: '',
  bought: '',
};
/** 恢复当前账号的非敏感表单，不从存储恢复文件或上传权限。 */
function initialDraft() {
  try {
    const saved = row(JSON.parse(readStorage(draftKey, true) || '{}'));
    return Object.fromEntries(
      Object.entries(defaults).map(([key, value]) => [
        key,
        typeof saved[key] === 'string' ? saved[key] : value,
      ]),
    );
  } catch {
    return defaults;
  }
}
const form = reactive(/** @type {typeof defaults} */ (initialDraft()));
const files = reactive(
  /** @type {Record<string,File[]>} */ ({ front: [], side: [], top: [], extra: [] }),
);
const uploaded = new Map();
const angles = [
  { key: 'front', label: '正面' },
  { key: 'side', label: '侧面' },
  { key: 'top', label: '顶部' },
  { key: 'extra', label: '补充照片（最多 6 张）' },
];
const saved = ref(true);
watch(form, () => {
  saved.value = writeStorage(draftKey, JSON.stringify(form), true);
});
const buildings = computed(() =>
  Array.isArray(session.config.buildings) ? session.config.buildings.map(String) : [],
);
/** 文件只留在当前页面，切换账号后页面销毁；实际格式与像素由服务端校验。 @param {Event} event 文件选择。 @param {string} angle 拍摄角度。 */
function selectFiles(event, angle) {
  files[angle] = Array.from(/** @type {HTMLInputElement} */ (event.target).files || []);
}
/** 以 base64 兼容旧上传接口，不将原始文件写入本地存储。 @param {File} file 本地图片。 @returns {Promise<string>} */
async function fileContent(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('图片读取失败'));
    reader.readAsDataURL(file);
  });
}
/** 校验后顺序上传并复用已成功编号；商品写入未知时禁止盲目再次发布。 */
async function publish() {
  await action.run(async () => {
    if (number(session.me, 'score') < 60) throw new Error('信誉低于 60 分，暂时无法发布');
    if (!form.title.trim() || !form.description.trim() || !form.region.trim())
      throw new Error('请填写商品标题、介绍与公共交付地点');
    if (form.category === 'books' && (!form.edition.trim() || !form.publisher.trim()))
      throw new Error('二手书须填写版次和出版社，不确定请写待确认');
    if (
      ['front', 'side', 'top'].some((angle) => files[angle].length !== 1) ||
      files.extra.length > 6
    )
      throw new Error('请分别选择正面、侧面、顶部实拍；补图最多 6 张');
    const selected = angles.flatMap((angle) =>
      files[angle.key].map((file) => ({ file, angle: angle.key })),
    );
    const digests = new Set();
    for (const { file } of selected) {
      if (!/^image\/(jpeg|png|webp)$/.test(file.type) || !file.size || file.size > 5 * 1024 * 1024)
        throw new Error('每张图片须为不超过 5MB 的 JPEG、PNG 或 WebP');
      const digest = Array.from(
        new Uint8Array(await crypto.subtle.digest('SHA-256', await file.arrayBuffer())),
      ).join(',');
      if (digests.has(digest)) throw new Error('请使用不同角度实拍，不能重复上传同一图片');
      digests.add(digest);
    }
    const payload = {
      ...form,
      price: yuanToCents(form.price),
      original_price: yuanToCents(form.original_price || '0'),
      delivery_fee: yuanToCents(form.delivery_fee || '0'),
      college: text(session.me, 'college'),
      photos: /** @type {string[]} */ ([]),
    };
    for (const { file, angle } of selected) {
      progress.value = `正在上传${angles.find((item) => item.key === angle)?.label}`;
      let id = uploaded.get(file);
      if (!id) {
        id = text(
          row(await api('/upload', { body: { content: await fileContent(file), angle } })),
          'id',
        );
        if (!id) throw new Error('上传响应缺少图片编号');
        uploaded.set(file, id);
      }
      payload.photos.push(id);
    }
    progress.value = '正在提交商品';
    try {
      const result = row(await api('/publish', { body: payload }));
      writeStorage(draftKey, null, true);
      await router.push('/products/' + number(result, 'id'));
    } catch (error) {
      uncertain.value = error instanceof ApiError && error.outcomeUnknown;
      throw error;
    } finally {
      progress.value = '';
    }
  }, '商品已发布');
}
</script>
<template>
  <header class="section-heading">
    <div>
      <span class="eyebrow">A NEW STORY</span>
      <h1>给闲置找个新主人</h1>
      <p class="muted">三张实拍，清楚介绍；交易与付款均为模拟。</p>
    </div>
    <RouterLink to="/my-products">我发布的</RouterLink>
  </header>
  <TaskFeedback
    :error="action.error.value"
    :notice="!saved ? '浏览器无法保存草稿，请保持此页打开。' : ''"
  />
  <div v-if="uncertain" class="notice">
    <b>商品提交结果待确认</b>
    <p>输入与上传编号仍保留。请先查看我发布的，确认服务端未创建商品后再重试。</p>
    <RouterLink to="/my-products" target="_blank">在新标签查看我发布的</RouterLink
    ><label class="checkbox-line"
      ><input type="checkbox" @change="uncertain = false" />我已核对，没有创建这件商品</label
    >
  </div>
  <form class="publish-layout" @submit.prevent="publish">
    <div class="form-stack">
      <section class="panel form-stack">
        <span class="eyebrow">01 · 基本信息</span>
        <h2>先说说它是什么</h2>
        <label
          >分类<select v-model="form.category">
            <option value="books">二手书</option>
            <option value="living">宿舍生活</option>
            <option value="sports">运动好物</option>
            <option value="electronics">电子产品</option>
          </select></label
        ><label
          >标题<ElInput
            v-model="form.title"
            required
            maxlength="80"
            placeholder="例如：数据结构 第二版，有少量笔记" /></label
        ><label
          >介绍<ElInput
            v-model="form.description"
            type="textarea"
            :rows="5"
            required
            maxlength="3000"
            show-word-limit
            placeholder="介绍使用情况、缺陷与附件…"
        /></label>
      </section>
      <section class="panel">
        <span class="eyebrow">02 · 实拍照片</span>
        <h2>看见真实的好物</h2>
        <div class="upload-grid">
          <label v-for="angle in angles" :key="angle.key" class="upload-slot"
            ><b>{{ angle.label }}</b
            ><input
              type="file"
              accept="image/jpeg,image/png,image/webp"
              :multiple="angle.key === 'extra'"
              :required="angle.key !== 'extra'"
              @change="selectFiles($event, angle.key)"
            /><small>{{
              files[angle.key].map((file) => file.name).join('、') ||
              '请选择实拍图片，每张不超过 5MB'
            }}</small></label
          >
        </div>
      </section>
      <section class="panel form-stack">
        <span class="eyebrow">03 · 价格与成色</span>
        <div class="form-grid">
          <label
            >售价（元，免费送填 0）<input
              v-model="form.price"
              required
              inputmode="decimal" /></label
          ><label>原购买价（可选）<input v-model="form.original_price" inputmode="decimal" /></label
          ><label>购买时间（可选）<input v-model="form.bought" type="month" /></label
          ><label
            >成色<select v-model="form.condition">
              <option>正常使用痕迹</option>
              <option>近乎全新</option>
              <option>明显磨损，已说明</option>
            </select></label
          >
        </div>
      </section>
      <section class="panel">
        <label class="filter-control"
          >购买时间（可选）<input v-model="form.bought" type="month"
        /></label>
      </section>
      <section v-if="form.category === 'books'" class="panel form-stack">
        <span class="eyebrow">04 · 二手书信息</span>
        <div class="form-grid">
          <label
            v-for="field in [
              { key: 'edition', label: '版次' },
              { key: 'publisher', label: '出版社' },
              { key: 'author', label: '作者 / 编者' },
              { key: 'isbn', label: 'ISBN' },
              { key: 'notes', label: '笔记情况' },
              { key: 'missing', label: '缺页情况' },
              { key: 'accessories', label: '附件情况' },
              { key: 'course', label: '适用课程' },
            ]"
            :key="field.key"
            >{{ field.label
            }}<input
              v-model="form[/** @type {keyof typeof defaults} */ (field.key)]"
              maxlength="120"
          /></label>
        </div>
      </section>
      <section class="panel form-stack">
        <span class="eyebrow">05 · 交付约定</span
        ><label
          >交付方式<select v-model="form.delivery">
            <option value="both">自提 / 卖家送货均可</option>
            <option value="pickup">仅自提</option>
            <option value="delivery">仅卖家送货</option>
          </select></label
        ><label
          >公共交付地点<input
            v-model="form.region"
            list="campus-buildings"
            required
            maxlength="80"
            placeholder="例如：图书馆门口" /><datalist id="campus-buildings">
            <option
              v-for="building in buildings"
              :key="building"
              :value="building"
            /></datalist></label
        ><label>送货费（元）<input v-model="form.delivery_fee" inputmode="decimal" /></label>
        <p class="muted">请使用公共碰面点，不填写宿舍门牌。同卖家合并送货费按最高一件收取。</p>
      </section>
      <div class="publish-submit">
        <span role="status">{{
          progress || '当前信誉 ' + number(session.me, 'score') + '/100'
        }}</span
        ><AppButton
          type="submit"
          :loading="action.busy.value"
          :disabled="uncertain || number(session.me, 'score') < 60"
          >确认发布</AppButton
        >
      </div>
    </div>
    <aside class="panel publish-aside">
      <h2>让信息清楚一点</h2>
      <p>写明版次与缺陷，能少一次反复询问。</p>
      <p>照片文件仅保留在当前页面，刷新后需要重新选择。文字草稿按账号保存在本次浏览器会话。</p>
      <p>
        上传失败会保留输入与已成功上传编号。未完成发布的上传对象清理由原后端负责，本轮未新增对象清理接口。
      </p>
    </aside>
  </form>
</template>
