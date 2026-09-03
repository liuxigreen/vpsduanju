<template>
  <div>
    <div class="card" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
      <div>
        <h2 style="margin:0;font-size:16px;">🕸 竞品知识图谱</h2>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">
          题材 × 语种 × 频道 × 钩子 关联网络 · 数据截至 {{ graph?.generated_at || '…' }}
        </div>
      </div>
      <div v-if="graph?.stats" style="display:flex;gap:14px;font-size:12px;">
        <span>📺 {{ graph.stats.channels }} 频道<span v-if="graph.stats.evidenced_channels" style="color:var(--text-muted);font-size:10px;">（实证{{ graph.stats.evidenced_channels }}）</span></span>
        <span style="color:#4ecdc4;">🎭 {{ graph.stats.genres }} 题材</span>
        <span>🌐 {{ graph.stats.languages }} 语种</span>
        <span>🪝 {{ graph.stats.hooks }} 钩子</span>
      </div>
      <button class="btn btn-sm" @click="load" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
    </div>

    <div v-if="error" class="empty-state"><div class="icon">⚠</div><div>{{ error }}</div></div>

    <div v-if="graph && !error" style="display:grid;grid-template-columns:minmax(0,3fr) minmax(260px,2fr);gap:16px;margin-top:16px;">
      <!-- 题材×语种 热力矩阵 -->
      <div class="card">
        <h3 style="margin:0 0 4px;font-size:14px;">🔥 题材 × 语种 热力矩阵</h3>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;">格子 = 字幕实证视频数 · 越亮内容越多 · 悬停看中位播放 · 点击行看详情</div>
        <div style="overflow-x:auto;">
          <table style="border-collapse:collapse;font-size:11px;min-width:100%;">
            <thead>
              <tr>
                <th style="text-align:left;padding:4px 8px;position:sticky;left:0;background:var(--bg-elevated);">题材</th>
                <th v-for="l in matrixLangs" :key="l" style="padding:4px 6px;color:var(--text-muted);">{{ l }}</th>
                <th style="padding:4px 8px;color:#4ecdc4;">合计动量/天</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in matrixRows" :key="row.genre" @click="selectGenre(row.genre)"
                  style="cursor:pointer;" @mouseenter="$event.currentTarget.style.background='var(--bg-elevated)'" @mouseleave="$event.currentTarget.style.background=''">
                <td style="padding:4px 8px;position:sticky;left:0;background:inherit;font-weight:bold;white-space:nowrap;">
                  {{ row.genre }}
                  <span v-if="row.rank.avg >= 5500 && row.rank.channels <= 60" style="font-size:9px;color:#3498db;margin-left:2px;" title="单频道效率高且玩家不多">🌊</span>
                  <span v-else-if="row.rank.channels >= 150" style="font-size:9px;color:#e74c3c;margin-left:2px;" title="频道数超150,竞争激烈">🔥</span>
                </td>
                <td v-for="l in matrixLangs" :key="l" style="padding:3px 6px;">
                  <span v-if="cell(row.genre, l)" :style="cellStyle(row.genre, l)" :title="`${row.genre}×${l}: 实证${cell(row.genre,l)[0]}条 · 中位播放${(cell(row.genre,l)[1]||0).toLocaleString()}`">{{ cell(row.genre, l)[0] }}</span>
                  <span v-else style="color:var(--text-dim);opacity:0.35;">·</span>
                </td>
                <td style="padding:4px 8px;color:#2ecc71;font-weight:bold;white-space:nowrap;">{{ fmt(row.rank.momentum_total) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 题材效率榜 -->
      <div class="card">
        <h3 style="margin:0 0 4px;font-size:14px;">💎 题材效率榜</h3>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;">单频道平均播放动量 · 高=蓝海机会 · 🌊=效率≥5500且玩家≤60</div>
        <div v-for="r in genreRank" :key="r.genre" @click="selectGenre(r.genre)"
             style="display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;cursor:pointer;"
             @mouseenter="$event.currentTarget.style.background='var(--bg-elevated)'" @mouseleave="$event.currentTarget.style.background=''">
          <div style="flex:1;min-width:0;">
            <div style="font-size:12px;">{{ r.genre }} <span v-if="r.momentum_avg>=5500 && r.channels<=60" style="font-size:9px;color:#3498db;">🌊</span></div>
            <div style="font-size:9px;color:var(--text-dim);">{{ r.channels }}频道 · 主打 {{ r.top_languages.join('/') }}<span v-if="r.subtitle_n" style="color:#4ecdc4;"> · 实证{{ r.subtitle_n }}条 中位{{ fmt(r.median_views) }}</span></div>
            <div style="height:3px;background:var(--bg-elevated);border-radius:2px;margin-top:2px;">
              <div :style="{ width: Math.min(r.momentum_avg / effMax * 100, 100) + '%', height: '100%', borderRadius: '2px', background: r.momentum_avg >= 5500 ? '#3498db' : '#4ecdc4' }"></div>
            </div>
          </div>
          <div style="text-align:right;flex-shrink:0;">
            <div style="font-size:12px;font-weight:bold;" :style="{ color: r.momentum_avg >= 5500 ? '#3498db' : '#4ecdc4' }">{{ fmt(r.momentum_avg) }}</div>
            <div style="font-size:9px;color:var(--text-muted);">均/天</div>
          </div>
        </div>
      </div>
    </div>

    <!-- 题材详情弹层 -->
    <div v-if="selected" class="modal-mask" @click.self="selected = null">
      <div class="modal" style="max-width:720px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3 style="margin:0;font-size:15px;">🎭 {{ selected.genre }} · {{ selected.channels }} 个频道</h3>
          <button class="btn btn-sm" @click="selected = null">✕</button>
        </div>
        <div style="display:flex;gap:16px;font-size:12px;margin-bottom:12px;flex-wrap:wrap;">
          <span>动量合计 <b style="color:#2ecc71;">{{ fmt(selected.momentum_total) }}/天</b></span>
          <span>单频道均 <b style="color:#3498db;">{{ fmt(selected.momentum_avg) }}/天</b></span>
          <span>订阅涨速合计 <b style="color:#e67e22;">+{{ fmt(selected.subs_velocity_total) }}/周</b></span>
          <span v-if="selected.subtitle_n">字幕实证 <b style="color:#4ecdc4;">{{ selected.subtitle_n }} 条</b> · 中位播放 <b style="color:#4ecdc4;">{{ fmt(selected.median_views) }}</b></span>
          <span>主语种 <b>{{ selected.top_languages.join(' / ') }}</b></span>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:12px;">
          <thead>
            <tr style="color:var(--text-muted);font-size:10px;">
              <th style="text-align:left;padding:4px;">频道</th>
              <th style="padding:4px;">语种</th>
              <th style="padding:4px;">订阅</th>
              <th style="padding:4px;">动量/天</th>
              <th style="padding:4px;">涨速/周</th>
              <th style="padding:4px;"></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in selected.top_channels" :key="c.channel_id" style="border-top:1px solid var(--border);">
              <td style="padding:5px 4px;">{{ c.name }}</td>
              <td style="padding:5px 4px;text-align:center;color:var(--text-muted);">{{ c.language }}</td>
              <td style="padding:5px 4px;text-align:center;">{{ fmtSubs(c.subscribers || 0) }}</td>
              <td style="padding:5px 4px;text-align:center;color:#2ecc71;font-weight:bold;">{{ fmt(c.momentum) }}</td>
              <td style="padding:5px 4px;text-align:center;color:#e67e22;">+{{ fmt(c.subs_velocity) }}</td>
              <td style="padding:5px 4px;text-align:center;"><a :href="c.url" target="_blank" style="color:#4ecdc4;font-size:11px;">▶</a></td>
            </tr>
          </tbody>
        </table>
        <div style="font-size:10px;color:var(--text-muted);margin-top:8px;">动量 = 近30天发布视频日均播放 · 涨速 = ≥14天窗口订阅周增量 · 点击 ▶ 跳转频道</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api/index.js'

const route = useRoute()

const graph = ref(null)
const loading = ref(false)
const error = ref('')
const selected = ref(null)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const d = await api('/knowledge-graph')
    if (d.error) { error.value = d.error; graph.value = null }
    else graph.value = d
  } catch (e) {
    error.value = '加载失败: ' + (e.message || e)
  } finally {
    loading.value = false
  }
}

const matrixLangs = computed(() => (graph.value?.matrix?.languages || []).slice(0, 7))
const genreRank = computed(() => graph.value?.genre_rank || [])
const effMax = computed(() => Math.max(1, ...genreRank.value.map(r => r.momentum_avg)))

// 每行的题材统计(含avg/channels) + 矩阵行
const rankByGenre = computed(() => {
  const m = {}
  genreRank.value.forEach(r => { m[r.genre] = r })
  return m
})
const matrixRows = computed(() =>
  genreRank.value.map(r => ({ genre: r.genre, rank: r }))
)

function cell(genre, lang) {
  const c = graph.value?.matrix?.cells
  if (!c) return null
  for (const row of c) {
    if (row[0] === genre && row[1] === lang) return [row[2], row[3]]
  }
  return null
}

function cellStyle(genre, lang) {
  const v = cell(genre, lang)
  if (!v) return {}
  // 列内归一化热度
  const langIdx = matrixLangs.value.indexOf(lang)
  let max = 1
  for (const row of graph.value.matrix.cells) {
    if (row[1] === matrixLangs.value[langIdx]) max = Math.max(max, row[2])
  }
  const heat = Math.min(v[0] / max, 1)
  return {
    display: 'inline-block', minWidth: '26px', textAlign: 'center',
    padding: '2px 5px', borderRadius: '4px',
    background: `rgba(78,205,196,${(0.08 + heat * 0.55).toFixed(2)})`,
    color: heat > 0.55 ? '#fff' : 'var(--text)',
    fontWeight: heat > 0.55 ? 'bold' : 'normal',
  }
}

function selectGenre(genre) {
  selected.value = rankByGenre.value[genre] || null
}

function fmt(n) { return (n || 0).toLocaleString() }
function fmtSubs(n) {
  n = n || 0
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
  if (n >= 1e3) return Math.round(n / 1e3) + 'K'
  return n
}

onMounted(async () => {
  await load()
  // 深链接：蓝海雷达点击跳转 /knowledge-graph?genre=xx → 自动打开该题材详情
  if (route.query.genre) selectGenre(String(route.query.genre))
})
</script>
