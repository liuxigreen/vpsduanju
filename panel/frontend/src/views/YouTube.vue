<template>
  <div>
    <h1>YouTube 频道管理</h1>
    <p class="page-desc">多账号 OAuth 授权 · 数据分析 · 频道监控</p>

    <div class="yt-btn-row">
      <button class="btn btn-primary" @click="addAccount">+ 添加账号</button>
      <button class="btn btn-secondary" @click="addNewAuth">➕ 添加授权</button>
    </div>

    <!-- Account List as TABLE -->
    <div v-if="!accounts.length" class="empty-state">暂无已授权账号。点击上方按钮添加。</div>
    <div v-else class="yt-channel-grid">
      <div v-for="acc in accounts" :key="acc.slug" class="yt-channel-card" :class="{ 'yt-channel-card--active': selectedSlug === acc.slug }" @click="acc.status === '已授权' ? showAnalytics(acc.slug) : null">
        <div style="display:flex;align-items:center;gap:10px;">
          <img v-if="acc.thumbnail" :src="acc.thumbnail" style="width:40px;height:40px;border-radius:50%;flex-shrink:0;" @error="$event.target.style.display='none'" />
          <div v-else style="width:40px;height:40px;border-radius:50%;background:var(--bg-elevated);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:18px;">📺</div>
          <div style="min-width:0;flex:1;">
            <div style="font-weight:600;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{{ acc.channel_title || acc.slug }}</div>
            <div style="font-size:10px;color:var(--text-dim);font-family:monospace;">{{ acc.channel_id ? acc.channel_id.substring(0,12)+'…' : '-' }}</div>
          </div>
          <span v-if="acc.status === '已授权'" class="tag" style="background:#1a3a1a;color:#8f9d6a;font-size:10px;">✅</span>
          <span v-else-if="acc.status === 'token过期'" class="tag" style="background:#3a3a1a;color:#f0c674;font-size:10px;">🔄</span>
          <span v-else class="tag" style="background:#3a1a1a;color:#cc6666;font-size:10px;">❌</span>
        </div>
        <div style="display:flex;gap:8px;margin-top:6px;font-size:11px;color:var(--text-dim);">
          <span v-if="acc.language">{{ acc.language }}</span>
          <span v-if="acc.operator">{{ acc.operator }}</span>
          <span v-if="acc.niche" style="color:var(--accent3);">{{ acc.niche }}</span>
        </div>
        <div style="margin-top:8px;">
          <button v-if="acc.status === '已授权'" class="btn btn-secondary btn-sm" style="font-size:11px;" @click.stop="showAnalytics(acc.slug)">📊 数据</button>
          <button v-else class="btn btn-primary btn-sm" style="font-size:11px;" @click.stop="refreshAuth(acc.slug || acc.channel_id)">🔑 授权</button>
        </div>
      </div>
    </div>

    <!-- Analytics Panel -->
    <Transition name="fade">
      <div v-if="selectedSlug" style="margin-top: 28px;">
        <div class="yt-analytics-header">
          <h2>📊 {{ selectedSlug }} 数据分析</h2>
          <div class="tabs" style="margin-bottom:0;">
            <div v-for="d in [7,14,30]" :key="d" class="tab" :class="{ active: period === d }" @click="switchPeriod(d)">{{ d }}天</div>
          </div>
          <button class="btn btn-secondary btn-sm" @click="refreshAuth(selectedSlug)" style="margin-left:auto;">🔑 重新授权</button>
        </div>

        <!-- 6 Stats Cards -->
        <div v-if="analyticsError" style="margin-top:16px;padding:16px;background:rgba(204,102,102,0.1);border:1px solid rgba(204,102,102,0.3);border-radius:8px;color:#cc6666;">
          ⚠️ {{ analyticsError }}
          <button class="btn btn-primary btn-sm" style="margin-left:12px;" @click="refreshAuth(selectedSlug)">🔑 重新授权</button>
        </div>
        <div v-else-if="summaryData" class="stats-grid">
          <div class="stat-card">
            <div class="stat-label">观看次数</div>
            <div class="stat-value">{{ formatNumber(summaryData.views || 0) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">观看时长</div>
            <div class="stat-value">{{ (summaryData.estimatedMinutesWatched || 0).toFixed(0) }} 分钟</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">平均观看</div>
            <div class="stat-value">{{ (summaryData.averageViewDuration || 0).toFixed(0) }} 秒</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">点赞</div>
            <div class="stat-value">{{ formatNumber(summaryData.likes || 0) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">新增订阅</div>
            <div class="stat-value" style="color:var(--success);">+{{ summaryData.subscribersGained || 0 }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">流失订阅</div>
            <div class="stat-value" style="color:var(--danger);">-{{ summaryData.subscribersLost || 0 }}</div>
          </div>
        </div>
        <div v-else class="empty-state">暂无汇总数据</div>

        <!-- Dynamic Tables -->
        <div v-for="section in tableSections" :key="section.key" class="card" style="margin-top:16px;">
          <div class="card-header"><div class="card-title">{{ section.title }}</div></div>
          <table v-if="getTableData(section.key).rows?.length" class="data-table">
            <thead>
              <tr>
                <th v-for="h in getTableData(section.key).headers" :key="h">{{ h === 'video' ? '视频' : h }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, ri) in getTableData(section.key).rows" :key="ri">
                <td v-for="(cell, ci) in row" :key="ci">
                  <template v-if="section.key === 'top_videos' && ci === 0">
                    <div style="display:flex;align-items:center;gap:6px;">
                      <img v-if="videoMeta?.thumbnails?.[cell]" :src="videoMeta.thumbnails[cell]" style="width:48px;height:27px;object-fit:cover;border-radius:3px;flex-shrink:0;" @error="$event.target.style.display='none'" />
                      <a :href="'https://youtube.com/watch?v=' + cell" target="_blank" style="color:var(--accent);font-size:12px;">{{ videoMeta?.titles?.[cell] || cell }}</a>
                    </div>
                  </template>
                  <template v-else>{{ cell }}</template>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty-state">暂无数据</div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api, apiPost } from '../api/index.js'
import { store, showLoading, hideLoading } from '../stores/store.js'
import { formatNumber } from '../utils.js'

const accounts = ref([])
const selectedSlug = ref(null)
const period = ref(7)
const analytics = ref({})
const analyticsError = ref('')
const videoMeta = ref(null)

const tableSections = [
  { key: 'daily', title: '📈 每日趋势' },
  { key: 'top_videos', title: '🎬 热门视频' },
  { key: 'geo', title: '🌍 地区分布' },
  { key: 'traffic', title: '🔗 流量来源' },
]

// Parse summary into a flat map
const summaryData = computed(() => {
  const s = analytics.value.summary
  if (!s || !s.rows || !s.rows.length) return null
  const m = {}
  s.headers.forEach((k, i) => { m[k] = s.rows[0][i] })
  return m
})

function getTableData(key) {
  return analytics.value[key] || {}
}

async function loadAccounts() {
  try {
    const d = await api('/yt-accounts')
    accounts.value = d.accounts || []
  } catch (err) { console.error('[YouTube]', err) }
}

function showAnalytics(slug) {
  selectedSlug.value = slug
  store.currentYtSlug = slug
  loadAnalytics()
}

async function switchPeriod(d) {
  period.value = d
  await loadAnalytics()
}

async function loadAnalytics() {
  if (!selectedSlug.value) return
  analyticsError.value = ''
  try {
    const d = await api(`/yt-analytics?slug=${encodeURIComponent(selectedSlug.value)}&period=${period.value}`)
    if (d.error) {
      analyticsError.value = d.error
      analytics.value = {}
      videoMeta.value = null
    } else {
      analytics.value = d
      videoMeta.value = d.video_meta || null
    }
  } catch (err) {
    analyticsError.value = err.message || '加载失败'
    console.error('[YouTube]', err)
  }
}

async function addAccount() {
  const slug = prompt('输入账号标识 (如 hk, us, jp):')
  if (!slug) return
  try {
    const d = await api(`/yt-auth-url?slug=${encodeURIComponent(slug)}`)
    if (d.url) {
      window.open(d.url, '_blank')
      alert('授权完成后，回到此页面点击"查看数据"。')
    } else {
      alert('错误: ' + (d.error || '未知'))
    }
  } catch (e) { alert('请求失败: ' + e.message) }
}

async function addNewAuth() {
  showLoading('生成授权链接…')
  try {
    const d = await api('/yt-new-auth')
    if (d.url) {
      window.open(d.url, '_blank')
      alert('请在新窗口完成授权，回到此页面后列表将自动刷新。')
      await loadAccounts()
    }
  } catch (err) { console.error('[YouTube]', err) }
  finally { hideLoading() }
}

async function refreshAuth(slug) {
  if (!slug) return
  showLoading('生成授权链接…')
  try {
    const d = await api(`/yt-auth-url?slug=${encodeURIComponent(slug)}`)
    if (d.url) window.open(d.url, '_blank')
  } catch (err) { console.error('[YouTube]', err) }
  finally { hideLoading() }
}

onMounted(() => { loadAccounts() })
</script>

<style scoped>
.yt-channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.yt-analytics-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.yt-analytics-header h2 {
  margin-bottom: 0;
  font-size: 15px;
}
.yt-btn-row {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.yt-channel-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.yt-channel-card:hover {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}
.yt-channel-card--active {
  border-color: var(--accent);
  background: rgba(var(--accent-rgb, 78,205,196), 0.05);
}
</style>

<style>
/* YouTube page mobile overrides (unscoped for @media) */
@media (max-width: 768px) {
  .yt-channel-grid {
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 6px !important;
  }
  .yt-channel-card {
    padding: 10px !important;
  }
  .yt-channel-card img {
    width: 32px !important;
    height: 32px !important;
  }
  .yt-analytics-header {
    gap: 8px !important;
    margin-bottom: 12px !important;
  }
  .yt-analytics-header h2 {
    font-size: 13px !important;
    width: 100%;
  }
  .yt-analytics-header .tabs {
    flex: 1;
  }
  .yt-btn-row {
    gap: 6px !important;
    margin-bottom: 10px !important;
  }
  .yt-btn-row .btn {
    font-size: 11px !important;
    padding: 6px 10px !important;
  }
  /* Stats grid: 2 columns on mobile */
  .stats-grid {
    grid-template-columns: repeat(2, 1fr) !important;
    gap: 6px !important;
  }
  .stat-card {
    padding: 8px !important;
  }
  .stat-value {
    font-size: 15px !important;
  }
}
</style>
