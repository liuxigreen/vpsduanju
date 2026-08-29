<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <div>
        <h1 style="margin:0;">今日简报</h1>
        <p class="page-desc">竞品预警 · 24h增量热榜 · 自有频道昨日表现 · 一屏看完</p>
      </div>
      <button class="btn btn-secondary btn-sm" @click="load" title="刷新">↻ 刷新</button>
    </div>

    <div v-if="loading" style="color:var(--text-muted)">加载中…</div>

    <div v-else-if="!brief" class="empty-state">暂无简报数据</div>

    <div v-else>
      <!-- 顶部统计条 -->
      <div class="stats-grid" style="margin-bottom:20px;">
        <div class="stat-card">
          <div class="stat-value" :style="brief.alerts?.length ? 'color:var(--accent4)' : ''">{{ brief.alerts?.length || 0 }}</div>
          <div class="stat-label">🔔 竞品爆款预警</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ brief.top_rising?.length || 0 }}</div>
          <div class="stat-label">📈 24h增量热榜</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">{{ ownRows.length }}</div>
          <div class="stat-label">📊 自有频道（{{ brief.report_date || '-' }}）</div>
        </div>
        <div class="stat-card">
          <div class="stat-value" :style="totalCritical ? 'color:var(--accent4)' : ''">{{ totalCritical }}</div>
          <div class="stat-label">🚨 严重问题数</div>
        </div>
      </div>

      <!-- 预警列表 -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <h2 style="margin:0;">🔔 竞品爆款预警</h2>
          <router-link to="/competitor-alerts" style="font-size:12px;color:var(--accent);">查看全部 →</router-link>
        </div>
        <div v-if="!brief.alerts?.length" style="color:var(--text-muted);font-size:13px;">
          今日无预警（基线建立后每天 08:30 自动扫描）
        </div>
        <div v-for="(a, i) in brief.alerts" :key="i"
             style="display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--border-subtle);font-size:13px;">
          <span>{{ a.type === 'breakout' ? '🚀' : a.type === 'spike' ? '⚡' : '🌱' }}</span>
          <span style="flex:1;color:var(--text);">{{ a.video_title || a.title || '' }}</span>
          <span style="color:var(--text-dim);">{{ a.channel_name || a.channel || '' }}</span>
          <span style="color:var(--accent4);font-weight:600;">+{{ fmt(a.delta_24h ?? a.views_delta) }}</span>
        </div>
      </div>

      <!-- 24h 热榜前3 -->
      <div class="card" style="margin-bottom:16px;">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <h2 style="margin:0;">📈 24h 增量热榜 TOP3</h2>
          <router-link to="/competitor-alerts" style="font-size:12px;color:var(--accent);">完整榜单 →</router-link>
        </div>
        <div v-if="!brief.top_rising?.length" style="color:var(--text-muted);font-size:13px;">
          暂无增量数据（8/30 起每天更新）
        </div>
        <div v-for="(r, i) in brief.top_rising" :key="i"
             style="display:flex;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--border-subtle);font-size:13px;">
          <span style="font-weight:700;color:var(--accent2);">#{{ i + 1 }}</span>
          <span style="flex:1;color:var(--text);">{{ r.video_title || r.title || '' }}</span>
          <span style="color:var(--text-dim);">{{ r.channel_name || r.channel || '' }}</span>
          <span style="color:var(--accent2);font-weight:600;">+{{ fmt(r.delta_24h ?? r.views_delta ?? r.delta) }}</span>
        </div>
      </div>

      <!-- 自有频道表 -->
      <div class="card">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <h2 style="margin:0;">📊 自有频道昨日表现</h2>
          <router-link to="/channel-analysis" style="font-size:12px;color:var(--accent);">深度诊断 →</router-link>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:13px;">
          <thead>
            <tr style="text-align:left;color:var(--text-dim);border-bottom:1px solid var(--border);">
              <th style="padding:6px 8px;">频道</th>
              <th style="padding:6px 8px;">语种</th>
              <th style="padding:6px 8px;text-align:right;">日播放</th>
              <th style="padding:6px 8px;text-align:right;">日增订阅</th>
              <th style="padding:6px 8px;text-align:right;">总订阅</th>
              <th style="padding:6px 8px;">健康度</th>
              <th style="padding:6px 8px;text-align:right;">严重问题</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in ownRows" :key="c.name" style="border-bottom:1px solid var(--border-subtle);">
              <td style="padding:6px 8px;color:var(--text);">{{ c.name }}</td>
              <td style="padding:6px 8px;color:var(--text-dim);">{{ c.language }}</td>
              <td style="padding:6px 8px;text-align:right;">{{ fmt(c.daily_views) }}</td>
              <td style="padding:6px 8px;text-align:right;">{{ c.daily_subs ?? '-' }}</td>
              <td style="padding:6px 8px;text-align:right;color:var(--text-dim);">{{ fmt(c.subs) }}</td>
              <td style="padding:6px 8px;">
                <span :style="healthStyle(c.health)">{{ c.health || '-' }}</span>
              </td>
              <td style="padding:6px 8px;text-align:right;">
                <span v-if="c.critical_issues" style="color:var(--accent4);font-weight:700;">{{ c.critical_issues }}</span>
                <span v-else style="color:var(--text-muted);">0</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'

const loading = ref(true)
const brief = ref(null)

const ownRows = computed(() => brief.value?.own_channels || [])
const totalCritical = computed(() => ownRows.value.reduce((s, c) => s + (c.critical_issues || 0), 0))

function fmt(n) {
  if (n === null || n === undefined) return '-'
  if (n >= 10000) return (n / 10000).toFixed(1) + '万'
  if (n >= 1000) return (n / 1000).toFixed(1) + 'k'
  return String(n)
}

function healthStyle(h) {
  if (!h) return { color: 'var(--text-muted)' }
  if (h.includes('健康') || h.includes('良')) return { color: 'var(--accent2)' }
  if (h.includes('差') || h.includes('危险')) return { color: 'var(--accent4)' }
  return { color: 'var(--text-dim)' }
}

async function load() {
  loading.value = true
  try {
    const d = await api('/dashboard')
    brief.value = d.today_brief || null
  } catch (e) {
    console.error(e)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>
