<template>
  <div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <div>
        <h1>竞品频道分析</h1>
        <p class="page-desc">竞品频道深度分析 · 按时间排序 · 今日新增标记</p>
      </div>
      <button class="btn btn-secondary btn-sm" @click="load(true)" title="刷新数据">↻ 刷新</button>
    </div>

    <div class="tabs" style="margin-bottom:16px;">
      <div class="tab" :class="{ active: ccView === 'channels' }" @click="ccView = 'channels'">📊 频道列表</div>
      <div class="tab" :class="{ active: ccView === 'insights' }" @click="switchToInsights">🔬 市场洞察</div>
    </div>

    <!-- 频道列表 -->
    <div v-if="ccView === 'channels'">
      <div class="stats-grid">
        <div class="stat-card"><div class="stat-label">精选频道</div><div class="stat-value">{{ channels.length }}</div></div>
        <div v-for="(count, tier) in tierCounts" :key="tier" class="stat-card">
          <div class="stat-label">{{ tierLabels[tier] || tier }}</div>
          <div class="stat-value">{{ count }}</div>
        </div>
      </div>

      <!-- 筛选 -->
      <div class="card" style="margin-bottom:16px;">
        <div class="cc-filters">
          <div class="cc-filter-group">
            <span class="cc-filter-label" style="color:#f0c674;font-weight:600;">体量：</span>
            <span v-for="f in tierFilters" :key="f.k" class="cc-filter-btn" :class="{ active: filter.tier === f.k }" @click="filter.tier = f.k">{{ f.l }} ({{ f.n }})</span>
          </div>
          <div class="cc-filter-group">
            <span class="cc-filter-label" style="color:#81a2be;font-weight:600;">语种：</span>
            <span v-for="f in langFilters" :key="f.k" class="cc-filter-btn" :class="{ active: filter.lang === f.k }" @click="filter.lang = f.k">{{ f.l }} ({{ f.n }})</span>
          </div>
          <div class="cc-filter-group">
            <span class="cc-filter-label" style="color:#b294bb;font-weight:600;">地区：</span>
            <span v-for="f in countryFilters" :key="f.k" class="cc-filter-btn" :class="{ active: filter.country === f.k }" @click="filter.country = f.k">{{ f.l }} ({{ f.n }})</span>
          </div>
          <div class="cc-filter-group">
            <span class="cc-filter-label" style="color:#4ecdc4;font-weight:600;">标签：</span>
            <span v-for="f in tagFilters" :key="f.k" class="cc-filter-btn" :class="{ active: filter.tag === f.k }" @click="filter.tag = f.k">{{ f.l }} ({{ f.n }})</span>
          </div>
        </div>
      </div>

      <div style="font-size:12px;color:var(--text-muted);margin-bottom:10px;">显示 {{ filtered.length }} / {{ channels.length }} 个频道</div>
      <div v-if="!filtered.length" class="empty-state"><div class="icon">◌</div><div>暂无频道数据</div></div>
      <div class="cc-grid">
        <div v-for="c in filtered" :key="c.channel_id" class="cc-card fade-in" @click="selectedChannel = c">
          <img v-if="getThumb(c)" :src="getThumb(c)" class="cc-thumb" style="width:100%;height:80px;object-fit:cover;border-radius:6px 6px 0 0;margin:-14px -14px 10px -14px;width:calc(100% + 28px);" @error="$event.target.style.display='none'" />
          <div class="cc-card-top">
            <div class="cc-card-name"><a :href="safeChannelUrl(c.channel_id)" target="_blank" @click.stop>{{ c.name }}</a></div>
            <div style="display:flex;gap:4px;align-items:center;flex-shrink:0;">
              <span v-if="isNew(c)" style="background:#2ecc71;color:#fff;font-size:9px;padding:1px 5px;border-radius:3px;">NEW</span>
              <span style="font-size:9px;padding:1px 5px;border-radius:3px;color:#fff;" :style="{ background: tierColors[c.tier] || '#95a5a6' }">{{ tierLabels[c.tier] || c.tier }}</span>
            </div>
          </div>
          <div class="cc-card-stats">
            <div class="cc-stat"><div class="cc-stat-val" style="color:var(--accent);">{{ formatSubs(c.subscribers || 0) }}</div><div class="cc-stat-label">订阅</div></div>
            <div class="cc-stat"><div class="cc-stat-val" :style="{ color: getHitCount(c) > 0 ? '#2ecc71' : 'var(--text-dim)' }">{{ getHitCount(c) }}/{{ getVideoCount(c) }}</div><div class="cc-stat-label">爆款</div></div>
            <div class="cc-stat"><div class="cc-stat-val" style="font-size:11px;color:var(--accent3);">{{ c.language }}</div><div class="cc-stat-label">语种</div></div>
            <div class="cc-stat"><div class="cc-stat-val" style="font-size:11px;color:var(--accent2);">{{ countryNames[c.country] || c.language || '-' }}</div><div class="cc-stat-label">地区</div></div>
          </div>
          <!-- 追踪数据 -->
          <div v-if="hasTracking(c)" style="display:flex;gap:12px;margin-top:4px;font-size:10px;">
            <span v-if="c.tracking?.subs_change_day != null" :style="{ color: changeColor(c.tracking.subs_change_day) }">👥 {{ fmtChange(c.tracking.subs_change_day) }}/{{ fmtChange(c.tracking.subs_change_week) }}</span>
            <span v-if="c.tracking?.views_change_day != null" :style="{ color: changeColor(c.tracking.views_change_day) }">▶ {{ fmtChange(c.tracking.views_change_day) }}/{{ fmtChange(c.tracking.views_change_week) }}</span>
          </div>
          <div class="cc-tags">
            <span v-for="t in getChannelGenres(c).slice(0, 3)" :key="t" class="cc-tag">{{ t }}</span>
          </div>
          <!-- 顶部钩子 -->
          <div v-if="getTopHooks(c).length" style="margin-top:4px;">
            <span v-for="h in getTopHooks(c).slice(0,2)" :key="h" style="background:rgba(78,205,196,0.15);color:#4ecdc4;border:1px solid rgba(78,205,196,0.3);padding:1px 4px;border-radius:3px;font-size:9px;margin:1px;display:inline-block;">{{ h }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- 市场洞察 -->
    <div v-if="ccView === 'insights'">
      <div v-if="!miLangs.length" class="empty-state">加载中…</div>
      <div v-else>
        <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:20px;">
          <button v-for="(l, i) in miLangs" :key="l.language" class="cc-filter-btn" :class="{ active: miSelected === l.language }" @click="loadInsight(l.language)" style="padding:8px 16px;font-size:13px;">
            {{ langIcons[l.language] || '🌏' }} {{ l.language }} <span style="color:var(--text-muted);font-size:11px;">({{ l.channel_count }}频道)</span>
          </button>
        </div>
        <div v-if="miDetail">
          <div style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap;">
            <div class="stat-card" style="flex:1;min-width:140px;"><div class="stat-label">分析频道</div><div class="stat-value">{{ miDetail.channel_count || 0 }}</div></div>
            <div class="stat-card" style="flex:1;min-width:140px;"><div class="stat-label">模型</div><div class="stat-value" style="font-size:14px;">{{ miDetail.model || '-' }}</div></div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:14px;">
            <div v-for="section in insightSections" :key="section.key" class="card" style="margin-bottom:0;">
              <h3 style="margin:0 0 10px;font-size:14px;color:var(--text);">{{ section.icon }} {{ section.label }}</h3>
              <div v-if="section.type === 'text'" style="font-size:12px;color:var(--text-dim);line-height:1.6;">{{ section.value }}</div>
              <div v-if="section.type === 'list'" style="display:flex;flex-direction:column;gap:6px;">
                <div v-for="(item, idx) in section.items" :key="idx" style="font-size:12px;line-height:1.5;padding:6px 10px;background:var(--bg-elevated);border-radius:6px;border-left:3px solid;" :style="{ borderLeftColor: section.color }">
                  <span :style="{ color: section.color }">{{ item }}</span>
                </div>
              </div>
              <div v-if="section.type === 'tags'" style="display:flex;flex-wrap:wrap;gap:6px;">
                <span v-for="item in section.items" :key="item" style="padding:4px 10px;border-radius:4px;font-size:12px;font-weight:500;" :style="{ background: section.color + '18', color: section.color, border: `1px solid ${section.color}40` }">{{ item }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Channel Detail Modal -->
    <Transition name="fade">
      <div v-if="selectedChannel" style="position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.85);z-index:1000;overflow-y:auto;padding:20px;" @click.self="selectedChannel = null">
        <div style="max-width:750px;margin:30px auto;background:var(--bg-card);border-radius:12px;overflow:hidden;border:1px solid var(--border);">
          <!-- Banner Thumbnail -->
          <img v-if="getModalThumb(selectedChannel)" :src="getModalThumb(selectedChannel)" style="width:100%;height:200px;object-fit:cover;" @error="$event.target.style.display='none'" />
          <div style="padding:20px 24px;">
            <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:16px;">
              <div>
                <h2 style="margin:0;font-size:18px;">{{ selectedChannel.name }}</h2>
                <div style="margin-top:6px;display:flex;gap:8px;align-items:center;">
                  <span style="padding:2px 10px;border-radius:4px;font-size:12px;color:#fff;" :style="{ background: tierColors[selectedChannel.tier] || '#95a5a6' }">{{ tierLabels[selectedChannel.tier] || selectedChannel.tier }}</span>
                  <span style="color:var(--text-muted);font-size:13px;">{{ selectedChannel.language }}</span>
                  <a :href="safeChannelUrl(selectedChannel.channel_id)" target="_blank" style="color:var(--accent);font-size:12px;">↗ YouTube</a>
                </div>
              </div>
              <button @click="selectedChannel = null" style="background:none;border:none;color:var(--text-muted);font-size:24px;cursor:pointer;">✕</button>
            </div>

            <!-- 基础数据 -->
            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">
              <div style="text-align:center;background:var(--bg-elevated);padding:10px;border-radius:8px;">
                <div style="font-size:18px;color:var(--accent);font-weight:bold;">{{ formatSubs(selectedChannel.subscribers || 0) }}</div>
                <div style="font-size:11px;color:var(--text-dim);">订阅</div>
              </div>
              <div style="text-align:center;background:var(--bg-elevated);padding:10px;border-radius:8px;">
                <div style="font-size:18px;color:var(--accent3);font-weight:bold;">{{ formatSubs(selectedChannel.avg_views || selectedChannel.llm_stats?.avg_views || 0) }}</div>
                <div style="font-size:11px;color:var(--text-dim);">均播</div>
              </div>
              <div style="text-align:center;background:var(--bg-elevated);padding:10px;border-radius:8px;">
                <div style="font-size:18px;color:var(--accent2);font-weight:bold;">{{ selectedChannel.llm_stats?.breakout_count || getDeepHitCount(selectedChannel) }}</div>
                <div style="font-size:11px;color:var(--text-dim);">爆款(≥1万)</div>
              </div>
              <div style="text-align:center;background:var(--bg-elevated);padding:10px;border-radius:8px;">
                <div style="font-size:18px;color:var(--accent4);font-weight:bold;">{{ selectedChannel.total_videos || getDeepVideoCount(selectedChannel) }}</div>
                <div style="font-size:11px;color:var(--text-dim);">总视频</div>
              </div>
            </div>

            <!-- LLM Stats: 点赞率, 评论率, 平均时长 -->
            <div v-if="selectedChannel.llm_stats?.like_rate != null" style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:20px;">
              <div style="text-align:center;background:var(--bg-elevated);padding:10px;border-radius:8px;">
                <div style="font-size:16px;color:#e91e63;font-weight:bold;">{{ selectedChannel.llm_stats.like_rate.toFixed(2) }}%</div>
                <div style="font-size:11px;color:var(--text-dim);">点赞率</div>
              </div>
              <div style="text-align:center;background:var(--bg-elevated);padding:10px;border-radius:8px;">
                <div style="font-size:16px;color:#9c27b0;font-weight:bold;">{{ selectedChannel.llm_stats.comment_rate?.toFixed(3) || '0' }}%</div>
                <div style="font-size:11px;color:var(--text-dim);">评论率</div>
              </div>
              <div style="text-align:center;background:var(--bg-elevated);padding:10px;border-radius:8px;">
                <div style="font-size:16px;color:#00bcd4;font-weight:bold;">{{ formatDuration(selectedChannel.llm_stats.avg_duration_sec) }}</div>
                <div style="font-size:11px;color:var(--text-dim);">平均时长</div>
              </div>
            </div>

            <!-- 内容标签 -->
            <div v-if="getChannelGenres(selectedChannel).length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🏷️ 内容标签</h3>
              <span v-for="t in getChannelGenres(selectedChannel)" :key="t" style="display:inline-block;background:var(--bg-elevated);color:var(--text-dim);padding:3px 8px;border-radius:4px;font-size:12px;margin:2px;">{{ t }}</span>
            </div>

            <!-- 标题情感钩子 -->
            <div v-if="getModalHooks(selectedChannel).length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🎯 标题情感钩子</h3>
              <span v-for="h in getModalHooks(selectedChannel)" :key="h.name || h" style="display:inline-block;background:#1a3a2a;color:#4ecdc4;padding:3px 8px;border-radius:4px;font-size:12px;margin:2px;">{{ (h.name || h).split('(')[0] }} {{ h.count ? '×' + h.count : '' }}</span>
            </div>

            <!-- 标题结构模式 -->
            <div v-if="getModalStructures(selectedChannel).length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">📐 标题结构模式</h3>
              <span v-for="s in getModalStructures(selectedChannel)" :key="s.name || s" style="display:inline-block;background:#2a1a3a;color:#a78bfa;padding:3px 8px;border-radius:4px;font-size:12px;margin:2px;">{{ s.name || s }} {{ s.count ? '×' + s.count : '' }}</span>
            </div>

            <!-- 故事主题 -->
            <div v-if="getModalThemes(selectedChannel).length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">📖 故事主题</h3>
              <span v-for="t in getModalThemes(selectedChannel)" :key="t.name || t" style="display:inline-block;background:#3a2a1a;color:#fbbf24;padding:3px 8px;border-radius:4px;font-size:12px;margin:2px;">{{ t.name || t }} {{ t.count ? '×' + t.count : '' }}</span>
            </div>

            <!-- 具体分析 -->
            <div v-if="getAnalysisTexts(selectedChannel).length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">📊 具体分析</h3>
              <div v-for="(a, i) in getAnalysisTexts(selectedChannel)" :key="i" style="color:#4ecdc4;font-size:13px;padding:4px 0;">→ {{ a }}</div>
            </div>

            <!-- 增长特征 -->
            <div v-if="getGrowthReasons(selectedChannel).length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">📈 增长特征</h3>
              <div v-for="(r, i) in getGrowthReasons(selectedChannel)" :key="i" style="color:var(--text-muted);font-size:13px;padding:3px 0;">• {{ r }}</div>
            </div>

            <!-- 增长归因 LLM -->
            <div v-if="selectedChannel.llm_distill?.why?.growth_drivers?.length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🧠 增长归因（LLM）</h3>
              <div v-for="d in selectedChannel.llm_distill.why.growth_drivers" :key="d" style="color:#4ecdc4;font-size:13px;padding:3px 0;">• {{ d }}</div>
            </div>

            <!-- 受众画像 -->
            <div v-if="selectedChannel.llm_distill?.why?.audience_fit" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">👥 受众画像</h3>
              <div style="color:var(--text-muted);font-size:13px;">{{ selectedChannel.llm_distill.why.audience_fit }}</div>
            </div>

            <!-- 频道阶段 -->
            <div v-if="selectedChannel.llm_distill?.why?.trajectory" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">📊 频道阶段</h3>
              <div style="color:var(--text-muted);font-size:13px;">{{ selectedChannel.llm_distill.why.trajectory }}</div>
            </div>

            <!-- 内容策略 -->
            <div v-if="selectedChannel.llm_distill?.what?.content_strategy" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🎯 内容策略</h3>
              <div style="color:#fbbf24;font-size:13px;">{{ selectedChannel.llm_distill.what.content_strategy }}</div>
            </div>

            <!-- 主打题材 -->
            <div v-if="selectedChannel.llm_distill?.what?.top_themes?.length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🔥 主打题材</h3>
              <span v-for="t in selectedChannel.llm_distill.what.top_themes" :key="t" style="display:inline-block;background:rgba(251,191,36,0.1);color:#fbbf24;padding:3px 8px;border-radius:4px;font-size:12px;margin:2px;">{{ t }}</span>
            </div>

            <!-- 标题公式 -->
            <div v-if="selectedChannel.llm_distill?.what?.title_formulas?.length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">📝 标题公式</h3>
              <div v-for="f in selectedChannel.llm_distill.what.title_formulas" :key="f" style="color:#a78bfa;font-size:13px;padding:3px 0;">• {{ f }}</div>
            </div>

            <!-- 钩子模式 -->
            <div v-if="selectedChannel.llm_distill?.what?.hook_patterns?.length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🪝 钩子模式</h3>
              <div v-for="h in selectedChannel.llm_distill.what.hook_patterns" :key="h" style="color:#4ecdc4;font-size:13px;padding:3px 0;">• {{ h }}</div>
            </div>

            <!-- 互动分析 -->
            <div v-if="selectedChannel.llm_distill?.what?.engagement_insight" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">💬 互动分析</h3>
              <div style="color:var(--text-muted);font-size:13px;">{{ selectedChannel.llm_distill.what.engagement_insight }}</div>
            </div>

            <!-- 视频详情 -->
            <div v-if="getVideoList(selectedChannel).length" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🎬 视频详情（含封面）</h3>
              <div v-for="(v, i) in getVideoList(selectedChannel)" :key="i" style="display:flex;gap:12px;padding:12px 0;border-bottom:1px solid var(--border);">
                <img v-if="v.thumbnail" :src="v.thumbnail" style="width:160px;height:90px;object-fit:cover;border-radius:6px;flex-shrink:0;" @error="$event.target.style.display='none'" />
                <div style="flex:1;min-width:0;">
                  <div style="font-size:13px;color:var(--text);line-height:1.4;max-height:2.8em;overflow:hidden;">{{ v.title || '' }}</div>
                  <div style="margin-top:6px;display:flex;gap:12px;font-size:12px;color:var(--text-dim);">
                    <span v-if="v.views || v.view_count">▶ {{ formatSubs(v.views || v.view_count) }}</span>
                    <span v-if="v.likes || v.like_count">👍 {{ formatSubs(v.likes || v.like_count) }}</span>
                    <span v-if="v.comments || v.comment_count">💬 {{ v.comments || v.comment_count }}</span>
                  </div>
                  <div v-if="v.tags?.length" style="margin-top:4px;">
                    <span v-for="t in v.tags.slice(0,3)" :key="t" style="background:var(--bg-elevated);color:var(--text-dim);padding:1px 4px;border-radius:3px;font-size:10px;margin:1px;display:inline-block;">{{ t }}</span>
                  </div>
                  <div v-if="v.title_analysis?.emotion_hooks?.length" style="margin-top:4px;">
                    <span v-for="h in v.title_analysis.emotion_hooks" :key="h" style="background:#1a3a2a;color:#4ecdc4;padding:1px 4px;border-radius:3px;font-size:10px;display:inline-block;">{{ h }}</span>
                  </div>
                </div>
              </div>
            </div>

            <!-- 搜索热度 -->
            <div v-if="selectedChannel.search_views" style="margin-bottom:16px;">
              <h3 style="color:var(--text);font-size:13px;margin-bottom:8px;">🔍 搜索热度</h3>
              <div style="color:var(--accent);font-size:16px;">{{ formatSubs(selectedChannel.search_views) }}</div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, reactive, onMounted } from 'vue'
import { api, invalidateCache } from '../api/index.js'
import { formatSubs, formatNumber, safeChannelUrl } from '../utils.js'

const ccView = ref('channels')
const channels = ref([])
const selectedChannel = ref(null)
const filter = reactive({ tier: 'all', time: 'all', lang: 'all', country: 'all', tag: 'all' })
const miLangs = ref([])
const miSelected = ref('')
const miDetail = ref(null)

const tierLabels = { top: '顶级', head: '头部', mid: '中部', rising: '起步', new: '新号', micro: '微型' }
const tierColors = { top: '#e74c3c', head: '#e74c3c', mid: '#f39c12', rising: '#2ecc71', new: '#3498db', micro: '#9b59b6' }
const langIcons = { '印尼': '🇮🇩', '英文': '🇺🇸', '繁中': '🇹🇼', '西语': '🇪🇸', '葡萄牙': '🇧🇷' }
const countryNames = { US: '美国', ID: '印尼', TW: '台湾', JP: '日本', ES: '西班牙', SG: '新加坡', HK: '香港', PT: '葡萄牙', CA: '加拿大', GB: '英国', BR: '巴西', MX: '墨西哥', AU: '澳洲', CN: '中国' }

// Channel genres: LLM题材优先，fallback到content_tags
function getChannelGenres(ch) {
  if (!ch) return []
  const llm = ch.llm_distill?.what?.top_themes || []
  if (llm.length) return llm
  return ch.content_tags || ch.genres || (ch.tags || []).filter(t => !['short drama', 'drama', 'shorts'].includes(t.toLowerCase()))
}

function isNew(c) {
  const today = new Date().toISOString().slice(0, 10)
  return (c.analyzed_at || '').startsWith(today)
}

function getThumb(c) {
  return c.thumbnail_url || c.sample_videos?.[0]?.thumbnail || c.top_covers?.[0]?.thumbnail || c.videos?.[0]?.thumbnail || ''
}

function getModalThumb(ch) {
  return ch.thumbnail_url || ch.sample_videos?.[0]?.thumbnail || ch.recent_week_videos?.[0]?.thumbnail || ch.top_covers?.[0]?.thumbnail || ch.videos?.[0]?.thumbnail || ''
}

function getHitCount(c) {
  const da = c.deep_analysis || {}
  const va = c.video_analysis || {}
  return da.hit_count || va.breakout_count || 0
}

function getVideoCount(c) {
  const da = c.deep_analysis || {}
  const va = c.video_analysis || {}
  return da.video_count || va.total_videos || c.total_videos || 0
}

function getDeepHitCount(ch) {
  const da = ch.deep_analysis || {}
  const va = ch.video_analysis || {}
  return da.hit_count || va.breakout_count || 0
}

function getDeepVideoCount(ch) {
  const da = ch.deep_analysis || {}
  const va = ch.video_analysis || {}
  return da.video_count || va.total_videos || 0
}

function hasTracking(c) {
  const tk = c.tracking || {}
  return tk.subs_change_day != null || tk.views_change_day != null
}

function fmtChange(v) {
  if (v == null) return ''
  return v >= 0 ? '+' + formatNumber(v) : formatNumber(v)
}

function changeColor(v) {
  if (v == null) return ''
  return v >= 0 ? 'var(--success)' : 'var(--danger)'
}

function getTopHooks(c) {
  const da = c.deep_analysis || {}
  const ta = c.title_analysis || {}
  const hooks = da.top_hooks || Object.entries(ta.hooks || {}).flatMap(([k, v]) => v.map(h => ({ name: h, count: 1 })))
  return hooks.map(h => (h.name || h).split('(')[0])
}

function getModalHooks(ch) {
  const da = ch.deep_analysis || {}
  const ta = ch.title_analysis || {}
  return da.top_hooks || Object.entries(ta.hooks || {}).flatMap(([k, v]) => v.map(h => ({ name: h, count: 1 })))
}

function getModalStructures(ch) {
  const da = ch.deep_analysis || {}
  const ta = ch.title_analysis || {}
  return da.title_structures || Object.entries(ta.structures || {}).map(([k, v]) => ({ name: k, count: v }))
}

function getModalThemes(ch) {
  const da = ch.deep_analysis || {}
  return da.story_themes || []
}

function getAnalysisTexts(ch) {
  return ch.analysis_text || ch.growth_reasons || []
}

function getGrowthReasons(ch) {
  return ch.growth_reasons || []
}

function getVideoList(ch) {
  const va = ch.video_analysis || {}
  return ch.videos_detail || va.top_videos || []
}

function formatDuration(sec) {
  if (!sec) return '-'
  return Math.floor(sec / 60) + ':' + String(sec % 60).padStart(2, '0')
}

const tierCounts = computed(() => {
  const t = {}
  channels.value.forEach(c => { t[c.tier] = (t[c.tier] || 0) + 1 })
  return t
})
const todayCount = computed(() => {
  const today = new Date().toISOString().slice(0, 10)
  return channels.value.filter(c => (c.analyzed_at || '').startsWith(today)).length
})
const tierFilters = computed(() => {
  const t = tierCounts.value
  return [
    { k: 'all', l: '全部', n: channels.value.length },
    ...Object.entries(t).map(([k, v]) => ({ k, l: tierLabels[k] || k, n: v }))
  ]
})
const langFilters = computed(() => {
  const l = {}
  channels.value.forEach(c => { l[c.language] = (l[c.language] || 0) + 1 })
  return [{ k: 'all', l: '全部', n: channels.value.length }, ...Object.entries(l).map(([k, v]) => ({ k, l: k, n: v }))]
})
const countryFilters = computed(() => {
  const co = {}
  channels.value.forEach(c => { if (c.country) co[c.country] = (co[c.country] || 0) + 1 })
  return [{ k: 'all', l: '全部', n: channels.value.length }, ...Object.entries(co).sort((a, b) => b[1] - a[1]).map(([k, v]) => ({ k, l: countryNames[k] || k, n: v }))]
})
const tagFilters = computed(() => {
  const tags = {}
  channels.value.forEach(c => {
    getChannelGenres(c).forEach(t => { tags[t] = (tags[t] || 0) + 1 })
  })
  const topTags = Object.entries(tags).sort((a, b) => b[1] - a[1]).slice(0, 10)
  return [{ k: 'all', l: '全部', n: channels.value.length }, ...topTags.map(([k, v]) => ({ k, l: k, n: v }))]
})
const filtered = computed(() => {
  let r = [...channels.value]
  const today = new Date().toISOString().slice(0, 10)
  if (filter.time === 'today') r = r.filter(c => (c.analyzed_at || '').startsWith(today))
  r.sort((a, b) => (b.analyzed_at || '').localeCompare(a.analyzed_at || ''))
  if (filter.tier !== 'all') r = r.filter(c => c.tier === filter.tier)
  if (filter.lang !== 'all') r = r.filter(c => c.language === filter.lang)
  if (filter.country !== 'all') r = r.filter(c => c.country === filter.country)
  if (filter.tag !== 'all') r = r.filter(c => getChannelGenres(c).includes(filter.tag))
  return r
})

async function load(force = false) {
  if (channels.value.length && !force) return
  if (force) invalidateCache('/competitor-channels')
  try {
    const d = await api('/competitor-channels')
    channels.value = d.channels || []
  } catch (err) { console.error('[CompetitorChannels]', err) }
}

async function switchToInsights() {
  ccView.value = 'insights'
  if (!miLangs.value.length) {
    try {
      const d = await api('/market-insights')
      miLangs.value = d.languages || []
      if (miLangs.value.length) loadInsight(miLangs.value[0].language)
    } catch (err) { console.error('[CompetitorChannels]', err) }
  }
}

async function loadInsight(lang) {
  miSelected.value = lang
  try {
    miDetail.value = await api(`/market-insights?lang=${encodeURIComponent(lang)}`)
  } catch (err) { console.error('[CompetitorChannels]', err) }
}

const insightSections = computed(() => {
  if (!miDetail.value) return []
  const ins = miDetail.value.insights || {}
  const w = ins.what_they_watch || {}
  const t = ins.titles_and_hooks || {}
  const c = ins.covers_and_visuals || {}
  const f = ins.future_opportunities || {}
  const tk = ins.takeaways || {}
  const comp = ins.competition || {}
  const sections = []
  // 观看偏好
  if (w.top_genres?.length) sections.push({ key: 'genres', icon: '🎬', label: '热门题材', type: 'list', items: w.top_genres.map(g => `${g.genre} — ${g.popularity}`), color: '#f0c674' })
  if (w.rising_genres?.length) sections.push({ key: 'rising', icon: '📈', label: '新兴题材', type: 'list', items: w.rising_genres.map(g => `${g.genre}: ${g.trend}`), color: '#8f9d6a' })
  if (w.declining_genres?.length) sections.push({ key: 'declining', icon: '📉', label: '衰退题材', type: 'list', items: w.declining_genres, color: '#cc6666' })
  if (w.audience_notes) sections.push({ key: 'audience', icon: '👥', label: '受众画像', type: 'text', value: w.audience_notes })
  // 标题钩子
  if (t.winning_formulas?.length) sections.push({ key: 'formulas', icon: '🪝', label: '标题公式', type: 'list', items: t.winning_formulas, color: '#b294bb' })
  if (t.top_hook_words?.length) sections.push({ key: 'hooks', icon: '🔤', label: '高频钩子词', type: 'tags', items: t.top_hook_words, color: '#ec4899' })
  if (t.language_mix) sections.push({ key: 'lang_mix', icon: '🌐', label: '语言策略', type: 'text', value: t.language_mix })
  if (t.hook_analysis) sections.push({ key: 'hook_analysis', icon: '🔍', label: '钩子分析', type: 'text', value: t.hook_analysis })
  // 封面视觉
  if (c.cover_styles?.length) sections.push({ key: 'covers', icon: '🎨', label: '封面风格', type: 'list', items: c.cover_styles, color: '#fbbf24' })
  if (c.what_works) sections.push({ key: 'cover_works', icon: '✅', label: '封面成功要素', type: 'text', value: c.what_works })
  if (c.common_elements?.length) sections.push({ key: 'cover_elements', icon: '🧩', label: '封面常见元素', type: 'tags', items: c.common_elements, color: '#f59e0b' })
  // 竞争格局
  if (comp.top_channels?.length) sections.push({ key: 'top_channels', icon: '🏆', label: '头部频道', type: 'list', items: comp.top_channels.map(ch => `${ch.name}: ${ch.why_top}`), color: '#81a2be' })
  if (comp.emerging_channels?.length) sections.push({ key: 'emerging', icon: '🌱', label: '新兴频道', type: 'list', items: comp.emerging_channels.map(ch => `${ch.name}: ${ch.why_watch}`), color: '#8f9d6a' })
  if (comp.content_gaps?.length) sections.push({ key: 'gaps', icon: '💡', label: '内容空白', type: 'list', items: comp.content_gaps, color: '#10b981' })
  // 未来机会
  if (f.localization_potential?.length) sections.push({ key: 'localization', icon: '🌍', label: '本土化机会', type: 'list', items: f.localization_potential, color: '#f59e0b' })
  if (f.cultural_fusion?.length) sections.push({ key: 'cultural', icon: '🎭', label: '文化融合', type: 'list', items: f.cultural_fusion, color: '#a855f7' })
  if (f.emerging_themes?.length) sections.push({ key: 'themes', icon: '🚀', label: '新兴主题', type: 'list', items: f.emerging_themes, color: '#8b5cf6' })
  if (f.subculture_narratives?.length) sections.push({ key: 'subculture', icon: '📖', label: '亚文化叙事', type: 'list', items: f.subculture_narratives, color: '#ec4899' })
  // 行动建议
  if (tk.if_entering_now?.length) sections.push({ key: 'takeaways', icon: '📋', label: '入场建议', type: 'list', items: tk.if_entering_now, color: '#f0c674' })
  if (tk.avoid?.length) sections.push({ key: 'avoid', icon: '⚠️', label: '避坑指南', type: 'list', items: tk.avoid, color: '#cc6666' })
  return sections
})

onMounted(() => { load() })
</script>
