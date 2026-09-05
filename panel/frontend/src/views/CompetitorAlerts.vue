<template>
  <div>
    <div class="tabs" style="display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap;">
      <div class="tab" :class="{ active: view === 'alerts' }" @click="view = 'alerts'">🔔 爆款预警</div>
      <div class="tab" :class="{ active: view === 'ranking' }" @click="view = 'ranking'">🔥 24h 增量热榜</div>
      <select v-model="langFilter" style="margin-left:auto;background:var(--bg-card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;padding:4px 8px;">
        <option value="">全部语种</option>
        <option v-for="l in langs" :key="l" :value="l">{{ l }}</option>
      </select>
    </div>
    <div style="font-size:10.5px;color:var(--text-dim);margin-bottom:10px;line-height:1.5;">
      <template v-if="view === 'alerts'">
        🔔 <b>爆款预警</b> = 新视频（≤7天）触发阈值才上榜，少而准、需要行动（跟拍选题）。数据与热榜有重叠属正常——热榜里同时触发预警的条目带 🚨 标记。
      </template>
      <template v-else>
        🔥 <b>24h增量热榜</b> = 全部在追踪视频按昨日播放增量排序，含老视频和大盘头部，看风向用。带 🚨 = 同时触发了左侧预警规则。
      </template>
    </div>

    <!-- 数据状态条 -->
    <div v-if="data" style="display:flex;gap:14px;font-size:11px;color:var(--text-muted);margin-bottom:10px;flex-wrap:wrap;">
      <span>数据更新: {{ data.generated_at || '—' }}</span>
      <span>历史: {{ data.history_days }} 天</span>
      <span v-if="data.ranking_date">热榜日期: {{ data.ranking_date }}</span>
      <span style="color:var(--text-dim);">预警规则: 🚀{{ data.thresholds?.breakout }} · ⚡{{ data.thresholds?.spike }} · 🌱{{ data.thresholds?.early_rise }}</span>
    </div>

    <!-- 🔔 爆款预警 -->
    <div v-if="view === 'alerts'">
      <div v-if="!filteredAlerts.length" class="empty-state">
        <div class="icon">🔔</div>
        <div>{{ data && data.history_days < 2 ? '首日基线建立中 — 预警从明天开始（需要≥2天历史算24h增量）' : (langFilter ? '该语种暂无预警' : '暂无预警') }}</div>
      </div>
      <div v-for="a in filteredAlerts" :key="a.video_id" class="alert-card" @click="openVideo(a)">
        <div style="display:flex;gap:8px;align-items:flex-start;">
          <div style="font-size:18px;">{{ typeIcons(a) }}</div>
          <div style="flex:1;min-width:0;">
            <div style="font-size:13px;font-weight:600;line-height:1.35;">{{ a.title || '(无标题)' }}</div>
            <div style="font-size:10px;color:var(--text-muted);margin-top:3px;">
              {{ a.channel }} · {{ a.language }} · {{ a.age_days }}天前发布
            </div>
            <div style="display:flex;gap:12px;margin-top:5px;font-size:11px;flex-wrap:wrap;align-items:center;">
              <span style="color:#e67e22;font-weight:bold;">+{{ fmt(a.delta_24h) }} <span style="font-size:9px;">24h增量</span></span>
              <span style="color:var(--text-muted);">总 {{ fmt(a.views) }}</span>
              <span v-if="a.baseline_daily" style="color:var(--text-dim);">基线 {{ fmt(a.baseline_daily) }}/天</span>
              <span v-if="a.spark && a.spark.some(v => v != null)" style="display:inline-flex;gap:1px;align-items:flex-end;height:16px;" title="近14天播放走势">
                <span v-for="(v, i) in a.spark" :key="i" style="width:3px;background:#4ecdc4;border-radius:1px;"
                      :style="{ height: (v == null ? 1 : Math.max(2, Math.round(v / Math.max(...a.spark.filter(x => x != null), 1) * 16))) + 'px', opacity: v == null ? 0.2 : (i === a.spark.length - 1 ? 1 : 0.45) }"></span>
              </span>
            </div>
            <div v-if="a.subtitle" style="display:flex;gap:5px;margin-top:5px;font-size:10px;flex-wrap:wrap;align-items:center;">
              <span style="font-size:9px;color:var(--text-dim);">字幕实证:</span>
              <span v-for="g in (a.subtitle.l1 || [])" :key="g" style="background:rgba(52,152,219,0.12);color:#3498db;padding:0 6px;border-radius:3px;">{{ g }}</span>
              <span v-if="a.subtitle.hook" style="background:rgba(230,126,34,0.12);color:#e67e22;padding:0 6px;border-radius:3px;">🪝 {{ a.subtitle.hook }}</span>
              <span v-if="a.subtitle.translated" style="color:var(--text-dim);">翻译剧</span>
              <span @click.stop="toggleExpand(a.video_id)" style="color:#3498db;cursor:pointer;font-size:10px;">{{ expanded[a.video_id] ? '▲ 收起' : '▼ 内容实证' }}</span>
            </div>
            <!-- 折叠的内容实证详情 -->
            <div v-if="expanded[a.video_id] && a.content" style="margin-top:8px;border-top:1px solid var(--border-subtle);padding-top:8px;" @click.stop>
              <div v-if="a.content.synopsis" style="font-size:11.5px;line-height:1.6;margin-bottom:6px;">{{ a.content.synopsis }}</div>
              <div v-if="(a.subtitle.l2 || []).length" style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px;">
                <span v-for="g in a.subtitle.l2" :key="g" style="font-size:10px;color:var(--text-muted);border:1px solid var(--border);padding:1px 6px;border-radius:3px;">{{ g }}</span>
              </div>
              <div v-if="a.content.hook_event" style="font-size:10.5px;margin-bottom:6px;">
                <span style="background:rgba(230,126,34,0.15);color:#e67e22;padding:1px 8px;border-radius:4px;">🪝 {{ a.subtitle.hook }}<template v-if="a.content.hook_sec != null"> · 第 {{ a.content.hook_sec }} 秒</template></span>
                <span style="color:var(--text-muted);margin-left:6px;">{{ a.content.hook_event }}</span>
              </div>
              <div v-if="(a.content.emotion_tags || []).length || a.content.audience" style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:6px;align-items:center;">
                <span v-if="a.content.audience" style="font-size:10px;background:rgba(52,152,219,0.12);color:#3498db;padding:1px 6px;border-radius:3px;">{{ a.content.audience }}</span>
                <span v-for="e in a.content.emotion_tags" :key="e" style="font-size:10px;color:var(--text-muted);border:1px solid var(--border);padding:1px 6px;border-radius:3px;">{{ e }}</span>
              </div>
              <div v-if="(a.content.hit_signals || []).length" style="margin-bottom:6px;">
                <div style="font-size:9.5px;color:var(--text-muted);margin-bottom:3px;">🔥 爆款信号</div>
                <div v-for="(s, si) in a.content.hit_signals" :key="si" style="font-size:10.5px;line-height:1.55;color:var(--text-main);">· {{ s }}</div>
              </div>
              <div v-if="a.content.antagonist && a.content.antagonist.desc" style="font-size:10.5px;margin-bottom:6px;color:var(--text-muted);">
                <span style="color:#c0392b;">反派</span> {{ a.content.antagonist.archetype }} — {{ a.content.antagonist.desc }}
              </div>
              <div v-if="a.content.title_match && a.content.title_match.delivers === false" style="font-size:10px;margin-bottom:6px;background:rgba(231,76,60,0.08);border:1px solid rgba(231,76,60,0.25);border-radius:4px;padding:3px 8px;color:#e74c3c;">
                ⚠️ 标题承诺「{{ a.content.title_match.promise }}」字幕未兑现：{{ a.content.title_match.gap }}
              </div>
              <div v-if="(a.content.lines_cn || []).length" style="margin-bottom:6px;">
                <div style="font-size:9.5px;color:var(--text-muted);margin-bottom:3px;">💬 标志性台词</div>
                <div v-for="(ln, li) in a.content.lines_cn" :key="li" style="font-size:10.5px;line-height:1.55;color:var(--text-main);">“{{ ln }}”</div>
              </div>
              <div v-if="(a.content.reveals || []).length" style="margin-bottom:6px;">
                <div style="font-size:9.5px;color:var(--text-muted);margin-bottom:4px;">反转时间轴（按片长位置）</div>
                <div style="position:relative;height:10px;background:var(--bg-elevated);border-radius:5px;">
                  <div v-for="(rv, ri) in alertReveals(a)" :key="ri"
                       :style="{ position: 'absolute', left: Math.min(Math.max(rv.pct, 2), 97) + '%', top: '0', width: '2px', height: '10px', background: '#e67e22' }"></div>
                </div>
                <div v-for="(rv, ri) in alertReveals(a)" :key="'r' + ri" style="font-size:10px;color:var(--text-muted);margin-top:3px;">
                  <span style="color:#e67e22;">{{ rv.pct }}%</span> {{ rv.event }}
                </div>
              </div>
              <div style="font-size:9.5px;color:var(--text-dim);">{{ a.content.model_family }} · conf {{ a.content.confidence }}</div>
            </div>
          </div>
          <div style="font-size:9px;color:var(--text-dim);white-space:nowrap;text-align:right;">▶ YouTube<br /><span @click.stop="toggleExpand(a.video_id)" style="cursor:pointer;color:#3498db;" v-if="a.content">{{ expanded[a.video_id] ? '▲' : '▼' }}</span></div>
        </div>
      </div>
    </div>

    <!-- 🔥 24h增量热榜 -->
    <div v-if="view === 'ranking'">
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center;">
        <span style="font-size:10px;color:var(--text-dim);">按24h播放增量排序 — 比总量榜更能发现"正在爆"的视频</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:11px;">
        <thead>
          <tr style="color:var(--text-dim);font-size:10px;text-align:left;">
            <th style="padding:4px 6px;">#</th>
            <th style="padding:4px 6px;">视频</th>
            <th style="padding:4px 6px;">频道</th>
            <th style="padding:4px 6px;text-align:right;">24h增量</th>
            <th style="padding:4px 6px;text-align:right;">总播放</th>
            <th style="padding:4px 6px;text-align:right;">发布</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in filteredRanking" :key="r.video_id"
              style="border-top:1px solid var(--border);cursor:pointer;"
              @click="openVideo(r)">
            <td style="padding:5px 6px;color:var(--text-dim);">{{ i + 1 }}</td>
            <td style="padding:5px 6px;max-width:340px;">
              <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;"><span v-if="r.alerted" title="同时触发了爆款预警" style="color:#e74c3c;">🚨 </span>{{ r.title || '(无标题)' }}</div>
            </td>
            <td style="padding:5px 6px;color:var(--text-muted);">{{ r.channel }}</td>
            <td style="padding:5px 6px;text-align:right;color:#e67e22;font-weight:bold;">+{{ fmt(r.delta_24h) }}</td>
            <td style="padding:5px 6px;text-align:right;color:var(--text-muted);">{{ fmt(r.views) }}</td>
            <td style="padding:5px 6px;text-align:right;color:var(--text-dim);">{{ (r.published_at || '').slice(0, 10) }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="!filteredRanking.length" class="empty-state">
        <div class="icon">🔥</div>
        <div>{{ data && data.history_days < 2 ? '明天开始有增量数据（历史需≥2天）' : '暂无数据' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const data = ref(null)
const view = ref('alerts')
const langFilter = ref('')

const alerts = computed(() => data.value?.alerts || [])
const ranking = computed(() => data.value?.ranking || [])
const langs = computed(() => [...new Set([
  ...alerts.value.map(a => a.language),
  ...ranking.value.map(r => r.language),
].filter(Boolean))])
const filteredAlerts = computed(() =>
  langFilter.value ? alerts.value.filter(a => a.language === langFilter.value) : alerts.value
)
const filteredRanking = computed(() =>
  langFilter.value ? ranking.value.filter(r => r.language === langFilter.value) : ranking.value
)

const TYPE_ICON = { breakout: '🚀', spike: '⚡', early_rise: '🌱' }
function typeIcons(a) {
  return (a.alert_types || []).map(t => TYPE_ICON[t] || '•').join('')
}
function fmt(n) {
  if (n == null) return '—'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  return n.toLocaleString()
}
const expanded = ref({})
function toggleExpand(vid) { expanded.value[vid] = !expanded.value[vid] }
function alertReveals(a) {
  const dur = a.content?.duration_sec || 0
  return (a.content?.reveals || [])
    .filter(rv => rv.at_sec != null)
    .map(rv => ({ pct: dur ? Math.max(1, Math.round(rv.at_sec / dur * 100)) : 50, event: rv.event || '' }))
    .slice(0, 5)
}
function openVideo(a) {
  window.open(`https://www.youtube.com/watch?v=${a.video_id}`, '_blank')
}

onMounted(async () => {
  try {
    data.value = await api('/competitor-alerts')
  } catch (e) {
    console.error('alerts load fail', e)
  }
})
</script>

<style scoped>
.alert-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color .15s;
}
.alert-card:hover { border-color: #e67e22; }
.empty-state { text-align: center; padding: 40px 0; color: var(--text-dim); }
.empty-state .icon { font-size: 30px; margin-bottom: 8px; }
</style>
