<template>
  <div>
    <div class="tabs" style="display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap;">
      <div class="tab" :class="{ active: view === 'alerts' }" @click="view = 'alerts'">🔔 爆款预警</div>
      <div class="tab" :class="{ active: view === 'ranking' }" @click="view = 'ranking'">🔥 24h 增量热榜</div>
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
      <div v-if="!alerts.length" class="empty-state">
        <div class="icon">🔔</div>
        <div>{{ data && data.history_days < 2 ? '首日基线建立中 — 预警从明天开始（需要≥2天历史算24h增量）' : '暂无预警' }}</div>
      </div>
      <div v-for="a in alerts" :key="a.video_id" class="alert-card" @click="openVideo(a)">
        <div style="display:flex;gap:8px;align-items:flex-start;">
          <div style="font-size:18px;">{{ typeIcons(a) }}</div>
          <div style="flex:1;min-width:0;">
            <div style="font-size:13px;font-weight:600;line-height:1.35;">{{ a.title || '(无标题)' }}</div>
            <div style="font-size:10px;color:var(--text-muted);margin-top:3px;">
              {{ a.channel }} · {{ a.language }} · {{ a.age_days }}天前发布
            </div>
            <div style="display:flex;gap:12px;margin-top:5px;font-size:11px;flex-wrap:wrap;">
              <span style="color:#e67e22;font-weight:bold;">+{{ fmt(a.delta_24h) }} <span style="font-size:9px;">24h增量</span></span>
              <span style="color:var(--text-muted);">总 {{ fmt(a.views) }}</span>
              <span v-if="a.baseline_daily" style="color:var(--text-dim);">基线 {{ fmt(a.baseline_daily) }}/天</span>
            </div>
          </div>
          <div style="font-size:9px;color:var(--text-dim);white-space:nowrap;">▶ YouTube</div>
        </div>
      </div>
    </div>

    <!-- 🔥 24h增量热榜 -->
    <div v-if="view === 'ranking'">
      <div style="display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap;align-items:center;">
        <select v-model="langFilter" style="background:var(--bg-card);border:1px solid var(--border);border-radius:6px;color:var(--text);font-size:11px;padding:4px 8px;">
          <option value="">全部语种</option>
          <option v-for="l in langs" :key="l" :value="l">{{ l }}</option>
        </select>
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
              <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-weight:500;">{{ r.title || '(无标题)' }}</div>
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
const langs = computed(() => [...new Set((data.value?.ranking || []).map(r => r.language).filter(Boolean))])
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
