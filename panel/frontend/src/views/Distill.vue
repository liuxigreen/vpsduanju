<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <div>
        <h1>蒸馏数据</h1>
        <p class="page-desc">三层架构蒸馏 · 原则→示例→生成规则 · 每个地区独立数据</p>
      </div>
      <button class="btn btn-secondary btn-sm" @click="load" title="刷新">↻ 刷新</button>
    </div>

    <div v-if="loading" style="color:var(--text-muted)">加载中…</div>

    <div v-else-if="!regions.length" class="empty-state">暂无蒸馏数据。运行 distill 流程后此处自动展示。</div>

    <Transition name="fade">
      <div v-if="regions.length">
        <div class="stats-grid" style="margin-bottom:20px;">
          <div v-for="reg in regions" :key="reg.lang" class="stat-card">
            <div class="stat-value">{{ reg.lang }}</div>
            <div class="stat-label">{{ reg.sections?.length || 0 }} 个章节 · {{ reg.evidence_files?.length || 0 }} 个证据文件</div>
          </div>
        </div>

        <div v-for="reg in regions" :key="reg.lang" class="card" style="margin-bottom:16px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
            <h2 style="margin:0;">🧪 {{ reg.lang }} 市场蒸馏</h2>
            <button class="btn btn-secondary btn-sm" @click="showDetail(reg.lang)">查看详情</button>
          </div>
          <div v-if="reg.sections?.length" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px;">
            <span v-for="s in reg.sections" :key="s" style="background:var(--bg-elevated);border:1px solid var(--border);border-radius:6px;padding:3px 10px;font-size:12px;color:var(--text-dim);">{{ s }}</span>
          </div>
          <div v-if="reg.preview" style="background:var(--bg-elevated);border-radius:8px;padding:12px;font-size:13px;color:var(--text-muted);max-height:120px;overflow:hidden;white-space:pre-wrap;">{{ reg.preview.substring(0, 400) }}…</div>
          <div v-if="reg.summary" style="margin-top:12px;display:flex;gap:12px;flex-wrap:wrap;">
            <span v-if="reg.summary.total_titles" style="font-size:12px;color:var(--accent2);">📝 {{ reg.summary.total_titles }} 标题</span>
            <span v-if="reg.summary.total_covers" style="font-size:12px;color:var(--accent3);">🎨 {{ reg.summary.total_covers }} 封面</span>
            <span v-if="reg.summary.total_tags" style="font-size:12px;color:var(--accent4);">🏷 {{ reg.summary.total_tags }} 标签</span>
          </div>
        </div>
      </div>
    </Transition>

    <!-- Detail Modal -->
    <Transition name="fade">
      <div v-if="detail" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.85);z-index:1000;overflow-y:auto;padding:20px;" @click.self="detail = null">
        <div style="max-width:860px;margin:30px auto;background:var(--bg-card);border-radius:12px;overflow:hidden;border:1px solid var(--border);padding:24px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;">
            <h2 style="margin:0;">🧪 {{ detail.lang }} 蒸馏详情</h2>
            <button @click="detail = null" style="background:none;border:none;color:var(--text-muted);font-size:24px;cursor:pointer;">✕</button>
          </div>

          <!-- Tab buttons with dates -->
          <div style="display:flex;gap:6px;margin-bottom:16px;flex-wrap:wrap;">
            <button class="btn btn-sm" :style="activeTab === 'mimo' ? 'background:var(--accent);color:#fff;' : 'background:var(--bg-elevated);'" @click="activeTab = 'mimo'">
              🆕 3.0{{ mimoDate ? ' (' + mimoDate + ')' : '' }}
            </button>
            <button class="btn btn-sm" :style="activeTab === 'gpt' ? 'background:var(--accent2);color:#fff;' : 'background:var(--bg-elevated);'" @click="activeTab = 'gpt'">
              🤖 {{ detail.gpt_model || 'GPT-5.5' }}{{ gptDate ? ' (' + gptDate + ')' : '' }}
            </button>
          </div>

          <!-- MiMo content -->
          <div v-show="activeTab === 'mimo'">
            <template v-if="detail.mimo_content">
              <DistillContent :content="detail.mimo_content" />
            </template>
            <div v-else class="empty-state">暂无 MiMo 蒸馏数据</div>
          </div>

          <!-- GPT content -->
          <div v-show="activeTab === 'gpt'">
            <template v-if="detail.gpt_content">
              <DistillContent :content="detail.gpt_content" />
            </template>
            <div v-else class="empty-state">暂无 GPT 蒸馏数据</div>
          </div>

          <!-- Evidence data -->
          <template v-if="evidenceKeys.length">
            <h2 style="margin:20px 0 12px;">证据数据</h2>
            <div v-for="key in evidenceKeys" :key="key" class="card" style="margin-bottom:12px;">
              <h2 style="font-size:14px;color:var(--accent2);">{{ key }}</h2>
              <div style="background:var(--bg-elevated);border-radius:8px;padding:12px;font-size:12px;max-height:300px;overflow-y:auto;">
                <pre style="white-space:pre-wrap;color:var(--text-dim);">{{ formatJson(detail[key]) }}</pre>
              </div>
            </div>
          </template>
        </div>
      </div>
    </Transition>
  </div>
</template>

<!-- DistillContent: structured render of stats/why/what/how -->
<script>
import { h, defineComponent } from 'vue'

const EXCLUDE_KEYS = ['lang','mimo_content','gpt_content','mimo_version','mimo_generated','gpt_version','gpt_generated','gpt_model']

export const DistillContent = defineComponent({
  name: 'DistillContent',
  props: { content: { type: Object, required: true } },
  setup(props) {
    return () => {
      const nc = props.content
      const nodes = []

      // ── Stats ──
      if (nc.stats) {
        const s = nc.stats
        nodes.push(h('div', { class: 'card', style: 'margin-bottom:16px;' }, [
          h('h2', {}, '📈 数据统计'),
          s.avg_title_length ? h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `标题均长: ${s.avg_title_length}字符`) : null,
          s.emoji_rate ? h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `Emoji使用率: ${s.emoji_rate}%`) : null,
          s.best_hours?.length ? h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `最佳小时: ${s.best_hours.join(', ')}`) : null,
          s.best_weekdays?.length ? h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `最佳星期: ${s.best_weekdays.join(', ')}`) : null,
          s.key_words?.length ? h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `高频关键词: ${s.key_words.join(', ')}`) : null,
          s.top_emojis?.length ? h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `常用Emoji: ${s.top_emojis.join(' ')}`) : null,
        ]))
      }

      // ── WHY ──
      if (nc.why) {
        const whyChildren = [h('h2', {}, '🧠 WHY（为什么有效）')]
        if (typeof nc.why === 'object' && !Array.isArray(nc.why)) {
          const dims = [['title','📝 标题原则'],['thumbnail','🖼️ 封面原则'],['tags_and_distribution','🏷️ 标签与分发原则']]
          dims.forEach(([key, label]) => {
            const items = nc.why[key]
            if (Array.isArray(items) && items.length) {
              whyChildren.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, label))
              items.forEach(item => {
                if (typeof item === 'object') {
                  whyChildren.push(h('div', { style: 'font-size:13px;color:var(--text-dim);margin:6px 0;' }, [h('b', {}, `▸ ${item.principle || ''}`)]))
                  if (item.psychology) whyChildren.push(h('div', { style: 'font-size:12px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `心理: ${item.psychology}`))
                  if (item.application) whyChildren.push(h('div', { style: 'font-size:12px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `应用: ${item.application}`))
                } else {
                  whyChildren.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `• ${item}`))
                }
              })
            }
          })
          const mi = nc.why.market_insights
          if (mi && typeof mi === 'object') {
            whyChildren.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, '🔍 市场洞察'))
            ;[['gender_bias','男女频差异'],['emerging_trends','新兴趋势'],['content_quality_signals','质量信号']].forEach(([k,l]) => {
              if (mi[k]) whyChildren.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `• ${l}: ${mi[k]}`))
            })
          }
        } else {
          whyChildren.push(h('div', { style: 'font-size:13px;line-height:1.8;color:var(--text-dim);white-space:pre-wrap;' }, typeof nc.why === 'string' ? nc.why : JSON.stringify(nc.why, null, 2)))
        }
        nodes.push(h('div', { class: 'card', style: 'margin-bottom:16px;' }, whyChildren))
      }

      // ── WHAT ──
      if (Array.isArray(nc.what) && nc.what.length) {
        const whatChildren = [h('h2', {}, '📊 WHAT（爆款故事模式）')]
        nc.what.forEach(item => {
          whatChildren.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, `▸ ${item.name || '模式'}`))
          if (item.template) whatChildren.push(h('div', { style: 'font-size:13px;color:var(--text-dim);margin:4px 0;background:var(--bg-code);padding:8px;border-radius:6px;' }, item.template))
          if (item.why_it_works) whatChildren.push(h('div', { style: 'font-size:12px;color:var(--text-muted);margin:2px 0;' }, `💡 ${item.why_it_works}`))
          if (item.sub_genre) whatChildren.push(h('div', { style: 'font-size:11px;color:var(--text-muted);margin:2px 0;' }, `题材: ${item.sub_genre}`))
          if (item.examples?.length) whatChildren.push(h('div', { style: 'font-size:11px;color:var(--text-muted);margin:2px 0;' }, `示例: ${item.examples.slice(0, 2).join(' | ')}`))
        })
        nodes.push(h('div', { class: 'card', style: 'margin-bottom:16px;' }, whatChildren))
      }

      // ── HOW ──
      if (nc.how) {
        const hr = [h('h2', {}, '🔧 HOW（执行规则）')]
        const hh = nc.how

        // Title skeletons
        if (hh.title_skeletons?.length) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, '标题骨架'))
          hh.title_skeletons.forEach(s => {
            hr.push(h('div', { style: 'font-size:13px;color:var(--text-dim);margin:6px 0;' }, [h('b', {}, `▸ ${s.name || '骨架'}`)]))
            if (s.narrative_pattern || s.core_formula) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0 2px 16px;background:var(--bg-code);padding:6px;border-radius:4px;' }, s.narrative_pattern || s.core_formula))
            if (s.psychological_hook || s.why_it_works) hr.push(h('div', { style: 'font-size:11px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `🪝 ${s.psychological_hook || s.why_it_works}`))
            ;(s.rules || []).forEach(r => hr.push(h('div', { style: 'font-size:11px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `• ${r}`)))
          })
        }

        // Rhetorical patterns
        const rp = hh.rhetorical_patterns
        if (rp?.sentence_structures?.length) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent4);margin:12px 0 8px;' }, '📦 标题包装模式'))
          rp.sentence_structures.forEach(s => {
            hr.push(h('div', { style: 'font-size:13px;color:var(--text-dim);margin:6px 0;' }, [h('b', {}, `▸ ${s.name || '模式'}`)]))
            if (s.pattern) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0 2px 16px;background:var(--bg-code);padding:6px;border-radius:4px;font-family:monospace;' }, s.pattern))
            if (s.example) hr.push(h('div', { style: 'font-size:11px;color:var(--accent1);margin:2px 0 2px 16px;' }, `💡 ${s.example}`))
            if (s.when_to_use) hr.push(h('div', { style: 'font-size:11px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `📌 ${s.when_to_use}`))
          })
        }

        // Hook combination
        const hc = hh.hook_combination
        if (hc) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent2);margin:12px 0 8px;' }, '🎯 钩子组合'))
          // 核心发现（兼容旧版golden_triangle）
          const coreDiscovery = hc['核心发现'] || hc.golden_triangle
          if (coreDiscovery) hr.push(h('div', { style: 'font-size:13px;color:var(--text-dim);margin:4px 0;background:linear-gradient(135deg,rgba(255,204,102,.15),rgba(43,213,118,.15));border:1px solid rgba(255,204,102,.4);border-radius:8px;padding:12px;' }, coreDiscovery))
          // 最强配对（兼容新旧字段名）
          const pairs = hc['最强配对'] || hc.strongest_pairs
          if (pairs?.length) {
            hr.push(h('div', { style: 'font-size:12px;color:var(--accent3);margin:8px 0 4px;' }, [h('b', {}, '最强配对:')]))
            pairs.forEach(p => hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0 2px 16px;' }, `🔥 ${p}`)))
          }
          // 低效组合（兼容新旧字段名）
          const forbidden = hc['低效组合'] || hc.forbidden_combinations
          if (forbidden?.length) {
            hr.push(h('div', { style: 'font-size:12px;color:var(--danger);margin:8px 0 4px;' }, [h('b', {}, '低效组合:')]))
            forbidden.forEach(c => hr.push(h('div', { style: 'font-size:12px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `❌ ${c}`)))
          }
          // 规则
          const rules = hc['规则'] || hc.rules
          if (rules?.length) {
            hr.push(h('div', { style: 'font-size:12px;color:var(--accent4);margin:8px 0 4px;' }, [h('b', {}, '规则:')]))
            rules.forEach(r => hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0 2px 16px;' }, `📌 ${r}`)))
          }
          // hook_types（新版：从数据中识别的钩子类型）
          const hookTypes = hc.hook_types
          if (hookTypes && Object.keys(hookTypes).length) {
            hr.push(h('div', { style: 'font-size:12px;color:var(--accent2);margin:8px 0 4px;' }, [h('b', {}, '钩子类型:')]))
            const stats = hc.hook_stats || {}
            Object.entries(hookTypes).forEach(([name, detail]) => {
              const count = stats[name] || 0
              const defn = typeof detail === 'object' ? detail.definition : detail
              hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0 2px 16px;' }, `• ${name}(${count}): ${defn || ''}`))
            })
          }
          // emergent_hooks（新发现的钩子类型）
          const emergent = hc.emergent_hooks
          if (emergent?.length) {
            hr.push(h('div', { style: 'font-size:12px;color:var(--accent1);margin:8px 0 4px;' }, [h('b', {}, '新发现钩子:')]))
            emergent.forEach(e => hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0 2px 16px;' }, `🆕 ${e.name || e}: ${e.definition || ''}`)))
          }
        }

        // Title constraints
        const tc = hh.title_constraints
        if (tc) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, '标题约束'))
          if (tc.avg_length) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `均长: ${tc.avg_length}字符 · Emoji率: ${tc.emoji_rate || 0}%`))
          // 兼容新旧字段
          const structure = tc.title_structure || tc.front_half
          if (structure) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `结构: ${structure}`))
          if (tc.back_half) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `后半句: ${tc.back_half}`))
          if (tc.key_words?.length) hr.push(h('div', { style: 'font-size:11px;color:var(--text-muted);margin:2px 0;' }, `关键词: ${tc.key_words.join(', ')}`))
        }

        // Thumbnail guidelines
        const tg = hh.thumbnail_guidelines
        if (tg) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, '封面指南'))
          ;[['composition','构图'],['figures','人物'],['colors','色彩'],['emotion','情绪基调'],['visual_symbols','视觉符号'],['text','文字']].forEach(([k,l]) => {
            if (tg[k]) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `• ${l}: ${tg[k]}`))
          })
        }

        // Cover-Title Synergy
        const syn = hh.cover_title_synergy || hh.title_synergy
        if (syn) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent1);margin:12px 0 8px;' }, '🔗 封面×标题协同'))
          if (syn.rule) hr.push(h('div', { style: 'font-size:13px;color:var(--text-dim);margin:4px 0;background:linear-gradient(135deg,rgba(255,107,107,.15),rgba(78,205,196,.15));border:1px solid rgba(255,107,107,.4);border-radius:8px;padding:12px;' }, syn.rule))
          if (syn.patterns?.length) {
            hr.push(h('div', { style: 'font-size:12px;color:var(--accent3);margin:8px 0 4px;' }, [h('b', {}, '协同模式:')]))
            syn.patterns.forEach(p => {
              hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:4px 0 2px 16px;' }, [h('b', {}, `▸ ${p.name || '模式'}`)]))
              if (p.description) hr.push(h('div', { style: 'font-size:11px;color:var(--text-muted);margin:2px 0 2px 28px;' }, p.description))
              if (p.example) hr.push(h('div', { style: 'font-size:11px;color:var(--accent1);margin:2px 0 2px 28px;' }, `💡 ${p.example}`))
            })
          }
          if (syn.anti_patterns?.length) {
            hr.push(h('div', { style: 'font-size:12px;color:var(--danger);margin:8px 0 4px;' }, [h('b', {}, '反模式:')]))
            syn.anti_patterns.forEach(a => hr.push(h('div', { style: 'font-size:12px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `❌ ${a.name || ''}: ${a.description || a}`)))
          }
        }

        // Hashtag strategy
        const hs = hh.hashtag_strategy
        if (hs) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, '标签策略'))
          if (hs.combination_pattern) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `组合模式: ${hs.combination_pattern}`))
          if (hs.trend_hijacking) hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `热点截流: ${hs.trend_hijacking}`))
          ;(hs.rules || []).forEach(r => hr.push(h('div', { style: 'font-size:12px;color:var(--text-muted);margin:2px 0 2px 16px;' }, `• ${r}`)))
        }

        // Publish time
        const pt = hh.publish_time
        if (pt) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, '发布时间'))
          hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `最佳小时: ${(pt.best_hours || []).join(', ')} · 最佳星期: ${(pt.best_weekdays || []).join(', ')}`))
        }

        // Growth strategy
        if (hh.growth_strategy?.length) {
          hr.push(h('h3', { style: 'font-size:14px;color:var(--accent3);margin:12px 0 8px;' }, '频道增长策略'))
          hh.growth_strategy.forEach(r => hr.push(h('div', { style: 'font-size:12px;color:var(--text-dim);margin:2px 0;' }, `✅ ${r}`)))
        }

        nodes.push(h('div', { class: 'card', style: 'margin-bottom:16px;' }, hr))
      }

      return nodes
    }
  }
})
</script>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'
import { showLoading, hideLoading } from '../stores/store.js'

const EXCLUDE_KEYS = ['lang','mimo_content','gpt_content','mimo_version','mimo_generated','gpt_version','gpt_generated','gpt_model']

const loading = ref(true)
const regions = ref([])
const detail = ref(null)
const activeTab = ref('mimo')

const mimoDate = computed(() => detail.value?.mimo_generated ? new Date(detail.value.mimo_generated).toLocaleDateString('zh-CN') : '')
const gptDate = computed(() => detail.value?.gpt_generated ? new Date(detail.value.gpt_generated).toLocaleDateString('zh-CN') : '')

const evidenceKeys = computed(() => {
  if (!detail.value) return []
  return Object.keys(detail.value).filter(k => !EXCLUDE_KEYS.includes(k) && typeof detail.value[k] === 'object' && detail.value[k] !== null)
})

function formatJson(obj) {
  try { return JSON.stringify(obj, null, 2).substring(0, 3000) } catch { return String(obj) }
}

async function load() {
  loading.value = true
  try {
    const d = await api('/distill')
    regions.value = d.regions || []
  } catch (err) { console.error('[Distill]', err) }
  finally { loading.value = false }
}

async function showDetail(lang) {
  showLoading('加载蒸馏详情…')
  try {
    const d = await api(`/distill-detail?lang=${encodeURIComponent(lang)}`)
    detail.value = d
    activeTab.value = 'mimo'
  } catch (err) { console.error('[Distill]', err) }
  finally { hideLoading() }
}

onMounted(() => { load() })
</script>
