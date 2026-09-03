<template>
  <div>
    <div class="card" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
      <div>
        <h2 style="margin:0;font-size:16px;">🌊 蓝海雷达</h2>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">
          题材 × 语种 · 字幕实证（高播放=需求 · 实证少=供给缺口）· 计算于 {{ data?.stats?.generated_at || '…' }}
        </div>
      </div>
      <div v-if="data?.stats" style="display:flex;gap:14px;font-size:12px;">
        <span style="color:#3498db;">🟢 蓝海 {{ data.stats.quadrant_counts.blue_ocean }}</span>
        <span style="color:#f1c40f;">🟡 热战 {{ data.stats.quadrant_counts.hot_war }}</span>
        <span style="color:var(--text-muted);">⬜ 荒漠 {{ data.stats.quadrant_counts.desert }}</span>
        <span style="color:#e74c3c;">🔴 红海 {{ data.stats.quadrant_counts.red_sea }}</span>
      </div>
      <button class="btn btn-sm" @click="load" :disabled="loading">{{ loading ? '加载中…' : '↻ 刷新' }}</button>
    </div>

    <div v-if="error" class="empty-state"><div class="icon">⚠</div><div>{{ error }}</div></div>

    <div v-if="data && !error">
      <!-- 四象限散点 -->
      <div class="card" style="margin-top:16px;">
        <h3 style="margin:0 0 4px;font-size:14px;">🧭 四象限分布</h3>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">
          横轴=实证视频数(供给, log) · 纵轴=中位播放(需求) · 虚线=中位数分界 · 点大小=样本量 · 悬停看明细
        </div>
        <svg :viewBox="`0 0 ${W} ${H}`" style="width:100%;height:auto;display:block;">
          <!-- 象限底色 -->
          <rect :x="PAD" :y="PAD" :width="splitX-PAD" :height="splitY-PAD" fill="rgba(52,152,219,0.07)"/>
          <rect :x="splitX" :y="PAD" :width="W-PAD-splitX" :height="splitY-PAD" fill="rgba(241,196,15,0.06)"/>
          <rect :x="PAD" :y="splitY" :width="splitX-PAD" :height="H-PAD-splitY" fill="rgba(149,165,166,0.05)"/>
          <rect :x="splitX" :y="splitY" :width="W-PAD-splitX" :height="H-PAD-splitY" fill="rgba(231,76,60,0.06)"/>
          <!-- 分界线 -->
          <line :x1="splitX" :y1="PAD" :x2="splitX" :y2="H-PAD" stroke="var(--border,#555)" stroke-dasharray="4 4" stroke-width="1"/>
          <line :x1="PAD" :y1="splitY" :x2="W-PAD" :y2="splitY" stroke="var(--border,#555)" stroke-dasharray="4 4" stroke-width="1"/>
          <!-- 象限标签 -->
          <text :x="PAD+8" :y="PAD+16" fill="#3498db" font-size="12" font-weight="bold">🟢 蓝海 · 进场</text>
          <text :x="W-PAD-8" :y="PAD+16" fill="#f1c40f" font-size="12" font-weight="bold" text-anchor="end">🟡 热战 · 拼执行</text>
          <text :x="PAD+8" :y="H-PAD-8" fill="#95a5a6" font-size="12">⬜ 荒漠 · 观察</text>
          <text :x="W-PAD-8" :y="H-PAD-8" fill="#e74c3c" font-size="12" text-anchor="end">🔴 红海 · 规避</text>
          <!-- 轴标注 -->
          <text :x="W/2" :y="H-6" fill="var(--text-muted)" font-size="10" text-anchor="middle">实证视频数（供给）→</text>
          <!-- 点 -->
          <circle v-for="pt in points" :key="pt.key"
                  :cx="pt.x" :cy="pt.y" :r="pt.r" :fill="pt.color" fill-opacity="0.75"
                  stroke="rgba(255,255,255,0.25)" stroke-width="0.5" style="cursor:pointer;"
                  @mouseenter="hover = pt" @mouseleave="hover = null" @click="pick(pt)">
            <title>{{ pt.genre }}×{{ pt.language }}: 实证{{ pt.n }}条 · 中位播放{{ pt.mv.toLocaleString() }}{{ pt.mainline ? ' · 主线' + pt.mainline : '' }}</title>
          </circle>
          <!-- 蓝海/热战头部点标名 -->
          <text v-for="pt in labeled" :key="'t'+pt.key" :x="pt.x+pt.r+3" :y="pt.y+3"
                :fill="pt.color" font-size="9" style="pointer-events:none;">{{ pt.genre }}×{{ pt.language }}</text>
        </svg>
        <div v-if="hover" style="font-size:11px;color:var(--text-muted);margin-top:4px;">
          {{ hover.genre }}<span v-if="hover.axis" style="color:#3498db;">（{{ hover.axis }}轴）</span>×{{ hover.language }} — 实证 {{ hover.n }} 条 · 中位播放 {{ hover.mv.toLocaleString() }}<span v-if="hover.mainline && hover.mainline !== '其他'" style="color:#e67e22;"> · 主线{{ hover.mainline }}</span> · {{ hover.quadrantLabel }}
        </div>
      </div>

      <!-- 蓝海外向榜单 -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:16px;">
        <div class="card">
          <h3 style="margin:0 0 8px;font-size:14px;color:#3498db;">🟢 蓝海区 Top10（高播放 · 低供给）</h3>
          <table style="width:100%;border-collapse:collapse;font-size:12px;">
            <thead><tr style="color:var(--text-muted);font-size:10px;">
              <th style="text-align:left;padding:4px;">题材×语种</th><th style="padding:4px;">主线</th><th style="padding:4px;">中位播放</th><th style="padding:4px;">实证数</th>
            </tr></thead>
            <tbody>
              <tr v-for="i in data.quadrant.blue_ocean.slice(0,10)" :key="i.genre+i.language" style="border-top:1px solid var(--border);cursor:pointer;" @click="pick(i,'blue_ocean')">
                <td style="padding:5px 4px;">{{ i.genre }} × {{ i.language }}</td>
                <td style="padding:5px 4px;text-align:center;"><span v-if="i.mainline && i.mainline !== '其他'" :style="mainlineChip(i.mainline)">{{ i.mainline }}</span><span v-else style="color:var(--text-dim);">·</span></td>
                <td style="padding:5px 4px;text-align:center;color:#3498db;font-weight:bold;">{{ fmt(i.median_views) }}</td>
                <td style="padding:5px 4px;text-align:center;color:var(--text-muted);">{{ i.n }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!data.quadrant.blue_ocean.length" class="empty-state" style="padding:16px;"><div>当前无蓝海信号</div></div>
        </div>
        <div class="card">
          <h3 style="margin:0 0 8px;font-size:14px;color:#e74c3c;">🔴 红海区 Top10（低播放 · 高供给 → 规避）</h3>
          <table style="width:100%;border-collapse:collapse;font-size:12px;">
            <thead><tr style="color:var(--text-muted);font-size:10px;">
              <th style="text-align:left;padding:4px;">题材×语种</th><th style="padding:4px;">主线</th><th style="padding:4px;">中位播放</th><th style="padding:4px;">实证数</th>
            </tr></thead>
            <tbody>
              <tr v-for="i in data.quadrant.red_sea.slice(0,10)" :key="i.genre+i.language" style="border-top:1px solid var(--border);cursor:pointer;" @click="pick(i,'red_sea')">
                <td style="padding:5px 4px;">{{ i.genre }} × {{ i.language }}</td>
                <td style="padding:5px 4px;text-align:center;"><span v-if="i.mainline && i.mainline !== '其他'" :style="mainlineChip(i.mainline)">{{ i.mainline }}</span><span v-else style="color:var(--text-dim);">·</span></td>
                <td style="padding:5px 4px;text-align:center;color:#e74c3c;font-weight:bold;">{{ fmt(i.median_views) }}</td>
                <td style="padding:5px 4px;text-align:center;color:var(--text-muted);">{{ i.n }}</td>
              </tr>
            </tbody>
          </table>
          <div v-if="!data.quadrant.red_sea.length" class="empty-state" style="padding:16px;"><div>无红海信号</div></div>
        </div>
      </div>

      <!-- 热战/荒漠折叠 -->
      <div class="card" style="margin-top:16px;">
        <h3 style="margin:0 0 8px;font-size:14px;cursor:pointer;" @click="showRest=!showRest">
          {{ showRest ? '▾' : '▸' }} 🟡 热战区（{{ data.quadrant.hot_war.length }}）· ⬜ 荒漠（{{ data.quadrant.desert.length }}）
        </h3>
        <div v-if="showRest" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
          <div>
            <div v-for="i in data.quadrant.hot_war" :key="'h'+i.genre+i.language"
                 style="display:flex;justify-content:space-between;padding:3px 4px;font-size:11px;border-top:1px solid var(--border);cursor:pointer;"
                 @click="pick(i,'hot_war')">
              <span>{{ i.genre }} × {{ i.language }}</span>
              <span style="color:#f1c40f;">{{ fmt(i.median_views) }} · {{ i.n }}条</span>
            </div>
          </div>
          <div>
            <div v-for="i in data.quadrant.desert" :key="'d'+i.genre+i.language"
                 style="display:flex;justify-content:space-between;padding:3px 4px;font-size:11px;border-top:1px solid var(--border);cursor:pointer;"
                 @click="pick(i,'desert')">
              <span>{{ i.genre }} × {{ i.language }}</span>
              <span style="color:var(--text-muted);">{{ fmt(i.median_views) }} · {{ i.n }}条</span>
            </div>
          </div>
        </div>
      </div>

      <div style="font-size:10px;color:var(--text-muted);margin-top:10px;">
        象限分界 = 全部有效 cell（实证 n≥{{ data.stats.min_n }}）的中位数 · 需求侧看中位播放（抗爆款拉高）· 供给侧看实证视频数 · 数据源: 4497 条竞品视频字幕分析
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api/index.js'

const router = useRouter()
const data = ref(null)
const loading = ref(false)
const error = ref('')
const hover = ref(null)
const showRest = ref(false)

async function load() {
  loading.value = true
  error.value = ''
  try {
    const d = await api('/blue-ocean')
    if (d.error) { error.value = d.error; data.value = null }
    else data.value = d
  } catch (e) {
    error.value = '加载失败: ' + (e.message || e)
  } finally {
    loading.value = false
  }
}

// ── 散点图 ──
const W = 900, H = 460, PAD = 36
const QCOLOR = { blue_ocean: '#3498db', hot_war: '#f1c40f', desert: '#95a5a6', red_sea: '#e74c3c' }
const QLABEL = { blue_ocean: '蓝海区 → 进场', hot_war: '热战区 → 拼执行', desert: '荒漠 → 观察', red_sea: '红海区 → 规避' }

const allPoints = computed(() => {
  if (!data.value) return []
  const out = []
  for (const [q, items] of Object.entries(data.value.quadrant)) {
    for (const i of items) {
      out.push({ ...i, mv: i.median_views, quadrant: q, color: QCOLOR[q], quadrantLabel: QLABEL[q], key: `${i.genre}|${i.language}` })
    }
  }
  return out
})

const scaleXMax = computed(() => Math.max(10, ...allPoints.value.map(p => p.n)))
const scaleYMax = computed(() => Math.max(1000, ...allPoints.value.map(p => p.mv)))
const logMaxN = computed(() => Math.log10(scaleXMax.value))
const logMaxV = computed(() => Math.log10(scaleYMax.value))

function xOf(n) { return PAD + (Math.log10(Math.max(1, n)) / logMaxN.value) * (W - 2 * PAD) }
function yOf(v) { return H - PAD - (Math.log10(Math.max(1, v)) / logMaxV.value) * (H - 2 * PAD) }

const splitX = computed(() => xOf(data.value?.stats?.median_n || 1))
const splitY = computed(() => yOf(data.value?.stats?.median_median_views || 1))

const points = computed(() => allPoints.value.map(p => ({
  ...p, x: xOf(p.n), y: yOf(p.mv), r: Math.min(14, 3 + Math.sqrt(p.n) * 0.6),
})))

// 只给蓝海+热战前5标名，避免文字打架
const labeled = computed(() => {
  const blue = points.value.filter(p => p.quadrant === 'blue_ocean').slice(0, 5)
  const hot = points.value.filter(p => p.quadrant === 'hot_war').sort((a, b) => b.mv - a.mv).slice(0, 3)
  return [...blue, ...hot]
})

// 主线四分类配色，与 KnowledgeGraph/后端 mainline_rules 对齐
const MAINLINE_COLORS = { '感情': '#e74c3c', '家庭': '#f1c40f', '个人': '#2ecc71', '职场': '#3498db', '其他': '#7f8c8d' }
function mainlineChip(k) {
  const c = MAINLINE_COLORS[k] || '#7f8c8d'
  return { padding: '0 6px', borderRadius: '4px', background: c + '22', color: c, fontSize: '10px', whiteSpace: 'nowrap' }
}

// 点击 → 跳图谱页并打开该题材详情
function pick(i, q) {
  router.push({ path: '/knowledge-graph', query: { genre: i.genre } })
}

function fmt(n) {
  n = n || 0
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

onMounted(load)
</script>
