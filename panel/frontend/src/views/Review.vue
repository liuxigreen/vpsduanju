<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <div>
        <h1>待审核频道</h1>
        <p class="page-desc">筛选通过的频道 · 人工确认后收录到唯一数据库</p>
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btn btn-secondary btn-sm" @click="load" title="刷新">↻ 刷新</button>
        <button class="btn btn-primary btn-sm" @click="runScreening" title="运行筛选">🔍 运行筛选</button>
      </div>
    </div>

    <!-- Stats bar -->
    <div v-if="stats.total" style="margin-bottom:16px;display:flex;gap:12px;flex-wrap:wrap;">
      <span class="tag tag-accent">{{ stats.total }} 个待审核</span>
      <span v-for="(count, lang) in stats.byLang" :key="lang" class="tag tag-accent2">{{ lang }}: {{ count }}</span>
    </div>

    <!-- Language filter buttons -->
    <div style="margin-bottom:16px;display:flex;gap:6px;flex-wrap:wrap;">
      <button v-for="lang in langOptions" :key="lang" class="btn btn-sm"
        :style="filterLang === lang ? 'background:var(--accent);color:#fff;' : ''"
        @click="filterLang = lang; load(lang)">
        {{ lang }} <span v-if="langStats[lang]" style="opacity:0.6;font-size:10px;">({{ langStats[lang] }})</span>
      </button>
    </div>

    <!-- Bulk action buttons -->
    <div style="margin-bottom:16px;" v-if="selectedIds.size > 0">
      <button class="btn btn-sm" style="background:var(--success);color:#fff;" @click="approveSelected">✓ 确认收录 ({{ selectedIds.size }})</button>
      <button class="btn btn-sm" style="background:var(--danger);color:#fff;margin-left:8px;" @click="rejectSelected">✗ 拒绝 ({{ selectedIds.size }})</button>
    </div>

    <div v-if="!channels.length && !loading" class="empty-state">点击"运行筛选"开始</div>
    <div v-if="loading" class="empty-state">加载中...</div>

    <Transition name="fade">
      <div v-if="filtered.length">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
          <span style="font-size:12px;color:var(--text-muted);">显示 {{ filtered.length }} / {{ channels.length }} 个频道</span>
          <button class="btn btn-sm btn-secondary" @click="toggleAll">{{ allSelected ? '取消全选' : '全选' }}</button>
        </div>

        <!-- Grouped by language -->
        <div v-for="group in groupedChannels" :key="group.lang" style="margin-bottom:24px;">
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid var(--border);">
            <span style="font-size:14px;font-weight:700;color:var(--accent);">{{ langIcons[group.lang] || '🌏' }} {{ group.lang }}</span>
            <span style="font-size:11px;color:var(--text-muted);">({{ group.channels.length }} 个频道)</span>
            <button class="btn btn-sm" style="margin-left:auto;font-size:10px;padding:2px 8px;"
              @click="toggleGroup(group.channels)">
              {{ isGroupSelected(group.channels) ? '取消' : '全选' }}
            </button>
          </div>

          <div class="review-grid">
            <div v-for="c in group.channels" :key="c.channel_id" class="review-mini-card"
              :style="{ borderColor: selectedIds.has(c.channel_id) ? 'var(--accent)' : '' }">
              <!-- 缩略图 -->
              <a :href="safeChannelUrl(c.channel_id)" target="_blank" style="display:block;text-decoration:none;">
                <img v-if="c.videos?.[0]?.video_id" :src="'https://i.ytimg.com/vi/' + c.videos[0].video_id + '/mqdefault.jpg'"
                  style="width:100%;height:120px;object-fit:cover;border-radius:4px;margin-bottom:4px;"
                  @error="$event.target.style.display='none'" />
              </a>
              <div style="display:flex;align-items:center;gap:6px;">
                <input type="checkbox" :checked="selectedIds.has(c.channel_id)" @click.stop @change="toggleSelect(c.channel_id)" style="flex-shrink:0;" />
                <div style="flex:1;min-width:0;">
                  <a :href="safeChannelUrl(c.channel_id)" target="_blank" @click.stop
                    style="font-size:12px;font-weight:600;color:var(--text);text-decoration:none;display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;"
                    :title="c.name">{{ c.name }}</a>
                </div>
              </div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px;font-size:10px;color:var(--text-dim);">
                <span style="color:var(--accent);">{{ formatSubs(c.subscribers || 0) }} 订阅</span>
                <span>{{ countryNames[c.country] || c.country || '-' }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { api, apiPost } from '../api/index.js'
import { showLoading, hideLoading, showToast } from '../stores/store.js'
import { formatSubs, safeChannelUrl } from '../utils.js'

const langOptions = ['印尼', '土耳其', '德语', '日语', '繁中', '英文', '葡萄牙', '西语']
const langIcons = { '印尼': '🇮🇩', '土耳其': '🇹🇷', '德语': '🇩🇪', '日语': '🇯🇵', '繁中': '🇹🇼', '英文': '🇺🇸', '葡萄牙': '🇧🇷', '西语': '🇪🇸' }
const countryNames = { US: '美国', ID: '印尼', TW: '台湾', JP: '日本', ES: '西班牙', SG: '新加坡', HK: '香港', PT: '葡萄牙', CA: '加拿大', GB: '英国', BR: '巴西', MX: '墨西哥', AU: '澳洲', CN: '中国', TR: '土耳其', DE: '德国' }

const loading = ref(false)
const channels = ref([])
const filterLang = ref('印尼')
const selectedIds = reactive(new Set())
const langStats = ref({})

const filtered = computed(() => channels.value)

const groupedChannels = computed(() => {
  const map = {}
  filtered.value.forEach(c => {
    const lang = c.language || '其他'
    if (!map[lang]) map[lang] = []
    map[lang].push(c)
  })
  // Sort groups: keep langOptions order first, then others
  const order = langOptions.filter(l => l !== 'all')
  const groups = Object.entries(map).map(([lang, chs]) => ({ lang, channels: chs }))
  groups.sort((a, b) => {
    const ia = order.indexOf(a.lang)
    const ib = order.indexOf(b.lang)
    return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
  })
  return groups
})

const stats = computed(() => {
  const byLang = langStats.value
  const total = Object.values(byLang).reduce((a, b) => a + b, 0)
  return { total, byLang }
})

const allSelected = computed(() => filtered.value.length > 0 && filtered.value.every(c => selectedIds.has(c.channel_id)))

function scoreColor(score) {
  if (!score && score !== 0) return '#95a5a6'
  if (score >= 70) return '#2ecc71'
  if (score >= 50) return '#f39c12'
  return '#95a5a6'
}

function toggleSelect(id) {
  if (selectedIds.has(id)) selectedIds.delete(id)
  else selectedIds.add(id)
}

function toggleAll() {
  if (allSelected.value) {
    filtered.value.forEach(c => selectedIds.delete(c.channel_id))
  } else {
    filtered.value.forEach(c => selectedIds.add(c.channel_id))
  }
}

function isGroupSelected(channels) {
  return channels.length > 0 && channels.every(c => selectedIds.has(c.channel_id))
}

function toggleGroup(channels) {
  if (isGroupSelected(channels)) {
    channels.forEach(c => selectedIds.delete(c.channel_id))
  } else {
    channels.forEach(c => selectedIds.add(c.channel_id))
  }
}

async function load(lang) {
  const target = lang || filterLang.value
  loading.value = true
  try {
    const d = await api('/review?lang=' + encodeURIComponent(target))
    channels.value = d.channels || []
    langStats.value = d.stats || {}
  } catch (err) { console.error('[Review]', err) }
  finally { loading.value = false }
}

async function runScreening() {
  showLoading('运行筛选中…')
  try {
    await apiPost('/review/run', {})
    await load()
    showToast('筛选完成', 'success')
  } catch (err) { console.error('[Review]', err) }
  finally { hideLoading() }
}

async function approveSelected() {
  if (!selectedIds.size) return
  showLoading('收录中…')
  try {
    await apiPost('/review/approve', { channel_ids: [...selectedIds] })
    selectedIds.clear()
    await load()
    showToast('收录成功', 'success')
  } catch (err) { console.error('[Review]', err) }
  finally { hideLoading() }
}

async function rejectSelected() {
  if (!selectedIds.size) return
  showLoading('拒绝中…')
  try {
    await apiPost('/review/reject', { channel_ids: [...selectedIds] })
    selectedIds.clear()
    await load()
    showToast('已拒绝', 'success')
  } catch (err) { console.error('[Review]', err) }
  finally { hideLoading() }
}

onMounted(() => { load() })
</script>
