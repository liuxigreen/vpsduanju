<template>
  <div>
    <div class="card" style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;">
      <div>
        <h2 style="margin:0;font-size:16px;">🕸 竞品知识图谱</h2>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">
          题材 × 语种 × 频道 × 钩子 × 主线 关联网络 · 数据截至 {{ graph?.generated_at || '…' }}
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

    <BlueOceanView style="margin-top:14px;" />


    <div v-if="graph && !error" style="display:grid;grid-template-columns:minmax(0,3fr) minmax(260px,2fr);gap:16px;margin-top:16px;">
      <!-- 题材×语种 热力矩阵 -->
      <div class="card">
        <h3 style="margin:0 0 4px;font-size:14px;">🔥 题材 × 语种 热力矩阵</h3>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;">格子 = 字幕实证视频数 · 越亮内容越多 · 点题材名看详情 · 点格子看该题材×语种的视频列表</div>
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
              <tr v-for="row in matrixRows" :key="row.genre"
                  @mouseenter="$event.currentTarget.style.background='var(--bg-elevated)'" @mouseleave="$event.currentTarget.style.background=''">
                <td @click="selectGenre(row.genre)" style="padding:4px 8px;position:sticky;left:0;background:inherit;font-weight:bold;white-space:nowrap;cursor:pointer;" title="看题材详情">
                  {{ row.genre }}
                  <span v-if="row.rank.avg >= 5500 && row.rank.channels <= 60" style="font-size:9px;color:#3498db;margin-left:2px;" title="单频道效率高且玩家不多">🌊</span>
                  <span v-else-if="row.rank.channels >= 150" style="font-size:9px;color:#e74c3c;margin-left:2px;" title="频道数超150,竞争激烈">🔥</span>
                </td>
                <td v-for="l in matrixLangs" :key="l" style="padding:3px 6px;">
                  <span v-if="cell(row.genre, l)" :style="[cellStyle(row.genre, l), { cursor: 'pointer' }]" @click.stop="gotoLibrary(row.genre, l)" :title="`${row.genre}×${l}: 实证${cell(row.genre,l)[0]}条 · 中位播放${(cell(row.genre,l)[1]||0).toLocaleString()}${cell(row.genre,l)[2] ? ' · 主线' + cell(row.genre,l)[2] : ''} · 点击看视频列表`">{{ cell(row.genre, l)[0] }}</span>
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
        <h3 style="margin:0 0 4px;font-size:14px;">💎 题材动量榜</h3>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;">单频道平均播放动量 · 高=蓝海机会 · 🌊=效率≥5500且玩家≤60</div>
        <div v-for="r in genreRank" :key="r.genre" @click="selectGenre(r.genre)"
             style="display:flex;align-items:center;gap:8px;padding:5px 6px;border-radius:6px;cursor:pointer;"
             @mouseenter="$event.currentTarget.style.background='var(--bg-elevated)'" @mouseleave="$event.currentTarget.style.background=''">
          <div style="flex:1;min-width:0;">
            <div style="font-size:12px;">{{ r.genre }}
              <span v-if="r.axis" style="font-size:9px;padding:0 4px;border-radius:3px;background:rgba(52,152,219,0.15);color:#3498db;" :title="r.axis + '轴（设定=世界观，母题=故事引擎）'">{{ r.axis }}</span>
              <span v-if="topMainline(r)" style="font-size:9px;color:#e67e22;">{{ topMainline(r) }}线</span>
              <span v-if="r.momentum_avg>=5500 && r.channels<=60" style="font-size:9px;color:#3498db;">🌊</span>
            </div>
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

      <!-- 钩子效果区（左列第二行，填补热力图下方空白） -->
      <div class="card" v-if="hookRows.length" style="grid-column:1 / 2;">
        <h3 style="margin:0 0 4px;font-size:14px;">🪝 开场钩子 × 效果</h3>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:10px;">类型 = 前3分钟主导钩子 · 秒 = 钩子出现时点分布 · 数字来自字幕实证（原句回查），样本 n 越大越稳，⚠️样本少仅供参考</div>
        <div v-for="h in hookRows" :key="h.name" style="display:flex;align-items:center;gap:10px;padding:4px 2px;">
          <div style="width:76px;flex-shrink:0;font-size:12px;font-weight:bold;">{{ h.name }}</div>
          <div style="flex:1;min-width:0;">
            <div style="height:6px;background:var(--bg-elevated);border-radius:3px;">
              <div :style="{ width: Math.max(h.median / hookMaxMedian * 100, 2) + '%', height: '100%', borderRadius: '3px', background: 'linear-gradient(90deg,#e67e22,#f39c12)' }"></div>
            </div>
            <div style="font-size:9px;color:var(--text-dim);margin-top:2px;">{{ h.langs }} · {{ h.secLabel }}</div>
          </div>
          <div style="text-align:right;flex-shrink:0;width:118px;">
            <div style="font-size:12px;font-weight:bold;color:#e67e22;">{{ fmt(h.median) }}<span v-if="h.thin" title="样本<200，数字仅供参考" style="font-size:9px;color:var(--text-dim);"> ⚠️样本少</span></div>
            <div style="font-size:9px;color:var(--text-muted);">中位播放 · {{ h.n }}条</div>
          </div>
        </div>
      </div>
      <!-- 词表健康 -->
      <div class="card" v-if="vocab" style="grid-column:2 / 3;">
        <h3 style="margin:0 0 4px;font-size:14px;">📖 题材命名一致性 <span style="font-size:10px;color:var(--text-muted);">v{{ vocab.vocab_version }}</span></h3>
        <div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">AI 分析里出现过的 {{ vocab.distinct_labels }} 种题材叫法，已归入 {{ vocab.vocab_targets }} 类，覆盖 <b style="color:#2ecc71;">{{ Math.round((vocab.known_share || 0) * 100) }}%</b>。下面是还没归类的叫法，你拍板后我会并进词表：</div>
        <div style="display:flex;gap:5px;flex-wrap:wrap;">
          <span v-for="p in (vocab.pending || [])" :key="p.label"
                :title="'出现 ' + p.n + ' 条 · 样例: ' + p.sample" style="font-size:10.5px;background:rgba(243,156,18,0.1);color:#f39c12;padding:2px 8px;border-radius:4px;">{{ p.label }} ×{{ p.n }}</span>
          <span v-if="!(vocab.pending || []).length" style="font-size:10.5px;color:#2ecc71;">✅ 词表全覆盖</span>
        </div>
      </div>
    </div>

    <!-- 题材详情弹层 -->
    <div v-if="selected" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.85);z-index:1000;overflow-y:auto;padding:20px;" @click.self="selected = null">
      <div style="background:var(--bg-card,#16213e);border:1px solid var(--border,#2a2a4a);border-radius:12px;max-width:720px;margin:40px auto;padding:20px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3 style="margin:0;font-size:15px;">🎭 {{ selected.genre }}
            <span v-if="selected.axis" style="font-size:10px;font-weight:normal;padding:1px 6px;border-radius:4px;background:rgba(52,152,219,0.18);color:#3498db;margin-left:4px;">{{ selected.axis }}轴</span>
            · {{ selected.channels }} 个频道</h3>
          <button class="btn btn-sm" @click="selected = null">✕</button>
        </div>
        <div style="display:flex;gap:16px;font-size:12px;margin-bottom:8px;flex-wrap:wrap;">
          <span>动量合计 <b style="color:#2ecc71;">{{ fmt(selected.momentum_total) }}/天</b></span>
          <span>单频道均 <b style="color:#3498db;">{{ fmt(selected.momentum_avg) }}/天</b></span>
          <span>订阅涨速合计 <b style="color:#e67e22;">+{{ fmt(selected.subs_velocity_total) }}/周</b></span>
          <span v-if="selected.subtitle_n">字幕实证 <b style="color:#4ecdc4;">{{ selected.subtitle_n }} 条</b> · 中位播放 <b style="color:#4ecdc4;">{{ fmt(selected.median_views) }}</b></span>
          <span>主语种 <b>{{ selected.top_languages.join(' / ') }}</b></span>
        </div>
        <div v-if="selected.mainlines && selected.subtitle_n" style="display:flex;gap:6px;font-size:11px;margin-bottom:12px;flex-wrap:wrap;align-items:center;">
          <span style="color:var(--text-muted);font-size:10px;">内容主线</span>
          <span v-for="(n,k) in selected.mainlines" :key="k" :style="mainlineChip(k, n, selected.subtitle_n)">{{ k }} {{ Math.round(n / selected.subtitle_n * 100) }}%</span>
        </div>
        <div v-if="(selected.hooks || []).length" style="margin:0 0 12px;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:5px;">开场钩子构成（该题材实证视频怎么开场 · 条长 = 该钩子中位播放）</div>
          <div v-for="h in selected.hooks" :key="h.name" style="display:flex;align-items:center;gap:8px;margin-top:3px;">
            <div style="width:70px;font-size:11px;flex-shrink:0;">{{ h.name }}</div>
            <div style="flex:1;height:5px;background:var(--bg-elevated);border-radius:3px;">
              <div :style="{ width: Math.max(h.median_views / ((selected.hooks[0].median_views) || 1) * 100, 3) + '%', height: '100%', borderRadius: '3px', background: 'linear-gradient(90deg,#8e44ad,#c39bd3)' }"></div>
            </div>
            <div style="width:130px;text-align:right;font-size:9.5px;color:var(--text-muted);flex-shrink:0;">{{ h.n }}条 · 中位 {{ fmt(h.median_views) }}</div>
          </div>
        </div>
        <div v-if="(selected.subtypes || []).length" style="margin:0 0 12px;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:5px;">剧情模式链（L2 亚型 · 悬停看实证数与中位播放 · 点击进内容库）</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <span v-for="st in selected.subtypes" :key="st.name" @click="gotoLibrary(selected.genre)"
                  style="font-size:10.5px;background:rgba(46,204,113,0.1);color:#2ecc71;padding:2px 8px;border-radius:4px;cursor:pointer;"
                  :title="'实证 ' + st.n + ' 条 · 中位播放 ' + fmt(st.median_views)">{{ st.name }} ×{{ st.n }}</span>
          </div>
        </div>
        <div style="margin:0 0 12px;">
          <router-link :to="{ path: '/library', query: { genre: selected.genre } }" style="font-size:11px;color:#3498db;">📚 查看全部 {{ selected.subtitle_n || 0 }} 条实证视频（内容库过滤视图）→</router-link>
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

        <template v-if="selected.top_videos && selected.top_videos.length">
          <h4 style="margin:16px 0 6px;font-size:13px;">🎬 实证 Top{{ selected.top_videos.length }} 视频（按播放 · 含剧情模式链）</h4>
          <div v-for="(v,i) in selected.top_videos" :key="i" style="border:1px solid var(--border);border-radius:8px;padding:8px 10px;margin-bottom:6px;">
            <div style="display:flex;justify-content:space-between;gap:8px;align-items:baseline;">
              <div style="font-size:12px;font-weight:bold;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ i + 1 }}. {{ v.title }}</div>
              <div style="font-size:11px;color:#2ecc71;flex-shrink:0;">{{ fmt(v.views) }}</div>
            </div>
            <div style="display:flex;gap:6px;font-size:10px;margin-top:4px;flex-wrap:wrap;align-items:center;">
              <span v-if="v.hook" style="padding:1px 6px;border-radius:4px;background:rgba(230,126,34,0.15);color:#e67e22;">🪝 {{ v.hook }}</span>
              <span v-if="v.mainline && v.mainline !== '其他'" :style="mainlineChip(v.mainline, 1, 1)">{{ v.mainline }}线</span>
              <span style="color:var(--text-muted);">{{ v.language }}</span>
              <span style="color:var(--text-dim);">{{ v.channel }}</span>
            </div>
            <div v-if="v.synopsis" style="font-size:11px;color:var(--text-muted);margin-top:4px;line-height:1.5;">{{ v.synopsis }}</div>
          </div>
          <div style="font-size:10px;color:var(--text-muted);margin-top:4px;">🪝 = 开场钩子类型 · 主线 = 剧情核心场域 · 摘要 = 字幕实证的一句话剧情（含剧情模式链）</div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api/index.js'
import BlueOceanView from './BlueOcean.vue'

const route = useRoute()
const router = useRouter()

// 热力图格子/剧情模式链 → 内容库过滤视图
function gotoLibrary(genre, lang) {
  const q = { genre }
  if (lang) q.lang = lang
  router.push({ path: '/library', query: q })
}

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
    api('/vocab-governance').then(v => { vocab.value = v && !v.error ? v : null }).catch(() => {})
  } catch (e) {
    error.value = '加载失败: ' + (e.message || e)
  } finally {
    loading.value = false
  }
}

const matrixLangs = computed(() => (graph.value?.matrix?.languages || []).slice(0, 7))
const genreRank = computed(() => graph.value?.genre_rank || [])
const effMax = computed(() => Math.max(1, ...genreRank.value.map(r => r.momentum_avg)))

// 钩子效果行：类型/实证数/中位播放/主语种/出现时点分位（API 顶层 hooks，graph v2.2）
const hookRows = computed(() => {
  const hs = graph.value?.hooks || []
  return hs
    .map(h => ({
      name: h.label,
      n: h.metrics.subtitle_n || 0,
      thin: (h.metrics.subtitle_n || 0) < 200,
      median: h.metrics.median_views || 0,
      langs: (h.metrics.top_languages || []).slice(0, 3).join('/'),
      p25: h.metrics.sec_p25, p50: h.metrics.sec_median, p75: h.metrics.sec_p75,
      secLabel: h.metrics.sec_median != null
        ? `出现时点 ${h.metrics.sec_p25 ?? '–'}–${h.metrics.sec_p75 ?? '–'}s · 中位 ${h.metrics.sec_median}s`
        : '出现时点未标注',
    }))
    .sort((a, b) => b.n - a.n)
})
const hookMaxMedian = computed(() => Math.max(1, ...hookRows.value.map(h => h.median)))
const vocab = ref(null)


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
    if (row[0] === genre && row[1] === lang) return [row[2], row[3], row[4]]
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

// 主线四分类配色（感情/家庭/个人/职场），与后端 mainline_rules 对齐
const MAINLINE_COLORS = { '感情': '#e74c3c', '家庭': '#f1c40f', '个人': '#2ecc71', '职场': '#3498db', '其他': '#7f8c8d' }
function mainlineChip(k, n, total) {
  const c = MAINLINE_COLORS[k] || '#7f8c8d'
  const share = total ? n / total : 1
  return {
    padding: '1px 7px', borderRadius: '4px',
    background: c + '22', color: c,
    fontWeight: share >= 0.5 ? 'bold' : 'normal',
  }
}
function topMainline(r) {
  const m = r.mainlines || {}
  let best = '', bn = 0
  for (const k in m) { if (k !== '其他' && m[k] > bn) { best = k; bn = m[k] } }
  return best
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

// 已在图谱页时再次从蓝海跳转（同组件复用，onMounted不再触发）
watch(() => route.query.genre, (g) => { if (g) selectGenre(String(g)) })
</script>
