<template>
  <div>
    <h1>上架助手</h1>
    <p class="page-desc">输入剧名或剧情内容，一键生成标题、封面指令</p>

    <div class="card">
      <div class="input-group" style="margin-bottom:12px">
        <label>剧名 <span style="color:var(--text-dim);font-size:11px">（输入剧名自动从本地查找剧情，无需手动粘贴）</span></label>
        <input v-model="dramaName" type="text" placeholder="例如：锦医风华" />
      </div>
      <div class="input-group" style="margin-bottom:12px">
        <label>剧情内容 <span style="color:var(--text-dim);font-size:11px">（粘贴剧情介绍、分集大纲等，或输入剧名自动加载）</span></label>
        <textarea v-model="plotContent" rows="5" placeholder="粘贴剧情内容…"></textarea>
      </div>
      <div class="input-row">
        <div class="input-group" style="flex:1">
          <label>目标语言</label>
          <select v-model="region">
            <option v-for="r in regions" :key="r.value" :value="r.value">{{ r.label }}</option>
          </select>
        </div>
        <div class="input-group" style="flex:1">
          <label>题材方向 <span style="color:var(--text-dim);font-size:11px">（可选）</span></label>
          <input type="text" v-model="direction" placeholder="留空=自动，或填：家庭伦理,亲情" />
        </div>
      </div>
      <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;">
        <button class="btn btn-primary" :disabled="generating" @click="generateTitles">
          <span>📝</span> 一键生成标题（20个）
        </button>
        <button class="btn btn-secondary" :disabled="generating" @click="generateProposal">
          <span>✦</span> 一键生成上架方案
        </button>
        <span style="color:var(--text-dim);font-size:12px">🤖 duanju Agent · 标题约6秒 · 完整方案约30秒</span>
      </div>
    </div>

    <!-- Results -->
    <Transition name="fade">
      <div v-if="results">
        <!-- 返回历史按钮 -->
        <div v-if="viewingHistory" style="margin-bottom:16px">
          <button class="btn btn-secondary" @click="backToHistory">← 返回历史记录</button>
        </div>

        <!-- 20 Titles -->
        <div v-if="titles20.length" class="result-section">
          <h3>📝 生成标题（20个） <span v-if="distillInfo" style="font-size:12px;color:var(--text-dim)">蒸馏均值{{ distillInfo.avg_title_length }}字符 · 目标{{ distillInfo.target_length }}字符</span></h3>
          <div class="result-grid">
            <div v-for="(t, i) in titles20" :key="i" class="result-card fade-in" style="position:relative">
              <div class="rank" :class="i < 5 ? '' : i < 10 ? 'alt1' : 'alt2'">{{ i + 1 }}</div>
              <button class="copy-btn" @click="copy(t.title)">复制</button>
              <div class="result-title">{{ t.title }}</div>
              <div v-if="t.title_hashtags?.length" style="margin-top:4px">
                <span v-for="h in t.title_hashtags" :key="h" class="tag tag-accent">{{ h }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Titles (5) -->
        <div v-if="proposal.titles?.length" class="result-section">
          <h3>📝 推荐标题（5个，按评分排序）</h3>
          <div class="result-grid">
            <div v-for="(t, i) in proposal.titles" :key="i" class="result-card fade-in" style="position:relative">
              <div class="rank" :class="['', 'alt1', 'alt2'][i] || 'alt2'">{{ i + 1 }}</div>
              <button class="copy-btn" @click="copy(typeof t === 'string' ? t : t.title)">复制</button>
              <div class="result-title">
                {{ typeof t === 'string' ? t : t.title }}
                <span v-if="t.style" class="tag tag-accent2" style="margin-left:8px">{{ t.style }}</span>
              </div>
              <div v-if="t.title_hashtags?.length" style="margin:4px 0">
                <span v-for="h in t.title_hashtags" :key="h" class="tag tag-accent">{{ h }}</span>
              </div>
              <div v-if="t.score" class="result-score">评分: {{ typeof t.score === 'object' ? t.score.total : t.score }}</div>
              <div v-if="t.conflict_points?.length" class="result-meta">冲突点: {{ t.conflict_points.join(' · ') }}</div>
            </div>
          </div>
        </div>

        <!-- AI Covers -->
        <div v-if="proposal.ai_covers?.length" class="result-section">
          <h3>🎨 AI封面指令（中文）</h3>
          <div class="result-grid">
            <div v-for="(c, i) in proposal.ai_covers" :key="i" class="result-card fade-in" style="position:relative">
              <div class="rank">{{ i + 1 }}</div>
              <button class="copy-btn" @click="copy(c.instruction)">复制</button>
              <div class="result-title">{{ c.style || `方案 ${i+1}` }}</div>
              <div class="prompt-box">
                <div class="prompt-label">AI封面指令（中文）</div>
                <div class="prompt-text">{{ c.instruction }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Covers -->
        <div v-if="covers.length" class="result-section">
          <h3>🎨 封面指令</h3>
          <div class="result-grid">
            <div v-for="(c, i) in covers" :key="i" class="result-card fade-in" style="position:relative">
              <div class="rank" :class="['', 'alt1', 'alt2'][i] || 'alt2'">{{ i + 1 }}</div>
              <button class="copy-btn" @click="copy(c.prompt || c.text)">复制</button>
              <div class="result-title">
                {{ (c.brief || '').substring(0, 40) || `方案 ${i+1}` }}
                <span v-if="c.style" class="tag tag-accent2" style="margin-left:8px">{{ c.style }}</span>
                <span v-if="c.composition" class="tag tag-accent3" style="margin-left:6px">{{ c.composition }}</span>
              </div>
              <div v-if="c.text_overlay" class="result-meta">封面文案: <code style="font-size:14px;color:var(--accent)">{{ c.text_overlay }}</code></div>
              <div v-if="c.conflicts_fused?.length" class="result-meta">冲突融合: <code v-for="x in c.conflicts_fused" :key="x">{{ x }}</code></div>
              <div class="prompt-box">
                <div class="prompt-label">AI 封面指令（复制到即梦/可灵）</div>
                <div class="prompt-text">{{ c.prompt || c.text }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- Optimized Covers (双版本) -->
        <div v-if="optimizedPrompts" class="result-section">
          <div class="result-card fade-in" style="grid-column: 1 / -1;">
            <div class="card-header">
              <div class="card-title">🎨 优化版封面指令（双版本）</div>
              <div class="card-meta">来源: {{ optimizedFile || 'generate_cover_structured_v2' }}</div>
            </div>
            <div style="margin-bottom:16px;display:flex;gap:8px;flex-wrap:wrap;">
              <button class="btn" :class="coverVersion === 'jimeng' ? 'btn-primary' : 'btn-secondary'" @click="coverVersion = 'jimeng'">即梦5.0版</button>
              <button class="btn" :class="coverVersion === 'gpt' ? 'btn-primary' : 'btn-secondary'" @click="coverVersion = 'gpt'">GPT/DALL-E 3版</button>
            </div>
            <div class="result-meta" style="margin-bottom:12px;padding:10px;background:var(--bg-elevated);border-left:3px solid var(--accent);">
              <strong>📌 使用说明：</strong><br>
              • <strong>即梦版</strong>：已删除坐标、HEX色值、px单位，强化亚洲面容描述，适配即梦5.0。<br>
              • <strong>GPT版</strong>：使用艺术术语，支持碎片化时空错位构图，DALL-E 3 可理解像素级定位。
            </div>
            <div class="prompt-box" style="margin-top:16px;">
              <div class="prompt-label">
                当前显示：{{ coverVersion === 'jimeng' ? '即梦5.0 封面指令' : 'GPT/DALL-E 3 封面指令' }}
                <button class="copy-btn" style="position:static;margin-left:12px;opacity:1;" @click="copy(optimizedPrompts[coverVersion])">一键复制</button>
              </div>
              <div class="prompt-text" style="max-height:500px;overflow-y:auto;white-space:pre-wrap;">{{ optimizedPrompts[coverVersion] }}</div>
            </div>
          </div>
        </div>

        <!-- Tags -->
        <div v-if="proposal.title_hashtags?.length" class="result-section">
          <h3>🏷 标题标签（title_hashtags）</h3>
          <span v-for="t in proposal.title_hashtags" :key="t" class="tag tag-accent">{{ t }}</span>
        </div>
        <div v-if="proposal.description_tags?.length" class="result-section">
          <h3>📝 描述标签（description_tags）</h3>
          <span v-for="t in proposal.description_tags" :key="t" class="tag tag-accent2">{{ t }}</span>
        </div>

        <!-- Description Template -->
        <div v-if="proposal.description_template" class="result-section">
          <h3>📄 YouTube描述模板</h3>
          <div class="card" style="background:var(--bg-elevated);border-color:var(--border);position:relative">
            <pre style="white-space:pre-wrap;word-break:break-word;font-family:'Space Mono',monospace;font-size:13px;line-height:1.8;color:var(--text)">{{ proposal.description_template }}</pre>
            <button class="copy-btn" @click="copy(proposal.description_template)" style="position:absolute;top:8px;right:8px;opacity:1">复制</button>
          </div>
        </div>
        <!-- Plot Content -->
        <div v-if="proposal.plot_content" class="result-section">
          <h3>📋 输入的剧情内容</h3>
          <div class="card" style="background:var(--bg-elevated);border-color:var(--border);">
            <pre style="white-space:pre-wrap;word-break:break-word;font-size:12px;line-height:1.8;color:var(--text-muted);max-height:300px;overflow-y:auto;">{{ proposal.plot_content.substring(0, 3000) }}</pre>
          </div>
        </div>
      </div>
    </Transition>

    <!-- History -->
    <div class="result-section" style="margin-top:40px">
      <h3 style="cursor:pointer" @click="showHistory = !showHistory">
        📋 历史记录 <span style="font-size:12px;color:var(--text-dim)">{{ showHistory ? '▼' : '▶' }}</span>
      </h3>
      <Transition name="fade">
        <div v-if="showHistory">
          <div v-if="!history.length" class="empty-state" style="padding:20px">暂无历史记录</div>
          <div v-for="h in history" :key="h.filename" class="result-card" style="cursor:pointer" @click="loadDetail(h.filename)">
            <div class="result-title">
              {{ h.drama_name }}
              <span class="tag tag-accent3">{{ h.region }}</span>
              <span v-if="h.type === 'titles'" class="tag tag-accent">📝 标题</span>
              <span v-else class="tag tag-accent2">📋 方案</span>
            </div>
            <div class="result-meta">{{ formatDate(h.generated_at) }} · {{ h.titles_count }}标题 · {{ h.ai_covers_count }}封面指令</div>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { api, apiPost } from '../api/index.js'
import { showLoading, hideLoading } from '../stores/store.js'
import { escapeHtml, copyText as copy, formatDate } from '../utils.js'

const regions = [
  { value: '繁中', label: '繁中（hk, tw, sg, mo）' },
  { value: 'en', label: '英文（en, us, gb, au, ca）' },
  { value: 'id', label: '印尼（id）' },
  { value: 'tr', label: '土耳其（tr）' },
  { value: 'jp', label: '日语（jp）' },
  { value: 'es', label: '西语（es, mx, ar, cl, co, pe）' },
  { value: '葡萄牙', label: '葡萄牙（pt, br）' },
]

const dramaName = ref('')
const plotContent = ref('')
const region = ref('hk')
const direction = ref('')
const generating = ref(false)
const results = ref(false)
const viewingHistory = ref(false)
const showHistory = ref(false)
const history = ref([])
const titles20 = ref([])
const distillInfo = ref(null)
const proposal = ref({})
const covers = ref([])
const optimizedPrompts = ref(null)
const optimizedFile = ref('')
const coverVersion = ref('jimeng')

async function generateTitles() {
  if (!dramaName.value.trim() && !plotContent.value.trim()) return
  generating.value = true
  showLoading('📝 生成20个标题中…（约6秒）')
  try {
    const d = await apiPost('/generate-titles', {
      drama_name: dramaName.value.trim(),
      plot_content: plotContent.value.trim(),
      region: region.value,
      direction: direction.value.trim()
    })
    results.value = true
    viewingHistory.value = false
    titles20.value = d.titles || []
    distillInfo.value = d.distill_info || null
    proposal.value = {}
  } catch (err) { console.error('[Upload]', err) }
  finally { generating.value = false; hideLoading() }
}

async function generateProposal() {
  if (!dramaName.value.trim() && !plotContent.value.trim()) return
  generating.value = true
  showLoading('🤖 Agent 生成上架方案中…（约30秒）')
  try {
    const d = await apiPost('/proposal', {
      drama_name: dramaName.value.trim(),
      plot_content: plotContent.value.trim(),
      region: region.value,
      direction: direction.value.trim()
    })
    results.value = true
    viewingHistory.value = false
    proposal.value = d.proposal || {}
    titles20.value = []
    distillInfo.value = null
    loadHistory()
  } catch (err) { console.error('[Upload]', err) }
  finally { generating.value = false; hideLoading() }
}

async function generateCovers() {
  if (!dramaName.value.trim()) return
  generating.value = true
  showLoading('🎨 生成封面指令…')
  try {
    const d = await apiPost('/generate', {
      action: 'cover',
      drama_name: dramaName.value.trim(),
      region: region.value
    })
    results.value = true
    viewingHistory.value = false
    covers.value = d.candidates || []
    titles20.value = []
    proposal.value = {}
    optimizedPrompts.value = null
  } catch (err) { console.error('[Upload]', err) }
  finally { generating.value = false; hideLoading() }
}

async function generateOptimizedCovers() {
  if (!dramaName.value.trim()) return
  generating.value = true
  showLoading('✨ 生成优化版封面（双版本）…')
  try {
    const d = await apiPost('/generate', {
      action: 'cover_optimized',
      drama_name: dramaName.value.trim(),
      region: region.value
    })
    results.value = true
    viewingHistory.value = false
    optimizedPrompts.value = d.prompts || null
    optimizedFile.value = d.file || ''
    coverVersion.value = 'jimeng'
    covers.value = []
    titles20.value = []
    proposal.value = {}
  } catch (err) { console.error('[Upload]', err) }
  finally { generating.value = false; hideLoading() }
}

async function loadHistory() {
  try {
    const d = await api('/proposal-history')
    history.value = d.history || []
  } catch (err) { console.error('[Upload]', err) }
}

async function loadDetail(filename) {
  showLoading('加载详情…')
  try {
    const d = await api(`/proposal-detail?file=${encodeURIComponent(filename)}`)
    if (d.detail) {
      proposal.value = d.detail
      titles20.value = []
      distillInfo.value = null
      results.value = true
      viewingHistory.value = true
      showHistory.value = false
    }
  } catch (err) { console.error('[Upload]', err) }
  finally { hideLoading() }
}

function backToHistory() {
  results.value = false
  viewingHistory.value = false
  showHistory.value = true
  loadHistory()
}

onMounted(() => { loadHistory() })
</script>
