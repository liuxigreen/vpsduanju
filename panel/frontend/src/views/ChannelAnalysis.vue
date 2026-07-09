<template>
  <div>
    <div class="ca-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
      <div>
        <h1>📊 自有账号分析</h1>
        <p class="page-desc">6账号全维度对比 · 日环比 · 周对比 · 异常提醒</p>
      </div>
      <div class="tabs" style="margin-bottom:0;">
        <div class="tab" :class="{ active: view === 'overview' }" @click="view = 'overview'">总览</div>
        <div class="tab" :class="{ active: view === 'daily' }" @click="view = 'daily'">日报</div>
      </div>
    </div>

    <div v-if="loading" class="empty-state">加载中...</div>

    <Transition name="fade">
      <div v-if="!loading && channels.length">
        <!-- ═══ 总览 ═══ -->
        <div v-if="view === 'overview'">
          <div class="stats-grid">
            <!-- 总订阅 -->
            <div class="stat-card">
              <div class="stat-value" style="color:var(--accent)">{{ totalSubs.toLocaleString() }}</div>
              <div class="stat-label">总订阅</div>
              <div v-if="weeklySubGain" :style="{ color: weeklySubGain > 0 ? 'var(--success)' : 'var(--danger)', fontSize: '12px', fontWeight: 600 }">
                {{ weeklySubGain > 0 ? '+' : '' }}{{ weeklySubGain.toLocaleString() }}
              </div>
              <div v-if="weeklySubGain" style="font-size:10px;color:var(--text-muted)">本周</div>
            </div>
            <!-- 总播放 -->
            <div class="stat-card">
              <div class="stat-value" style="color:var(--accent3)">{{ totalViews.toLocaleString() }}</div>
              <div class="stat-label">总播放</div>
              <div v-if="weeklyViewGain" :style="{ color: weeklyViewGain > 0 ? 'var(--success)' : 'var(--danger)', fontSize: '12px', fontWeight: 600 }">
                {{ weeklyViewGain > 0 ? '+' : '' }}{{ weeklyViewGain.toLocaleString() }}
              </div>
              <div v-if="weeklyViewGain" style="font-size:10px;color:var(--text-muted)">本周</div>
            </div>
            <!-- 平均留存率（圆环图） -->
            <div class="stat-card" style="display:flex;align-items:center;gap:12px;">
              <div :style="retentionRingStyle(avgRetention)" style="width:52px;height:52px;border-radius:50%;flex-shrink:0;position:relative;">
                <div style="position:absolute;inset:6px;background:var(--bg-card,#1a1f2e);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:var(--text);">{{ avgRetention }}%</div>
              </div>
              <div>
                <div class="stat-label" style="margin-bottom:2px;">平均留存</div>
                <div style="font-size:10px;color:var(--text-muted);">已授权 {{ oauthChannelCount }} 频道</div>
              </div>
            </div>
            <!-- 平均观看时长 -->
            <div class="stat-card">
              <div class="stat-value" style="color:var(--accent2)">{{ avgWatchDuration }}</div>
              <div class="stat-label">平均观看时长</div>
              <div style="font-size:10px;color:var(--text-muted);">已授权频道均值</div>
            </div>
            <!-- 30天净增粉 -->
            <div class="stat-card">
              <div class="stat-value" :style="{ color: totalNetSubs >= 0 ? 'var(--success)' : 'var(--danger)' }">{{ totalNetSubs >= 0 ? '+' : '' }}{{ totalNetSubs.toLocaleString() }}</div>
              <div class="stat-label">30天净增粉</div>
              <div style="font-size:10px;color:var(--text-muted);">已授权频道合计</div>
            </div>
            <!-- 异常频道 -->
            <div class="stat-card">
              <div class="stat-value" :style="{ color: anomalyCount > 0 ? 'var(--danger)' : 'var(--success)' }">{{ anomalyCount }}</div>
              <div class="stat-label">异常频道</div>
              <div style="font-size:10px;color:var(--text-muted);">{{ anomalyCount > 0 ? '需关注' : '全部正常' }}</div>
            </div>
          </div>

          <!-- 核心数据总览表格 -->
          <div class="card" style="margin-top:20px;">
          <div class="card-header">
            <div class="card-title">📋 核心数据总览</div>
            <div class="card-desc" style="font-size:12px;color:var(--text-muted)">报告日期: {{ data.report_date }} <span v-if="oauthChannelCount > 0" style="color:var(--success);margin-left:8px;">🔑 {{ oauthChannelCount }} 频道已授权深度数据</span></div>
          </div>
          <div style="overflow-x:auto">
            <table class="data-table" style="font-size:12px;">
              <thead><tr>
                <th class="sticky-col sticky-col-1">频道</th><th>语种</th>
                <th class="num">订阅</th><th class="num">播放</th>
                <th class="num" style="color:var(--accent2)">观看时长</th>
                <th class="num" style="color:var(--accent2)">留存%</th>
                <th class="num" style="color:var(--accent2)">净增粉</th>
                <th>状态</th>
              </tr></thead>
              <tbody>
                <template v-for="(c, idx) in channels" :key="c.name">
                <tr style="cursor:pointer" @click="toggleDetail(idx)">
                  <td class="sticky-col sticky-col-1" style="font-weight:600;">
                    <span :style="{ display: 'inline-block', transition: 'transform 0.2s', fontSize: '10px', marginRight: '4px', transform: expanded.has(idx) ? 'rotate(90deg)' : 'rotate(0)' }">▶</span>
                    {{ c.name }}
                  </td>
                  <td>{{ c.language || '-' }}</td>
                  <td class="num" style="color:var(--accent);font-weight:600;">{{ c.subscribers.toLocaleString() }}</td>
                  <td class="num" style="color:var(--accent3);">{{ c.total_views.toLocaleString() }}</td>
                  <td class="num" style="font-weight:600;">
                    {{ c.oauth?.authorized && c.oauth?.avg_view_duration ? formatDuration(c.oauth.avg_view_duration) : '—' }}
                  </td>
                  <td class="num">
                    <template v-if="c.oauth?.authorized && c.oauth?.avg_view_pct">
                      <span :style="{ display:'inline-block', width:'8px', height:'8px', borderRadius:'50%', background: retentionColor(c.oauth.avg_view_pct) === 'var(--success)' ? '#4caf50' : retentionColor(c.oauth.avg_view_pct) === 'var(--accent)' ? '#ff9800' : '#f44336', marginRight: '4px' }"></span>
                      <span style="font-weight:700;" :style="{ color: retentionColor(c.oauth.avg_view_pct) }">{{ c.oauth.avg_view_pct }}%</span>
                    </template>
                    <span v-else style="color:var(--text-dim);">—</span>
                  </td>
                  <td class="num" style="font-weight:700;">
                    <template v-if="c.oauth?.authorized">
                      <span :style="{ color: (c.oauth.subs_gained_30d - c.oauth.subs_lost_30d) >= 0 ? 'var(--success)' : 'var(--danger)' }">
                        {{ c.oauth.subs_gained_30d - c.oauth.subs_lost_30d >= 0 ? '↑' : '↓' }}{{ Math.abs(c.oauth.subs_gained_30d - c.oauth.subs_lost_30d) }}
                      </span>
                    </template>
                    <span v-else style="color:var(--text-dim);">—</span>
                  </td>
                  <td><span :style="{ fontSize: '11px', color: healthColor(c.health) }">{{ c.health || '-' }}</span></td>
                </tr>
                <!-- 展开详情行 -->
                <tr v-if="expanded.has(idx)" :key="'detail-' + c.name">
                  <td colspan="8" style="padding:0;background:var(--bg-elevated,#1a1f2e);border-top:1px solid var(--border-subtle);">
                    <div style="padding:16px;">
                      <div style="font-size:13px;font-weight:600;color:var(--text);margin-bottom:12px;">📊 {{ c.name }} — 诊断详情</div>

                      <!-- 诊断卡片行 -->
                      <div style="display:flex;gap:12px;margin-bottom:12px;flex-wrap:wrap;align-items:flex-start;">
                        <div style="display:flex;gap:10px;">
                          <div style="padding:8px 16px;background:var(--bg-card,#222);border-radius:6px;text-align:center;border:1px solid var(--border);">
                            <div style="font-size:20px;font-weight:700;" :style="{ color: scoreColor(diagScores[c.name]?.avg_score || diagScores[c.name]?.avg || 0) }">{{ (diagScores[c.name]?.avg_score || diagScores[c.name]?.avg || 0).toFixed(1) }}</div>
                            <div style="font-size:11px;color:var(--text-secondary)">诊断均分</div>
                          </div>
                          <div style="padding:8px 16px;background:var(--bg-card,#222);border-radius:6px;text-align:center;border:1px solid var(--border);">
                            <div style="font-size:20px;font-weight:700;" :style="{ color: (diagScores[c.name]?.needs_optimization || 0) > 0 ? 'var(--danger)' : 'var(--success)' }">{{ diagScores[c.name]?.needs_optimization || 0 }}/{{ diagScores[c.name]?.total_videos || 0 }}</div>
                            <div style="font-size:11px;color:var(--text-secondary)">需优化</div>
                          </div>
                          <template v-if="c.oauth?.authorized">
                            <div style="padding:8px 16px;background:var(--bg-card,#222);border-radius:6px;text-align:center;border:1px solid var(--accent2);">
                              <div style="font-size:20px;font-weight:700;color:var(--accent2);">{{ c.oauth.avg_view_pct }}%</div>
                              <div style="font-size:11px;color:var(--text-secondary)">平均留存</div>
                            </div>
                            <div style="padding:8px 16px;background:var(--bg-card,#222);border-radius:6px;text-align:center;border:1px solid var(--accent2);">
                              <div style="font-size:20px;font-weight:700;color:var(--accent2);">{{ formatWatchTime(c.oauth.watch_minutes_30d) }}</div>
                              <div style="font-size:11px;color:var(--text-secondary)">观看时长</div>
                            </div>
                            <div style="padding:8px 16px;background:var(--bg-card,#222);border-radius:6px;text-align:center;border:1px solid var(--accent2);">
                              <div style="font-size:20px;font-weight:700;" :style="{ color: (c.oauth.subs_gained_30d - c.oauth.subs_lost_30d) > 0 ? 'var(--success)' : 'var(--danger)' }">{{ c.oauth.subs_gained_30d - c.oauth.subs_lost_30d > 0 ? '+' : '' }}{{ c.oauth.subs_gained_30d - c.oauth.subs_lost_30d }}</div>
                              <div style="font-size:11px;color:var(--text-secondary)">30天净增粉</div>
                            </div>
                            <div style="padding:8px 16px;background:var(--bg-card,#222);border-radius:6px;text-align:center;border:1px solid var(--accent2);">
                              <div style="font-size:20px;font-weight:700;color:var(--accent2);">{{ effPerK(c.oauth) }}</div>
                              <div style="font-size:11px;color:var(--text-secondary)">千播订</div>
                            </div>
                          </template>
                        </div>
                      </div>

                      <!-- YPP 数据卡片 -->
                      <div style="margin-bottom:14px;padding:12px;background:var(--bg-card,#222);border-radius:8px;border:1px solid var(--border);">
                        <div style="font-size:11px;font-weight:600;color:var(--accent);margin-bottom:8px;">🔐 YPP 数据（需合作伙伴计划）</div>
                        <div style="display:flex;gap:8px;flex-wrap:wrap;">
                          <div v-for="item in yppMetrics(c)" :key="item.label" style="display:flex;align-items:center;gap:6px;padding:4px 10px;background:rgba(255,255,255,0.03);border-radius:4px;font-size:11px;">
                            <span>{{ item.label }}</span>
                            <span v-if="item.ok" style="color:var(--success);font-weight:600;">✅ {{ item.value }}</span>
                            <span v-else style="color:var(--text-dim);">❌ <span style="font-size:10px;">{{ item.reason }}</span></span>
                          </div>
                        </div>
                      </div>
                      <!-- ═══ 频道健康全景（综合大卡片）═══ -->
                      <template v-if="c.oauth?.authorized">
                        <div style="margin-bottom:14px;padding:16px;background:var(--bg-card,#222);border-radius:10px;border:1px solid var(--border);">
                          <div style="font-size:13px;font-weight:700;color:var(--accent);margin-bottom:14px;">📊 {{ c.name }} — 频道健康全景</div>

                          <!-- 核心指标行 -->
                          <div style="display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin-bottom:16px;">
                            <div style="text-align:center;padding:10px 6px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div :style="retentionRingStyle(c.oauth.avg_view_pct)" style="width:48px;height:48px;border-radius:50%;margin:0 auto 6px;position:relative;">
                                <div style="position:absolute:inset:5px;background:var(--bg-card,#222);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:11px;font-weight:700;color:var(--text);">{{ c.oauth.avg_view_pct || 0 }}%</div>
                              </div>
                              <div style="font-size:11px;color:var(--text-secondary);">平均留存</div>
                            </div>
                            <div style="text-align:center;padding:10px 6px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div style="font-size:20px;font-weight:700;color:var(--accent2);">{{ formatWatchTime(c.oauth.watch_minutes_30d) }}</div>
                              <div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">观看时长</div>
                            </div>
                            <div style="text-align:center;padding:10px 6px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div style="font-size:20px;font-weight:700;" :style="{ color: (c.oauth.subs_gained_30d - c.oauth.subs_lost_30d) >= 0 ? 'var(--success)' : 'var(--danger)' }">
                                {{ (c.oauth.subs_gained_30d - c.oauth.subs_lost_30d) >= 0 ? '+' : '' }}{{ (c.oauth.subs_gained_30d || 0) - (c.oauth.subs_lost_30d || 0) }}
                              </div>
                              <div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">30天净增粉</div>
                            </div>
                            <div style="text-align:center;padding:10px 6px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div style="font-size:20px;font-weight:700;color:var(--accent);">{{ effPerK(c.oauth) }}</div>
                              <div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">千播订</div>
                            </div>
                            <div style="text-align:center;padding:10px 6px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div style="font-size:20px;font-weight:700;color:var(--accent3);">{{ c.oauth.views_30d ? c.oauth.views_30d.toLocaleString() : '—' }}</div>
                              <div style="font-size:11px;color:var(--text-secondary);margin-top:4px;">30天播放</div>
                            </div>
                          </div>

                          <!-- 分段留存 + 流量来源 + 地域 三列 -->
                          <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:14px;">
                            <!-- 分段留存曲线 -->
                            <div v-if="diagScores[c.name]?.retention_data?.has_data" style="padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div style="font-size:11px;font-weight:600;color:var(--accent2);margin-bottom:8px;">📈 留存曲线</div>
                              <!-- SVG折线图 -->
                              <svg viewBox="0 0 200 120" style="width:100%;height:120px;" v-if="diagScores[c.name]?.retention_data">
                                <!-- 网格线 -->
                                <line x1="30" y1="5" x2="30" y2="95" stroke="rgba(255,255,255,0.15)" stroke-width="0.5"/>
                                <line x1="30" y1="95" x2="190" y2="95" stroke="rgba(255,255,255,0.15)" stroke-width="0.5"/>
                                <line x1="30" y1="50" x2="190" y2="50" stroke="rgba(255,255,255,0.08)" stroke-width="0.5" stroke-dasharray="2"/>
                                <!-- Y轴标签 -->
                                <text x="26" y="8" fill="rgba(255,255,255,0.65)" font-size="8" text-anchor="end">100%</text>
                                <text x="26" y="53" fill="rgba(255,255,255,0.65)" font-size="8" text-anchor="end">50%</text>
                                <text x="26" y="98" fill="rgba(255,255,255,0.65)" font-size="8" text-anchor="end">0%</text>
                                <!-- 折线（3个点：1min/3min/5min） -->
                                <polyline
                                  :points="[
                                    [60, 95 - (diagScores[c.name].retention_data.avg_retention_1pct || 0) * 90],
                                    [110, 95 - (diagScores[c.name].retention_data.avg_retention_3min || 0) * 90],
                                    [160, 95 - (diagScores[c.name].retention_data.avg_retention_5min || 0) * 90]
                                  ].map(p => p.join(',')).join(' ')"
                                  fill="none" :stroke="diagScores[c.name].retention_data.avg_retention_3min > 0.3 ? '#4caf50' : diagScores[c.name].retention_data.avg_retention_3min > 0.2 ? '#ff9800' : '#f44336'"
                                  stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                                <!-- 数据点 -->
                                <circle v-for="(pt, pi) in [
                                  {x:60, val: diagScores[c.name].retention_data.avg_retention_1pct},
                                  {x:110, val: diagScores[c.name].retention_data.avg_retention_3min},
                                  {x:160, val: diagScores[c.name].retention_data.avg_retention_5min}
                                ]" :key="'d'+pi" :cx="pt.x" :cy="95 - (pt.val||0)*90" r="4.5" :fill="(pt.val||0) > 0.7 ? '#4caf50' : (pt.val||0) > 0.3 ? '#ff9800' : '#f44336'"/>
                                <!-- 数值标签 -->
                                <text v-for="(pt, pi) in [
                                  {x:60, val: diagScores[c.name].retention_data.avg_retention_1pct, label:'1min'},
                                  {x:110, val: diagScores[c.name].retention_data.avg_retention_3min, label:'3min'},
                                  {x:160, val: diagScores[c.name].retention_data.avg_retention_5min, label:'5min'}
                                ]" :key="'t'+pi" :x="pt.x" :y="95 - (pt.val||0)*90 - 6" fill="white" font-size="10" text-anchor="middle" font-weight="600">{{ pt.val ? (pt.val*100).toFixed(0)+'%' : '—' }}</text>
                                <!-- X轴标签 -->
                                <text x="60" y="110" fill="rgba(255,255,255,0.75)" font-size="8" text-anchor="middle">1min</text>
                                <text x="110" y="110" fill="rgba(255,255,255,0.75)" font-size="8" text-anchor="middle">3min</text>
                                <text x="160" y="110" fill="rgba(255,255,255,0.75)" font-size="8" text-anchor="middle">5min</text>
                              </svg>
                              <div style="font-size:10px;color:var(--text-muted);margin-top:6px;text-align:center;">
                                {{ diagScores[c.name]?.retention_data?.video_count || 0 }}条视频均值 | 回弹{{ diagScores[c.name]?.retention_data?.rebounds_count || 0 }}条
                              </div>
                            </div>
                            <div v-else style="padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;display:flex;align-items:center;justify-content:center;">
                              <div style="font-size:11px;color:var(--text-muted);">📈 留存曲线：需OAuth授权</div>
                            </div>

                            <!-- 流量来源 -->
                            <div v-if="analyticsData[analyticsKey(c)]?.traffic?.rows?.length" style="padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div style="font-size:11px;font-weight:600;color:var(--accent2);margin-bottom:10px;">🔀 流量来源</div>
                              <div v-for="(row, ri) in analyticsData[analyticsKey(c)].traffic.rows.slice(0, 5)" :key="ri" style="margin-bottom:5px;">
                                <div style="display:flex;justify-content:space-between;font-size:10px;margin-bottom:2px;">
                                  <span>{{ trafficLabel(row[0]) }}</span>
                                  <span style="color:var(--text-muted);">{{ (row[1] / trafficTotal(analyticsData[analyticsKey(c)].traffic.rows) * 100).toFixed(0) }}%</span>
                                </div>
                                <div style="height:5px;background:var(--border);border-radius:3px;overflow:hidden;">
                                  <div :style="{ width: (row[1] / analyticsData[analyticsKey(c)].traffic.rows[0][1] * 100) + '%', height: '100%', background: 'var(--accent2)', borderRadius: '3px' }"></div>
                                </div>
                              </div>
                            </div>
                            <div v-else style="padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;display:flex;align-items:center;justify-content:center;">
                              <div style="font-size:11px;color:var(--text-muted);">🔀 流量来源：加载中...</div>
                            </div>

                            <!-- 地域分布 -->
                            <div v-if="analyticsData[analyticsKey(c)]?.geo?.rows?.length" style="padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;">
                              <div style="font-size:11px;font-weight:600;color:var(--accent2);margin-bottom:10px;">🌍 地域分布</div>
                              <div style="display:flex;align-items:center;gap:12px;">
                                <div :style="donutStyle(analyticsData[analyticsKey(c)].geo.rows)" style="width:60px;height:60px;border-radius:50%;flex-shrink:0;position:relative;">
                                  <div style="position:absolute:inset:12px;background:var(--bg-card,#222);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;color:var(--text);">{{ analyticsData[analyticsKey(c)].geo.rows.length }}国</div>
                                </div>
                                <div style="flex:1;">
                                  <div v-for="(row, ri) in analyticsData[analyticsKey(c)].geo.rows.slice(0, 6)" :key="ri" style="display:flex;align-items:center;gap:4px;font-size:9px;margin-bottom:2px;">
                                    <span :style="{ width:'6px',height:'6px',borderRadius:'50%',background: geoColors[ri],flexShrink:0 }"></span>
                                    <span style="flex:1;">{{ countryName(row[0]) }}</span>
                                    <span style="color:var(--text-muted);min-width:30px;text-align:right;">{{ (row[1] / geoTotal(analyticsData[analyticsKey(c)].geo.rows) * 100).toFixed(0) }}%</span>
                                  </div>
                                </div>
                              </div>
                            </div>
                            <div v-else style="padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;display:flex;align-items:center;justify-content:center;">
                              <div style="font-size:11px;color:var(--text-muted);">🌍 地域分布：加载中...</div>
                            </div>
                          </div>

                          <!-- 受众画像（全宽） -->
                          <div style="padding:12px;background:rgba(255,255,255,0.03);border-radius:8px;">
                            <div style="font-size:11px;font-weight:600;color:var(--accent2);margin-bottom:10px;">👥 受众画像</div>
                            <!-- 已加载 -->
                            <div v-if="analyticsData[analyticsKey(c)]?.demographics?.length || analyticsData[analyticsKey(c)]?.device?.length" style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
                              <!-- 年龄×性别分布 -->
                              <div>
                                <div style="font-size:11px;color:var(--text-secondary);margin-bottom:6px;">年龄×性别</div>
                                <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
                                  <div :style="genderDonutStyle(analyticsData[analyticsKey(c)].demographics)" style="width:36px;height:36px;border-radius:50%;flex-shrink:0;position:relative;">
                                    <div style="position:absolute;inset:4px;background:rgba(26,31,46,0.9);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:7px;font-weight:700;color:var(--text);">
                                      {{ genderPct(analyticsData[analyticsKey(c)].demographics, 'female') }}%
                                    </div>
                                  </div>
                                  <div>
                                    <span style="color:#e57373;font-size:10px;">♀ {{ genderPct(analyticsData[analyticsKey(c)].demographics, 'female') }}%</span>
                                    <span style="color:#4fc3f7;font-size:10px;margin-left:4px;">♂ {{ genderPct(analyticsData[analyticsKey(c)].demographics, 'male') }}%</span>
                                  </div>
                                </div>
                                <div v-for="(ag, ai) in topAgeGroups(analyticsData[analyticsKey(c)].demographics)" :key="ai" style="display:flex;align-items:center;gap:4px;font-size:9px;margin-bottom:3px;">
                                  <span style="min-width:32px;color:var(--text-muted);">{{ ag.age }}</span>
                                  <div style="flex:1;height:5px;background:var(--border);border-radius:2px;overflow:hidden;will-change:width;">
                                    <div :style="{ width: ag.pct + '%', height: '100%', background: ag.gender === 'female' ? '#e57373' : '#4fc3f7', borderRadius: '2px' }"></div>
                                  </div>
                                  <span style="color:var(--text-muted);min-width:24px;text-align:right;">{{ ag.pct }}%</span>
                                  <span v-if="ag.est_minutes" style="color:var(--text-muted);min-width:36px;text-align:right;font-size:9px;">{{ fmtMinutes(ag.est_minutes) }}</span>
                                </div>
                              </div>
                              <!-- 设备类型 + 频道权重 -->
                              <div>
                                <div style="font-size:11px;color:var(--text-secondary);margin-bottom:6px;">设备类型</div>
                                <div v-if="analyticsData[analyticsKey(c)]?.device?.length">
                                  <div v-for="(d, di) in analyticsData[analyticsKey(c)].device.slice(0, 4)" :key="di" style="display:flex;align-items:center;gap:4px;font-size:9px;margin-bottom:3px;">
                                    <span style="min-width:36px;color:var(--text-muted);">{{ deviceLabel(d.type) }}</span>
                                    <div style="flex:1;height:5px;background:var(--border);border-radius:2px;overflow:hidden;will-change:width;">
                                      <div :style="{ width: devicePct(c, d.views) + '%', height: '100%', background: 'var(--accent3)', borderRadius: '2px' }"></div>
                                    </div>
                                    <span style="color:var(--text-muted);min-width:28px;text-align:right;">{{ devicePct(c, d.views) }}%</span>
                                    <span style="color:var(--text-muted);min-width:36px;text-align:right;font-size:9px;">{{ fmtMinutes(d.minutes) }}</span>
                                  </div>
                                </div>
                                <div v-else style="font-size:9px;color:var(--text-muted);margin-bottom:8px;">需OAuth授权</div>
                                <!-- 频道权重 -->
                                <div style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border);">
                                  <div style="font-size:11px;color:var(--text-secondary);margin-bottom:4px;">⚖️ 频道权重</div>
                                  <div v-if="analyticsData[analyticsKey(c)]?.traffic?.rows?.length">
                                    <div v-for="(m, mi) in weightMetrics(c)" :key="mi" style="display:flex;align-items:center;gap:6px;margin-bottom:3px;">
                                      <span style="font-size:9px;min-width:48px;color:var(--text-muted);">{{ m.label }}</span>
                                      <div style="flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden;will-change:width;">
                                        <div :style="{ width: m.pct + '%', height: '100%', background: m.color, borderRadius: '2px' }"></div>
                                      </div>
                                      <span style="font-size:9px;font-weight:600;min-width:28px;text-align:right;" :style="{ color: m.color }">{{ m.value }}</span>
                                    </div>
                                    <div style="font-size:9px;color:var(--text-muted);margin-top:4px;">
                                      算法信任度：<span style="font-weight:600;" :style="{ color: weightLevel(c).color }">{{ weightLevel(c).label }}</span>
                                    </div>
                                  </div>
                                  <div v-else style="font-size:9px;color:var(--text-muted);">需OAuth授权</div>
                                </div>
                              </div>
                            </div>
                            <!-- 加载中 -->
                            <div v-else-if="c?.oauth?.authorized && analyticsData[analyticsKey(c)] === undefined" style="font-size:10px;color:var(--text-dim);text-align:center;padding:8px 0;">
                              <span style="opacity:0.6;">⏳ 加载中...</span>
                            </div>
                            <!-- 未授权 -->
                            <div v-else style="font-size:10px;color:var(--text-dim);text-align:center;padding:8px 0;">需OAuth授权</div>
                          </div>
                        </div>
                      </template>

                      <!-- LLM 诊断 -->
                      <div v-if="getChannelLlm(c.name)" style="margin-bottom:12px;padding:12px;background:var(--bg-card,#222);border-radius:8px;border:1px solid var(--border);">
                        <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                          <div style="text-align:center;min-width:60px;">
                            <div style="font-size:28px;font-weight:800;" :style="{ color: scoreColor(getChannelLlm(c.name).health_score || 0) }">{{ (getChannelLlm(c.name).health_score || 0).toFixed(1) }}</div>
                            <div style="font-size:11px;color:var(--text-secondary)">健康度 {{ getChannelLlm(c.name).health_grade || '' }}</div>
                          </div>
                          <div style="flex:1;font-size:12px;color:var(--text);line-height:1.5;">{{ getChannelLlm(c.name).summary || '' }}</div>
                        </div>

                        <!-- 批3 additive: 瓶颈横幅 -->
                        <div v-if="getChannelLlm(c.name).bottleneck?.primary" class="ca-bottleneck-banner" style="margin-bottom:8px;padding:10px 12px;background:linear-gradient(90deg,rgba(255,152,0,0.12),rgba(255,152,0,0.04));border-left:3px solid #ff9800;border-radius:6px;">
                          <div style="font-size:11px;font-weight:700;color:#ff9800;margin-bottom:3px;">🎯 当前瓶颈</div>
                          <div style="font-size:12px;font-weight:600;">{{ getChannelLlm(c.name).bottleneck.primary }}</div>
                          <div v-if="getChannelLlm(c.name).bottleneck.evidence" style="font-size:10px;color:var(--text-muted);margin-top:2px;">📊 {{ getChannelLlm(c.name).bottleneck.evidence }}</div>
                          <div v-if="getChannelLlm(c.name).bottleneck.next_lever" style="font-size:11px;color:var(--accent);margin-top:3px;">🔧 下一步：{{ getChannelLlm(c.name).bottleneck.next_lever }}</div>
                        </div>

                        <!-- 批3 additive: 四象限归类概览 -->
                        <div v-if="getChannelLlm(c.name).quadrant_summary?.status" style="margin-bottom:8px;padding:8px 10px;background:rgba(63,81,181,0.06);border:1px solid rgba(63,81,181,0.18);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">🎬 视频四象限（{{ getChannelLlm(c.name).quadrant_summary.status }} · 已归类 {{ getChannelLlm(c.name).quadrant_summary.total_classified || 0 }}）
                            <span v-if="getChannelLlm(c.name).quadrant_summary.status==='skipped'" style="color:var(--text-muted);font-weight:400;font-size:10px;">— 无 CTR 数据，跳过归类</span>
                            <span v-else-if="getChannelLlm(c.name).quadrant_summary.status==='provisional'" style="color:#ffb74d;font-weight:400;font-size:10px;">— CTR pending，使用播放代理</span>
                          </div>
                          <div v-if="getChannelLlm(c.name).quadrant_summary.bucket_takeaways?.length" class="ca-quadrant-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:6px;">
                            <div v-for="(bt, bti) in getChannelLlm(c.name).quadrant_summary.bucket_takeaways.filter(x => (x.count||0)>0)" :key="bti" style="padding:5px 7px;background:rgba(255,255,255,0.04);border-radius:4px;">
                              <div style="font-weight:600;font-size:10px;">{{ bt.bucket }} <span style="color:var(--accent);">({{ bt.count }})</span></div>
                              <div style="color:var(--text-muted);font-size:10px;">{{ bt.action }}</div>
                            </div>
                          </div>
                        </div>

                        <!-- 批3 additive: 冲突警告（Python 后校验写入） -->
                        <div v-if="getChannelLlm(c.name).conflicts?.length" style="margin-bottom:8px;padding:8px 10px;background:rgba(255,82,82,0.08);border-left:3px solid var(--danger);border-radius:6px;font-size:11px;">
                          <div style="font-weight:700;color:var(--danger);margin-bottom:3px;">⚠️ 诊断内部冲突（LLM 表达矛盾）</div>
                          <div v-for="(cf, cfi) in getChannelLlm(c.name).conflicts" :key="cfi" style="margin-bottom:4px;">
                            <div style="font-weight:600;">{{ cf.dimension }}</div>
                            <div style="color:var(--success);font-size:10px;">优势侧：{{ cf.as_strength }}</div>
                            <div style="color:var(--danger);font-size:10px;">问题侧：{{ cf.as_problem }}</div>
                          </div>
                        </div>

                        <!-- 批3 additive: 变现分项（覆盖旧 monetization_readiness） -->
                        <div v-if="getChannelLlm(c.name).monetization_detail" class="ca-monetization-detail" style="margin-bottom:8px;padding:8px 10px;background:rgba(0,200,83,0.05);border:1px solid rgba(0,200,83,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">💰 YPP 变现分项</div>
                          <div style="display:flex;gap:12px;flex-wrap:wrap;">
                            <div>订阅：<b>{{ getChannelLlm(c.name).monetization_detail.subscribers || '-' }}</b></div>
                            <div>观看时长：<b>{{ getChannelLlm(c.name).monetization_detail.watch_hours_12mo || '-' }}</b></div>
                            <div v-if="getChannelLlm(c.name).monetization_detail.engagement_gate">互动：<b>{{ getChannelLlm(c.name).monetization_detail.engagement_gate }}</b></div>
                          </div>
                        </div>

                        <!-- 批3 additive: 订阅转化分析 (新 schema) -->
                        <div v-if="getChannelLlm(c.name).sub_conversion_analysis" style="margin-bottom:8px;padding:8px 10px;background:rgba(103,58,183,0.05);border:1px solid rgba(103,58,183,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">🔔 订阅转化</div>
                          <div style="color:var(--text-muted);margin-bottom:3px;">水平：<b>{{ getChannelLlm(c.name).sub_conversion_analysis.channel_level || '-' }}</b></div>
                          <div v-if="getChannelLlm(c.name).sub_conversion_analysis.top_pattern" style="color:var(--success);margin-bottom:2px;">🏆 Top 规律：{{ getChannelLlm(c.name).sub_conversion_analysis.top_pattern }}</div>
                          <div v-if="getChannelLlm(c.name).sub_conversion_analysis.bottom_pattern" style="color:var(--danger);margin-bottom:2px;">🥶 Bottom 规律：{{ getChannelLlm(c.name).sub_conversion_analysis.bottom_pattern }}</div>
                          <div v-if="getChannelLlm(c.name).sub_conversion_analysis.action" style="color:var(--accent);margin-top:3px;">💡 {{ getChannelLlm(c.name).sub_conversion_analysis.action }}</div>
                        </div>

                        <!-- 流量分析 (新 schema: traffic_analysis) -->
                        <div v-if="getChannelLlm(c.name).traffic_analysis" style="margin-bottom:8px;padding:8px 10px;background:rgba(0,150,255,0.05);border:1px solid rgba(0,150,255,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">📊 流量结构 <span style="color:var(--text-muted);font-weight:400;">({{ getChannelLlm(c.name).traffic_analysis.health || '-' }})</span></div>
                          <div style="color:var(--text-muted);margin-bottom:2px;">推荐 <b>{{ getChannelLlm(c.name).traffic_analysis.recommend_pct || '-' }}%</b> · 订阅 <b>{{ getChannelLlm(c.name).traffic_analysis.subscriber_pct || '-' }}%</b> · 搜索 <b>{{ getChannelLlm(c.name).traffic_analysis.search_pct || '-' }}%</b></div>
                          <div v-if="getChannelLlm(c.name).traffic_analysis.insight" style="color:var(--accent);margin-top:3px;">{{ getChannelLlm(c.name).traffic_analysis.insight }}</div>
                        </div>

                        <!-- 地域策略 -->
                        <div v-if="getChannelLlm(c.name).geo_strategy" style="margin-bottom:8px;padding:8px 10px;background:rgba(255,193,7,0.05);border:1px solid rgba(255,193,7,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">🌍 地域策略</div>
                          <div v-if="getChannelLlm(c.name).geo_strategy.top_markets" style="color:var(--text-muted);">Top 市场：{{ Array.isArray(getChannelLlm(c.name).geo_strategy.top_markets) ? getChannelLlm(c.name).geo_strategy.top_markets.join(', ') : getChannelLlm(c.name).geo_strategy.top_markets }}</div>
                          <div v-if="getChannelLlm(c.name).geo_strategy.growth_markets" style="color:var(--success);">增长市场：{{ Array.isArray(getChannelLlm(c.name).geo_strategy.growth_markets) ? getChannelLlm(c.name).geo_strategy.growth_markets.join(', ') : getChannelLlm(c.name).geo_strategy.growth_markets }}</div>
                          <div v-if="getChannelLlm(c.name).geo_strategy.opportunity_markets" style="color:var(--accent);">机会市场：{{ Array.isArray(getChannelLlm(c.name).geo_strategy.opportunity_markets) ? getChannelLlm(c.name).geo_strategy.opportunity_markets.join(', ') : getChannelLlm(c.name).geo_strategy.opportunity_markets }}</div>
                          <div v-if="getChannelLlm(c.name).geo_strategy.insight" style="color:var(--text);margin-top:3px;">{{ getChannelLlm(c.name).geo_strategy.insight }}</div>
                        </div>

                        <!-- 留存诊断 -->
                        <div v-if="getChannelLlm(c.name).retention_diagnosis" style="margin-bottom:8px;padding:8px 10px;background:rgba(233,30,99,0.05);border:1px solid rgba(233,30,99,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">📈 留存诊断 <span style="color:var(--text-muted);font-weight:400;">({{ getChannelLlm(c.name).retention_diagnosis.status || '-' }})</span></div>
                          <div v-if="getChannelLlm(c.name).retention_diagnosis.hook_quality" style="color:var(--text-muted);">钩子质量：{{ getChannelLlm(c.name).retention_diagnosis.hook_quality }}</div>
                          <div v-if="getChannelLlm(c.name).retention_diagnosis.evidence" style="color:var(--accent);margin-top:3px;">📊 {{ getChannelLlm(c.name).retention_diagnosis.evidence }}</div>
                        </div>

                        <!-- 受众洞察 -->
                        <div v-if="getChannelLlm(c.name).audience_insight" style="margin-bottom:8px;padding:8px 10px;background:rgba(3,169,244,0.05);border:1px solid rgba(3,169,244,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">👥 受众洞察</div>
                          <div v-if="getChannelLlm(c.name).audience_insight.actual_profile" style="color:var(--text-muted);">实际画像：{{ getChannelLlm(c.name).audience_insight.actual_profile }}</div>
                          <div v-if="getChannelLlm(c.name).audience_insight.match_with_content" style="color:var(--accent);margin-top:3px;">🎯 匹配度：{{ getChannelLlm(c.name).audience_insight.match_with_content }}</div>
                        </div>

                        <!-- 增长诊断 -->
                        <div v-if="getChannelLlm(c.name).growth_diagnosis" style="margin-bottom:8px;padding:8px 10px;background:rgba(76,175,80,0.05);border:1px solid rgba(76,175,80,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">📈 增长诊断 <span style="color:var(--text-muted);font-weight:400;">({{ getChannelLlm(c.name).growth_diagnosis.trend || '-' }})</span></div>
                          <div v-if="getChannelLlm(c.name).growth_diagnosis.root_cause" style="color:var(--danger);">根因：{{ getChannelLlm(c.name).growth_diagnosis.root_cause }}</div>
                          <div v-if="getChannelLlm(c.name).growth_diagnosis.bottleneck" style="color:var(--accent);margin-top:3px;">瓶颈：{{ getChannelLlm(c.name).growth_diagnosis.bottleneck }}</div>
                        </div>

                        <!-- 封面标题协同 -->
                        <div v-if="getChannelLlm(c.name).cover_title_synergy" style="margin-bottom:8px;padding:8px 10px;background:rgba(255,87,34,0.05);border:1px solid rgba(255,87,34,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">🎨 封面×标题协同 <span style="color:var(--accent);">{{ getChannelLlm(c.name).cover_title_synergy.score || '-' }}/10</span></div>
                          <div v-if="getChannelLlm(c.name).cover_title_synergy.assessment" style="color:var(--text-muted);">{{ getChannelLlm(c.name).cover_title_synergy.assessment }}</div>
                          <div v-if="getChannelLlm(c.name).cover_title_synergy.improvement" style="color:var(--accent);margin-top:3px;">💡 {{ getChannelLlm(c.name).cover_title_synergy.improvement }}</div>
                        </div>

                        <!-- 系列分析 -->
                        <div v-if="getChannelLlm(c.name).series_analysis" style="margin-bottom:8px;padding:8px 10px;background:rgba(96,125,139,0.05);border:1px solid rgba(96,125,139,0.15);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">📚 系列分析</div>
                          <div v-if="getChannelLlm(c.name).series_analysis.current_series" style="color:var(--text-muted);">当前系列：{{ getChannelLlm(c.name).series_analysis.current_series }}<span v-if="getChannelLlm(c.name).series_analysis.series_count"> · {{ getChannelLlm(c.name).series_analysis.series_count }}个</span></div>
                          <div v-if="getChannelLlm(c.name).series_analysis.series_performance" style="color:var(--text);margin-top:2px;">{{ getChannelLlm(c.name).series_analysis.series_performance }}</div>
                          <div v-if="getChannelLlm(c.name).series_analysis.recommendation" style="color:var(--accent);margin-top:3px;">💡 {{ getChannelLlm(c.name).series_analysis.recommendation }}</div>
                        </div>

                        <div style="display:flex;gap:10px;margin-bottom:8px;flex-wrap:wrap;">
                          <div v-if="getChannelLlm(c.name).strengths?.length" style="flex:1;min-width:180px;padding:8px 10px;background:rgba(0,200,83,0.06);border-radius:6px;border:1px solid rgba(0,200,83,0.15);">
                            <div style="font-size:11px;font-weight:600;color:var(--success);margin-bottom:4px;">✅ 核心优势</div>
                            <div v-for="(s, si) in getChannelLlm(c.name).strengths" :key="si" style="font-size:11px;margin-bottom:3px;"><b>{{ s.area || '' }}</b>：{{ s.detail || '' }}</div>
                          </div>
                          <div v-if="getChannelLlm(c.name).problems?.length" style="flex:1;min-width:180px;padding:8px 10px;background:rgba(255,82,82,0.06);border-radius:6px;border:1px solid rgba(255,82,82,0.15);">
                            <div style="font-size:11px;font-weight:600;color:var(--danger);margin-bottom:4px;">🚨 核心问题</div>
                            <div v-for="(p, pi) in getChannelLlm(c.name).problems" :key="pi" style="margin-bottom:3px;">
                              <div style="font-size:11px;cursor:pointer;" @click="expandedProblem = expandedProblem === c.name+'::'+pi ? null : c.name+'::'+pi">
                                {{ sevIcon(p.severity) }} <b>{{ p.area || '' }}</b>：{{ (p.detail || '').slice(0, 60) }}{{ (p.detail || '').length > 60 ? '…' : '' }}
                              </div>
                              <div v-if="expandedProblem === c.name+'::'+pi" style="margin:2px 0 4px 16px;padding:6px;background:rgba(255,255,255,0.04);border-radius:4px;font-size:10px;transition:all 0.15s;">
                                <div style="color:var(--text);">{{ p.detail || '' }}</div>
                                <div v-if="p.evidence" style="color:var(--accent);margin-top:3px;">📊 {{ p.evidence }}</div>
                                <div v-if="p.affected_videos?.length" style="color:var(--text-muted);margin-top:3px;">受影响视频: {{ p.affected_videos.join(', ') }}</div>
                              </div>
                            </div>
                          </div>
                        </div>
                        <div v-if="getChannelLlm(c.name).actions?.length" style="padding:8px 10px;background:rgba(255,255,255,0.03);border-radius:6px;font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">🎯 行动清单</div>
                          <div v-for="(a, ai) in getChannelLlm(c.name).actions" :key="ai" style="margin-bottom:3px;">
                            <div style="cursor:pointer;" @click="expandedAction = expandedAction === c.name+'::'+ai ? null : c.name+'::'+ai">
                              <span style="color:var(--accent);font-weight:600;">P{{ a.priority || '?' }}</span> {{ a.action || '' }}
                            </div>
                            <div v-if="expandedAction === c.name+'::'+ai" style="margin:2px 0 4px 16px;padding:6px;background:rgba(255,255,255,0.04);border-radius:4px;font-size:10px;transition:all 0.15s;">
                              <div v-if="a.based_on" style="color:var(--text-muted);">📌 基于: {{ a.based_on }}</div>
                              <div v-if="a.expected_impact" style="color:var(--success);margin-top:2px;">📈 预期: {{ a.expected_impact }}</div>
                              <div v-if="a.effort" style="color:var(--accent);margin-top:2px;">💪 难度: {{ effortIcon(a.effort) }}{{ a.effort }}</div>
                            </div>
                          </div>
                        </div>
                        <!-- AI发现的规律 -->
                        <div v-if="getChannelLlm(c.name).ai_discoveries?.length" style="margin-top:8px;padding:8px 10px;background:rgba(156,39,176,0.06);border-radius:6px;border:1px solid rgba(156,39,176,0.15);font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">🔍 AI发现的隐藏规律</div>
                          <div v-for="(disc, di) in getChannelLlm(c.name).ai_discoveries" :key="di" style="margin-bottom:4px;">
                            <div style="font-weight:600;color:var(--accent2);cursor:pointer;" @click="expandedDiscovery = expandedDiscovery === c.name+'::'+di ? null : c.name+'::'+di">{{ disc.pattern || '' }}</div>
                            <div style="color:var(--text-muted);">{{ disc.insight || '' }}</div>
                            <div v-if="expandedDiscovery === c.name+'::'+di && disc.evidence" style="margin:2px 0 4px 8px;padding:6px;background:rgba(255,255,255,0.04);border-radius:4px;font-size:10px;transition:all 0.15s;">
                              <div style="color:var(--accent);">📊 {{ disc.evidence }}</div>
                            </div>
                          </div>
                        </div>
                        <!-- 流量来源 + 地域 (合并) -->
                        <div v-if="getChannelLlm(c.name).traffic_geo" style="margin-top:8px;padding:8px 10px;background:rgba(0,150,255,0.05);border-radius:6px;border:1px solid rgba(0,150,255,0.12);font-size:11px;">
                          <div style="font-weight:600;margin-bottom:4px;">📊 流量 & 地域 <span style="color:var(--text-muted);">({{ getChannelLlm(c.name).traffic_geo.health || '-' }})</span></div>
                          <div style="color:var(--text-muted);">推荐{{ getChannelLlm(c.name).traffic_geo.recommend_pct || '-' }}% · 订阅{{ getChannelLlm(c.name).traffic_geo.subscriber_pct || '-' }}% · 搜索{{ getChannelLlm(c.name).traffic_geo.search_pct || '-' }}%</div>
                          <div v-if="getChannelLlm(c.name).traffic_geo.top_markets" style="color:var(--text-muted);margin-top:2px;">🌍 {{ getChannelLlm(c.name).traffic_geo.top_markets }}</div>
                          <div v-if="getChannelLlm(c.name).traffic_geo.insight" style="color:var(--accent);margin-top:2px;">{{ getChannelLlm(c.name).traffic_geo.insight }}</div>
                        </div>
                        <!-- 变现 + 上传节奏&系列 (合并) -->
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:8px;font-size:11px;">
                          <div v-if="getChannelLlm(c.name).monetization_readiness" style="padding:6px 8px;background:rgba(255,255,255,0.03);border-radius:6px;">
                            <div style="font-weight:600;margin-bottom:3px;">💰 变现</div>
                            <div style="color:var(--text-muted);">{{ getChannelLlm(c.name).monetization_readiness.status || '-' }} · 观看{{ getChannelLlm(c.name).monetization_readiness.watch_hours || '-' }} · 订阅{{ getChannelLlm(c.name).monetization_readiness.subscribers || '-' }}</div>
                          </div>
                          <div v-if="getChannelLlm(c.name).upload_series" style="padding:6px 8px;background:rgba(255,255,255,0.03);border-radius:6px;">
                            <div style="font-weight:600;margin-bottom:3px;">📺 节奏 & 系列</div>
                            <div style="color:var(--text-muted);">{{ getChannelLlm(c.name).upload_series.current_rate || '-' }}</div>
                            <div v-if="getChannelLlm(c.name).upload_series.recommendation" style="color:var(--accent);margin-top:2px;">{{ getChannelLlm(c.name).upload_series.recommendation }}</div>
                          </div>
                        </div>
                      </div>

                      <!-- 视频诊断表 -->
                      <div v-if="getMergedVideos(c.name).length" style="overflow-x:auto;">
                        <div style="font-size:12px;font-weight:600;color:var(--text-secondary);margin-bottom:6px;">📋 视频诊断 <span v-if="c.oauth?.authorized" style="color:var(--accent2);">（含深度数据）</span></div>
                        <table class="data-table" style="font-size:11px;">
                          <thead><tr>
                            <th style="width:24px;">#</th><th>标题</th><th style="width:50px;">日期</th>
                            <th class="num" style="width:55px;">播放</th><th class="num" style="width:40px;">点赞</th>
                            <th class="num" style="width:40px;">评论</th><th class="num" style="width:45px;">赞率</th>
                            <th v-if="c.oauth?.authorized" class="num" style="width:45px;color:var(--accent2)">留存%</th>
                            <th v-if="c.oauth?.authorized" class="num" style="width:50px;color:var(--accent2)">观看时长</th>
                            <th class="num" style="width:40px;">评分</th><th>问题 & 建议</th>
                          </tr></thead>
                          <tbody>
                            <template v-for="(v, vi) in getMergedVideos(c.name)" :key="vi">
                            <tr :style="{ cursor: 'pointer', background: expandedVideo === c.name+'::'+vi ? 'var(--bg-hover)' : '' }" @click="expandedVideo = expandedVideo === c.name+'::'+vi ? null : c.name+'::'+vi">
                              <td style="color:var(--text-muted);">{{ vi + 1 }}</td>
                              <td>
                                <div style="display:flex;align-items:center;gap:6px;">
                                  <img v-if="v.thumbnail" :src="v.thumbnail" style="width:48px;height:27px;object-fit:cover;border-radius:3px;flex-shrink:0;" @error="$event.target.style.display='none'" />
                                  <div style="line-height:1.4;" :title="v.title || ''">{{ v.title || '-' }}</div>
                                </div>
                              </td>
                              <td style="font-size:10px;color:var(--text-muted);white-space:nowrap;">{{ fmtDate(v.published_at) }}</td>
                              <td class="num">{{ (v.views || 0).toLocaleString() }}</td>
                              <td class="num">{{ (v.likes || 0).toLocaleString() }}</td>
                              <td class="num">{{ (v.comments || 0).toLocaleString() }}</td>
                              <td class="num" style="font-weight:600;" :style="{ color: likeRateColor(v.views, v.likes) }">{{ calcLikeRate(v.views, v.likes) }}%</td>
                              <td v-if="c.oauth?.authorized" class="num" style="font-weight:600;" :style="{ color: retentionColor(v._retention || null) }">{{ v._retention != null ? v._retention.toFixed(1) + '%' : '—' }}</td>
                              <td v-if="c.oauth?.authorized" class="num" style="font-size:10px;">{{ v._watchMin != null ? v._watchMin.toLocaleString() + 'm' : '—' }}</td>
                              <td class="num" style="font-weight:700;" :style="{ color: scoreColor(v._score || 0) }">{{ (v._score || 0) > 0 ? v._score.toFixed(1) : '-' }}</td>
                              <td style="font-size:10px;max-width:200px;">
                                <div v-if="v._issues?.length" style="color:var(--danger);cursor:pointer;">
                                  ⚠️ {{ v._issues.length }}个问题 <span style="color:var(--text-dim);font-size:9px;">点击展开→</span>
                                </div>
                                <div v-else-if="v._optTitles?.length" style="color:var(--success);cursor:pointer;">
                                  💡 {{ v._optTitles.length }}个优化建议 <span style="color:var(--text-dim);font-size:9px;">点击展开→</span>
                                </div>
                                <div v-else style="color:var(--text-dim);">—</div>
                              </td>
                            </tr>
                            <!-- 诊断详情行 -->
                            <tr v-if="expandedVideo === c.name+'::'+vi && (v._issues?.length || v._titleAnalysis || v._coverSynergy || v._optTitles?.length)" :key="vi+'-detail'" style="background:var(--bg-card);">
                              <td :colspan="c.oauth?.authorized ? 10 : 8" style="padding:12px 16px;">
                                <!-- 问题 & 建议 -->
                                <div v-if="v._issues?.length" style="margin-bottom:10px;background:var(--bg-main);border-radius:8px;padding:10px;font-size:12px;">
                                  <div style="font-weight:600;margin-bottom:6px;color:var(--danger);">⚠️ 问题 & 建议</div>
                                  <div v-for="(issue, ii) in v._issues" :key="ii" style="margin-bottom:4px;padding-left:8px;border-left:2px solid var(--danger);">
                                    <div style="color:var(--text);">{{ issue.issue || issue }}</div>
                                    <div v-if="issue.suggestion" style="color:var(--success);margin-top:2px;">💡 {{ issue.suggestion }}</div>
                                  </div>
                                </div>
                                <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:12px;">
                                  <!-- 左列：标题分析 -->
                                  <div style="background:var(--bg-main);border-radius:8px;padding:10px;">
                                    <div style="font-weight:600;margin-bottom:6px;color:var(--accent);">📝 标题分析</div>
                                    <template v-if="v._titleAnalysis">
                                      <div><b>骨架：</b>{{ v._titleAnalysis.skeleton || '-' }}</div>
                                      <div style="margin-top:4px;"><b>钩子：</b>
                                        <template v-for="(val, key) in v._titleAnalysis.hooks" :key="key">
                                          <span v-if="key !== 'other' && val" style="background:var(--accent);color:#fff;border-radius:3px;padding:1px 4px;margin-right:3px;font-size:11px;">{{ key }}</span>
                                        </template>
                                        <span v-for="o in (v._titleAnalysis.hooks?.other || [])" :key="o" style="background:var(--accent2);color:#fff;border-radius:3px;padding:1px 4px;margin-right:3px;font-size:11px;">{{ o }}</span>
                                      </div>
                                      <div v-if="v._titleAnalysis.hook_types_found?.length" style="margin-top:4px;"><b>具体钩子：</b>{{ v._titleAnalysis.hook_types_found.join('、') }}</div>
                                      <div style="margin-top:4px;"><b>包装：</b>{{ v._titleAnalysis.packaging || '-' }}</div>
                                      <div v-if="v._titleAnalysis.missing?.length" style="margin-top:4px;color:var(--danger);"><b>缺失：</b>{{ v._titleAnalysis.missing.join('、') }}</div>
                                    </template>
                                    <div v-else style="color:var(--text-dim);">无数据</div>
                                  </div>
                                  <!-- 右列：封面协同 -->
                                  <div style="background:var(--bg-main);border-radius:8px;padding:10px;">
                                    <div style="font-weight:600;margin-bottom:6px;color:var(--accent2);">🎨 封面×标题协同</div>
                                    <template v-if="v._coverSynergy">
                                      <div><b>协同分：</b><span :style="{ color: scoreColor(v._coverSynergy.score || 0), fontWeight: 700 }">{{ (v._coverSynergy.score || 0).toFixed(1) }}/10</span></div>
                                      <div style="margin-top:4px;"><b>模式：</b>{{ v._coverSynergy.synergy_pattern || '-' }}</div>
                                      <div v-if="v._coverSynergy.anti_pattern" style="margin-top:4px;color:var(--danger);"><b>反模式：</b>{{ v._coverSynergy.anti_pattern }}</div>
                                      <div style="margin-top:4px;"><b>评估：</b>{{ v._coverSynergy.assessment || '-' }}</div>
                                      <div v-if="v._coverSynergy.improvement" style="margin-top:4px;color:var(--success);"><b>建议：</b>{{ v._coverSynergy.improvement }}</div>
                                    </template>
                                    <div v-else style="color:var(--text-dim);">无数据</div>
                                  </div>
                                </div>
                                <!-- 优化标题 -->
                                <div v-if="v._optTitles?.length" style="margin-top:10px;background:var(--bg-main);border-radius:8px;padding:10px;font-size:12px;">
                                  <div style="font-weight:600;margin-bottom:6px;color:var(--success);">💡 优化标题</div>
                                  <div v-for="(ot, oi) in v._optTitles" :key="oi" style="margin-bottom:6px;padding-left:8px;border-left:2px solid var(--success);">
                                    <div style="font-weight:600;">{{ oi+1 }}. {{ typeof ot === 'object' ? ot.title : ot }}</div>
                                    <div v-if="typeof ot === 'object'" style="color:var(--text-muted);margin-top:2px;">
                                      <span v-if="ot.skeleton">骨架：{{ ot.skeleton }}</span>
                                      <span v-if="ot.hooks"> · 钩子：{{ ot.hooks }}</span>
                                    </div>
                                    <div v-if="typeof ot === 'object' && ot.reason" style="color:var(--text-muted);margin-top:2px;">{{ ot.reason }}</div>
                                  </div>
                                </div>
                              </td>
                            </tr>
                            </template>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </td>
                </tr>
                </template>
              </tbody>
            </table>
          </div>
          </div>
        </div>

        <!-- ═══ 日报 ═══ -->
        <div v-if="view === 'daily'">
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-value" style="color:var(--success)">{{ fmtGain(todaySubGain) }}</div>
              <div class="stat-label">今日新增订阅</div>
              <div style="font-size:11px;color:var(--text-muted)">累计 {{ totalSubs.toLocaleString() }}</div>
            </div>
            <div class="stat-card">
              <div class="stat-value" style="color:var(--success)">{{ fmtGain(todayViewGain) }}</div>
              <div class="stat-label">今日新增播放</div>
            </div>
            <div class="stat-card">
              <div class="stat-value" style="color:var(--success)">{{ fmtGain(todayVideoGain) }}</div>
              <div class="stat-label">今日新增视频</div>
            </div>
            <div class="stat-card">
              <div class="stat-value" :style="{ color: anomalyCount > 0 ? 'var(--danger)' : 'var(--success)' }">{{ anomalyCount }}</div>
              <div class="stat-label">异常频道</div>
            </div>
          </div>

          <!-- 频道日报表格 -->
          <div class="card" style="margin-top:20px;">
            <div class="card-header">
              <div class="card-title">📋 频道日报</div>
              <div class="card-desc" style="font-size:12px;color:var(--text-muted)">日期: {{ data.report_date }}</div>
            </div>
            <div style="overflow-x:auto">
              <table class="data-table" style="font-size:12px;">
                <thead><tr>
                  <th>#</th><th>频道</th><th>语种</th><th>赛道</th>
                  <th class="num">今日+订阅</th><th class="num">环比%</th>
                  <th class="num">今日+播放</th><th class="num">环比%</th>
                  <th class="num">今日+视频</th>
                  <th class="num">赞率</th><th class="num">赞率变化</th>
                  <th class="num">累计订阅</th><th class="num">累计播放</th>
                  <th>健康</th><th>异常</th>
                </tr></thead>
                <tbody>
                  <tr v-for="(c, idx) in dailySorted" :key="c.name">
                    <td style="color:var(--text-muted);">{{ idx + 1 }}</td>
                    <td style="font-weight:600;">{{ c.name }}</td>
                    <td>{{ c.language || '-' }}</td>
                    <td style="font-size:11px;">{{ c.niche || '-' }}</td>
                    <td class="num" :style="{ color: gainColor(c.growth?.has_prev ? c.growth.subscribers_change : null), fontWeight: 600 }">
                      {{ fmtGain(c.growth?.has_prev ? c.growth.subscribers_change : null) }}
                    </td>
                    <td class="num" style="font-size:11px;" :style="{ color: gainColor(c.growth?.has_prev ? c.growth.subscribers_change_pct : null) }">
                      {{ fmtPct(c.growth?.has_prev ? c.growth.subscribers_change_pct : null) }}
                    </td>
                    <td class="num" :style="{ color: gainColor(c.growth?.has_prev ? c.growth.views_change : null), fontWeight: 600 }">
                      {{ fmtGain(c.growth?.has_prev ? c.growth.views_change : null) }}
                    </td>
                    <td class="num" style="font-size:11px;" :style="{ color: gainColor(c.growth?.has_prev ? c.growth.views_change_pct : null) }">
                      {{ fmtPct(c.growth?.has_prev ? c.growth.views_change_pct : null) }}
                    </td>
                    <td class="num" :style="{ color: gainColor(c.growth?.has_prev ? c.growth.videos_change : null) }">
                      {{ fmtGain(c.growth?.has_prev ? c.growth.videos_change : null) }}
                    </td>
                    <td class="num" :style="{ color: c.like_rate >= 1.5 ? 'var(--success)' : c.like_rate >= 1 ? 'var(--accent)' : 'var(--danger)' }">{{ c.like_rate }}%</td>
                    <td class="num" style="font-size:11px;" :style="{ color: gainColor(c.growth?.has_prev ? c.growth.like_rate_change : null) }">
                      {{ c.growth?.has_prev ? (c.growth.like_rate_change > 0 ? '+' : '') + (c.growth.like_rate_change ?? '-') : '-' }}
                    </td>
                    <td class="num" style="color:var(--text-muted);font-size:11px;">{{ c.subscribers.toLocaleString() }}</td>
                    <td class="num" style="color:var(--text-muted);font-size:11px;">{{ c.total_views.toLocaleString() }}</td>
                    <td><span :style="{ color: healthColor(c.health), fontSize: '11px' }">{{ c.health || '-' }}</span></td>
                    <td>
                      <template v-if="detectAnomalies(c).length">
                        <span v-for="(a, ai) in detectAnomalies(c)" :key="ai" style="background:rgba(204,102,102,0.15);color:var(--danger);padding:1px 6px;border-radius:3px;font-size:10px;margin:1px;display:inline-block;">{{ a }}</span>
                      </template>
                      <span v-else style="color:var(--success);font-size:11px;">无</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <!-- 近期视频表（按频道切换） -->
          <div v-if="allDailyVideos.length" class="card" style="margin-top:20px;">
            <div class="card-header">
              <div class="card-title">🎬 近期视频</div>
              <div style="display:flex;gap:4px;flex-wrap:wrap;">
                <button class="btn btn-sm" :class="dailyVidFilter === 'all' ? 'active' : 'btn-secondary'" style="font-size:10px;padding:2px 8px;" @click="dailyVidFilter = 'all'">全部</button>
                <button v-for="ch in channels" :key="ch.name" class="btn btn-sm" :class="dailyVidFilter === ch.name ? 'active' : 'btn-secondary'" style="font-size:10px;padding:2px 8px;" @click="dailyVidFilter = ch.name">{{ ch.name.split(' ')[0] }}</button>
              </div>
            </div>
            <div style="overflow-x:auto">
              <table class="data-table" style="font-size:11px;">
                <thead><tr>
                  <th style="width:30px;">#</th><th>频道</th><th>标题</th><th>日期</th>
                  <th class="num">播放</th><th class="num">点赞</th><th class="num">评论</th><th class="num">赞率</th>
                </tr></thead>
                <tbody>
                  <tr v-for="(v, vi) in filteredDailyVideos" :key="vi">
                    <td style="color:var(--text-muted);">{{ vi + 1 }}</td>
                    <td style="font-size:10px;color:var(--text-muted);white-space:nowrap;">{{ v._channel || '-' }}</td>
                    <td>
                      <div style="display:flex;align-items:center;gap:6px;">
                        <img v-if="v.thumbnail" :src="v.thumbnail" style="width:48px;height:27px;object-fit:cover;border-radius:3px;flex-shrink:0;" @error="$event.target.style.display='none'" />
                        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px;" :title="v.title || ''">{{ v.title || '-' }}</div>
                      </div>
                    </td>
                    <td style="font-size:10px;color:var(--text-muted);white-space:nowrap;">{{ fmtDate(v.published_at) }}</td>
                    <td class="num">{{ (v.views || 0).toLocaleString() }}</td>
                    <td class="num">{{ (v.likes || 0).toLocaleString() }}</td>
                    <td class="num">{{ (v.comments || 0).toLocaleString() }}</td>
                    <td class="num" style="font-weight:600;" :style="{ color: likeRateColor(v.views, v.likes) }">{{ calcLikeRate(v.views, v.likes) }}%</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api/index.js'
import { formatNumber } from '../utils.js'

const view = ref('overview')
const loading = ref(true)
const data = ref({})
const expanded = ref(new Set())
const dailyVidFilter = ref('all')
const analyticsData = ref({})  // slug → analytics response

const channels = computed(() => data.value.channels || [])
const diagScores = computed(() => data.value.diagnostics || {})
const expandedVideo = ref(null)  // 'channelName::videoIndex' 格式
// 诊断板块展开状态
const expandedProblem = ref(null)   // 'channelName::problemIndex'
const expandedAction = ref(null)    // 'channelName::actionIndex'
const expandedDiscovery = ref(null) // 'channelName::discoveryIndex'
const expandedQuadrant = ref(null)  // 'channelName::qName::videoIndex'

const totalSubs = computed(() => channels.value.reduce((s, c) => s + c.subscribers, 0))
const totalViews = computed(() => channels.value.reduce((s, c) => s + c.total_views, 0))
const totalVideos = computed(() => channels.value.reduce((s, c) => s + c.videos, 0))
const avgLikeRate = computed(() => channels.value.length ? (channels.value.reduce((s, c) => s + c.like_rate, 0) / channels.value.length).toFixed(2) : '0')
const weeklySubGain = computed(() => channels.value.reduce((s, c) => s + (c.weekly_growth?.has_weekly ? c.weekly_growth.subscribers_change : 0), 0))
const weeklyViewGain = computed(() => channels.value.reduce((s, c) => s + (c.weekly_growth?.has_weekly ? c.weekly_growth.views_change : 0), 0))
const weeklyVideoGain = computed(() => channels.value.reduce((s, c) => s + (c.weekly_growth?.has_weekly ? c.weekly_growth.videos_change : 0), 0))

const todaySubGain = computed(() => channels.value.reduce((s, c) => s + (c.growth?.has_prev ? c.growth.subscribers_change : 0), 0))
const todayViewGain = computed(() => channels.value.reduce((s, c) => s + (c.growth?.has_prev ? c.growth.views_change : 0), 0))
const todayVideoGain = computed(() => channels.value.reduce((s, c) => s + (c.growth?.has_prev ? c.growth.videos_change : 0), 0))

const anomalyCount = computed(() => channels.value.filter(c => {
  const lr = c.like_rate || 0
  const d1k = c.days_to_1k || 0
  const g = c.growth || {}
  return lr < 1 || d1k > 365 || (c.health && (c.health.includes('最差') || c.health.includes('零互动'))) || (g.has_prev && (g.subscribers_change < 0 || g.views_change_pct < -20))
}).length)

const dailySorted = computed(() => [...channels.value].sort((a, b) => {
  const ag = a.growth?.has_prev ? a.growth.subscribers_change : 0
  const bg = b.growth?.has_prev ? b.growth.subscribers_change : 0
  return bg - ag
}))

// All daily videos across channels
const allDailyVideos = computed(() => {
  const vids = []
  const details = data.value.channel_details || {}
  channels.value.forEach(c => {
    const det = details[c.name] || {}
    ;(det.recent_videos || []).forEach(v => vids.push({ ...v, _channel: c.name }))
  })
  vids.sort((a, b) => new Date(b.published_at || 0) - new Date(a.published_at || 0))
  return vids
})

const filteredDailyVideos = computed(() => {
  const vids = allDailyVideos.value
  if (dailyVidFilter.value === 'all') return vids.slice(0, 10)
  return vids.filter(v => v._channel === dailyVidFilter.value).slice(0, 10)
})

// Helpers
function fmtGain(v) { return v == null ? '-' : v > 0 ? `+${v.toLocaleString()}` : `${v.toLocaleString()}` }
function fmtPct(v) { return v == null ? '-' : v > 0 ? `+${v}%` : `${v}%` }
function fmtMinutes(m) { if (!m) return ''; return m >= 60 ? `${Math.round(m/60)}h` : `${m}m` }
function gainColor(v) { return v == null ? 'var(--text-dim)' : v > 0 ? 'var(--success)' : v < 0 ? 'var(--danger)' : 'var(--text-dim)' }
function scoreColor(s) { return s >= 7 ? 'var(--success)' : s >= 5 ? 'var(--accent)' : 'var(--danger)' }
function healthColor(h) {
  if (!h) return 'var(--text-muted)'
  if (h.includes('标杆')) return 'var(--success)'
  if (h.includes('最差') || h.includes('零互动')) return 'var(--danger)'
  if (h.includes('转化差')) return 'var(--accent)'
  return 'var(--text-muted)'
}
function sevIcon(s) { return s === 'critical' ? '🔴' : s === 'major' ? '🟡' : '🔵' }
function trendIcon(t) { return t === '增长' ? '📈' : t === '稳定' ? '➡️' : t === '放缓' ? '📉' : '🛑' }
function effortIcon(e) { return e === '低' ? '🟢' : e === '中' ? '🟡' : '🔴' }
function quadrantColor(name) {
  const map = { '爆款基因': '#4caf50', '标题超卖': '#ff9800', '门面拖累': '#2196f3', '选题失败': '#f44336' }
  return map[name] || 'var(--text-muted)'
}
const quadrantDesc = {
  '爆款基因': { label: '高CTR + 高留存', desc: '封面吸引人，内容也留得住人。', action: '复制它的标题封面模式和开头剪法' },
  '标题超卖': { label: '高CTR + 低留存', desc: '封面标题很能骗点击，但内容没兑现承诺。', action: '修开头30秒剪辑，别动标题' },
  '门面拖累': { label: '低CTR + 高留存', desc: '内容被证明是好的，但封面标题没人想点。', action: '只换封面标题重发，最划算的优化' },
  '选题失败': { label: '低CTR + 低留存', desc: '没人点、点了也不看，剧目本身不行。', action: '停止优化，记入选剧排除条件' },
  '样本不足': { label: '展示量<2000', desc: '数据太少，判了也不准。', action: '等展示量积累，不用处理' },
}
function fmtDate(d) { return d ? new Date(d).toLocaleDateString('zh-TW', { month: '2-digit', day: '2-digit' }) : '-' }
function calcLikeRate(views, likes) { return views > 0 ? (likes / views * 100).toFixed(2) : '0.00' }
function likeRateColor(views, likes) {
  const lr = views > 0 ? (likes / views * 100) : 0
  return lr >= 1.5 ? 'var(--success)' : lr >= 1.0 ? 'var(--accent)' : 'var(--danger)'
}
function ctrColor(ctr) { return ctr == null ? 'var(--text-dim)' : ctr >= 4 ? 'var(--success)' : ctr >= 2 ? 'var(--accent)' : 'var(--danger)' }
function retentionColor(pct) { return pct == null ? 'var(--text-dim)' : pct >= 10 ? 'var(--success)' : pct >= 5 ? 'var(--accent)' : 'var(--danger)' }
function retentionRingStyle(pct) {
  const p = Math.min(100, Math.max(0, Number(pct) || 0))
  const color = p >= 10 ? '#4caf50' : p >= 5 ? '#ff9800' : '#f44336'
  return { background: `conic-gradient(${color} 0% ${p}%, var(--border) ${p}% 100%)` }
}
function analyticsKey(ch) { return ch?.oauth?.slug || ch?.market || '' }
function yppMetrics(ch) {
  const subs = ch.subscribers || 0
  const oauth = ch.oauth || {}
  const watchMin = oauth.watch_minutes_30d || 0
  const watchHours = Math.round(watchMin / 60)
  const subsOk = subs >= 1000
  const watchOk = watchHours >= 4000
  const bothOk = subsOk && watchOk
  let status, reason
  if (bothOk) {
    status = 'eligible' // 达标，等YouTube审核
    reason = '已达标，等YouTube审批'
  } else {
    status = 'not_ready'
    reason = !subsOk ? `需${1000 - subs}更多订阅` : `需${4000 - watchHours}h更多观看`
  }
  return [
    { label: '展示次数', status, reason },
    { label: 'CTR 点击率', status, reason },
    { label: '年龄和性别', status, reason },
    { label: '字幕语言', status, reason },
    { label: '观看行为细分', status, reason },
  ]
}
function effPerK(oauth) { if (!oauth?.authorized || !oauth.views_30d || !oauth.subs_gained_30d) return 0; return (oauth.subs_gained_30d / oauth.views_30d * 1000).toFixed(1) }
function formatWatchTime(minutes) { if (!minutes) return '—'; if (minutes >= 60) return (minutes / 60).toFixed(0) + 'h'; return minutes + 'm' }
function formatDuration(seconds) { if (!seconds) return '—'; const m = Math.floor(seconds / 60); const s = Math.round(seconds % 60); return `${m}m${s}s` }
const oauthChannelCount = computed(() => channels.value.filter(c => c.oauth?.authorized).length)
const avgRetention = computed(() => {
  const authorized = channels.value.filter(c => c.oauth?.authorized && c.oauth?.avg_view_pct > 0)
  if (!authorized.length) return 0
  return (authorized.reduce((s, c) => s + c.oauth.avg_view_pct, 0) / authorized.length).toFixed(1)
})
const avgWatchDuration = computed(() => {
  const authorized = channels.value.filter(c => c.oauth?.authorized && c.oauth?.avg_view_duration > 0)
  if (!authorized.length) return '—'
  const avg = authorized.reduce((s, c) => s + c.oauth.avg_view_duration, 0) / authorized.length
  const m = Math.floor(avg / 60)
  const s = Math.round(avg % 60)
  return `${m}m${s}s`
})
const totalNetSubs = computed(() => {
  return channels.value
    .filter(c => c.oauth?.authorized)
    .reduce((s, c) => s + (c.oauth.subs_gained_30d || 0) - (c.oauth.subs_lost_30d || 0), 0)
})

function detectAnomalies(c) {
  const alerts = []
  const lr = c.like_rate || 0
  const d1k = c.days_to_1k || 0
  if (lr < 1) alerts.push('赞率低')
  if (d1k > 365) alerts.push('千订慢')
  if (c.health && (c.health.includes('最差') || c.health.includes('零互动'))) alerts.push('需关注')
  const g = c.growth || {}
  if (g.has_prev) {
    if (g.subscribers_change < 0) alerts.push('掉粉')
    if (g.views_change_pct < -20) alerts.push('播放骤降')
    if (g.like_rate_change < -0.5) alerts.push('赞率下跌')
    if (g.videos_change === 0) alerts.push('未发布')
  }
  return alerts
}

function toggleDetail(idx) {
  const s = new Set(expanded.value)
  if (s.has(idx)) s.delete(idx)
  else {
    s.add(idx)
    // 懒加载 OAuth 深度数据
    const ch = channels.value[idx]
    const aKey = analyticsKey(ch)
    if (ch?.oauth?.authorized && aKey && !analyticsData.value[aKey]) {
      api(`/yt-analytics?slug=${aKey}`).then(d => {
        analyticsData.value = { ...analyticsData.value, [aKey]: d }
      }).catch(() => {})
    }
  }
  expanded.value = s
}

const trafficLabelMap = { SUBSCRIBER: '订阅推送', RELATED_VIDEO: '推荐视频', YT_SEARCH: '搜索', YT_OTHER_PAGE: '其他页面', YT_CHANNEL: '频道页', END_SCREEN: '片尾画面', PLAYLIST: '播放列表', EXT_URL: '外部链接', NO_LINK_OTHER: '其他来源', NOTIFICATION: '通知' }
function trafficLabel(key) { return trafficLabelMap[key] || key }
const countryNameMap = {
  US: '美国', IN: '印度', PH: '菲律宾', MY: '马来西亚', GB: '英国',
  BD: '孟加拉', ID: '印尼', ZA: '南非', NG: '尼日利亚', CA: '加拿大',
  BR: '巴西', MX: '墨西哥', DE: '德国', FR: '法国', JP: '日本',
  KR: '韩国', TH: '泰国', VN: '越南', TR: '土耳其', EG: '埃及',
  PK: '巴基斯坦', RU: '俄罗斯', SA: '沙特', AE: '阿联酋', CO: '哥伦比亚', AR: '阿根廷'
}
const countryFlag = { US:'🇺🇸',IN:'🇮🇳',PH:'🇵🇭',MY:'🇲🇾',GB:'🇬🇧',BD:'🇧🇩',ID:'🇮🇩',ZA:'🇿🇦',NG:'🇳🇬',CA:'🇨🇦',BR:'🇧🇷',MX:'🇲🇽',DE:'🇩🇪',FR:'🇫🇷',JP:'🇯🇵',KR:'🇰🇷',TH:'🇹🇭',VN:'🇻🇳',TR:'🇹🇷',EG:'🇪🇬',PK:'🇵🇰',RU:'🇷🇺',SA:'🇸🇦',AE:'🇦🇪',CO:'🇨🇴',AR:'🇦🇷' }
function countryName(code) { return (countryFlag[code] || '') + ' ' + (countryNameMap[code] || code) }

const geoColors = ['#4fc3f7','#81c784','#ffb74d','#e57373','#ba68c8','#4dd0e1','#aed581']
function geoTotal(rows) { return rows.reduce((s, r) => s + r[1], 0) }
function trafficTotal(rows) { return rows.reduce((s, r) => s + r[1], 0) }
function donutStyle(rows) {
  const total = geoTotal(rows)
  if (!total) return {}
  const colors = geoColors
  let acc = 0
  const stops = rows.slice(0, 5).map((r, i) => {
    const pct = r[1] / total * 100
    const start = acc
    acc += pct
    return `${colors[i]} ${start}% ${acc}%`
  })
  if (acc < 100) stops.push(`var(--border) ${acc}% 100%`)
  return { background: `conic-gradient(${stops.join(',')})` }
}

function getDiag(name) { return diagScores.value[name] || {} }
function getChannelDiagnostics(name) { return getDiag(name).top_issues || [] }
function getChannelLlm(name) { return getDiag(name).channel_llm || null }
function getVideoTitle(name, videoId) {
  const map = getDiag(name).video_title_map || {}
  return map[videoId] || videoId
}

// 受众画像 helpers
function genderPct(demo, gender) {
  if (!demo?.length) return 0
  return demo.filter(d => d.gender === gender).reduce((s, d) => s + d.pct, 0).toFixed(0)
}
function genderDonutStyle(demo) {
  if (!demo?.length) return {}
  const female = demo.filter(d => d.gender === 'female').reduce((s, d) => s + d.pct, 0)
  const male = demo.filter(d => d.gender === 'male').reduce((s, d) => s + d.pct, 0)
  const total = female + male || 1
  return { background: `conic-gradient(#e57373 0% ${female/total*100}%, #4fc3f7 ${female/total*100}% 100%)` }
}
function topAgeGroups(demo) {
  if (!demo?.length) return []
  // 返回按性别分开的年龄组，含估算时长
  const result = []
  const ageOrder = ['13-17', '18-24', '25-34', '35-44', '45-54', '55-64', '65+']
  const groups = {}
  demo.forEach(d => {
    // API返回 'age18-24', 'age65-' 等格式，去掉前缀
    const normAge = d.age.replace(/^age/, '').replace(/-$/, '+')
    if (!groups[normAge]) groups[normAge] = { male: 0, female: 0, male_min: 0, female_min: 0 }
    groups[normAge][d.gender] = d.pct
    if (d.gender === 'male') groups[normAge].male_min = d.est_minutes || 0
    if (d.gender === 'female') groups[normAge].female_min = d.est_minutes || 0
  })
  ageOrder.forEach(age => {
    if (groups[age]) {
      if (groups[age].female > 0) result.push({ age, pct: Math.round(groups[age].female), gender: 'female', est_minutes: groups[age].female_min })
      if (groups[age].male > 0) result.push({ age, pct: Math.round(groups[age].male), gender: 'male', est_minutes: groups[age].male_min })
    }
  })
  return result.slice(0, 8)
}
function deviceLabel(type) {
  const map = { 'MOBILE': '📱移动', 'DESKTOP': '💻桌面', 'TABLET': '📱平板', 'TV': '📺电视', 'GAME_CONSOLE': '🎮游戏机' }
  return map[type] || type
}
function devicePct(c, views) {
  const aData = analyticsData.value[analyticsKey(c)]
  if (!aData?.device?.length) return 0
  const total = aData.device.reduce((s, d) => s + d.views, 0)
  return total ? Math.round(views / total * 100) : 0
}
function langName(lang) {
  const map = { 'zh-Hans': '中文', 'zh-Hant': '繁中', 'en': '英文', 'id': '印尼', 'tr': '土', 'pt': '葡', 'es': '西', 'ja': '日', 'ko': '韩', 'vi': '越', 'th': '泰', 'ar': '阿' }
  return map[lang] || lang?.substring(0, 3) || lang
}
function subLangPct(c, views) {
  const aData = analyticsData.value[analyticsKey(c)]
  if (!aData?.subtitle_lang?.length) return 0
  const total = aData.subtitle_lang.reduce((s, d) => s + d.views, 0)
  return total ? Math.round(views / total * 100) : 0
}
function watchTimePct(c, minutes) {
  const aData = analyticsData.value[analyticsKey(c)]
  if (!aData?.age_gender_watch?.length) return 0
  const max = Math.max(...aData.age_gender_watch.map(w => w.minutes))
  return max ? Math.round(minutes / max * 100) : 0
}
function weightMetrics(c) {
  const aData = analyticsData.value[analyticsKey(c)]
  if (!aData?.traffic?.rows) return []
  const traffic = aData.traffic.rows
  const total = trafficTotal(traffic)
  const browse = (traffic.find(r => r[0] === 'RELATED_VIDEO')?.[1] || 0) / total * 100
  const sub = (traffic.find(r => r[0] === 'SUBSCRIBER')?.[1] || 0) / total * 100
  const search = (traffic.find(r => r[0] === 'YT_SEARCH')?.[1] || 0) / total * 100
  const ret = c.oauth?.avg_view_pct || 0
  return [
    { label: '推荐流量', pct: Math.min(100, browse), value: browse.toFixed(0) + '%', color: browse > 40 ? '#4caf50' : browse > 20 ? '#ff9800' : '#f44336' },
    { label: '订阅流量', pct: Math.min(100, sub), value: sub.toFixed(0) + '%', color: sub > 25 ? '#4caf50' : sub > 15 ? '#ff9800' : '#f44336' },
    { label: '搜索流量', pct: Math.min(100, search), value: search.toFixed(0) + '%', color: search > 15 ? '#4caf50' : search > 5 ? '#ff9800' : '#f44336' },
    { label: '留存率', pct: Math.min(100, ret), value: ret.toFixed(1) + '%', color: ret > 10 ? '#4caf50' : ret > 5 ? '#ff9800' : '#f44336' },
  ]
}
function weightLevel(c) {
  const metrics = weightMetrics(c)
  if (!metrics.length) return { label: '未知', color: 'var(--text-dim)' }
  const score = metrics.reduce((s, m) => {
    const v = parseFloat(m.value)
    if (m.label === '推荐流量') return s + (v > 40 ? 3 : v > 20 ? 2 : v > 10 ? 1 : 0)
    if (m.label === '订阅流量') return s + (v > 25 ? 2 : v > 15 ? 1 : 0)
    if (m.label === '留存率') return s + (v > 15 ? 3 : v > 10 ? 2 : v > 5 ? 1 : 0)
    return s
  }, 0)
  if (score >= 7) return { label: '强（算法高度信任）', color: '#4caf50' }
  if (score >= 4) return { label: '中（算法在测试）', color: '#ff9800' }
  return { label: '弱（算法信任度低）', color: '#f44336' }
}

function getMergedVideos(name) {
  const details = data.value.channel_details || {}
  const det = details[name] || {}
  const vids = det.recent_videos || det.top_videos || []
  const diag = getDiag(name)
  const diagMap = {}
  ;(diag.video_scores || []).forEach(vs => { diagMap[vs.video_id] = vs })
  // 建立 OAuth video 数据映射（retention, watch time）
  const ch = channels.value.find(c => c.name === name)
  const oauthVideoMap = {}
  if (ch?.oauth?.authorized && ch?.market && analyticsData.value[ch.market]?.top_videos?.rows) {
    analyticsData.value[ch.market].top_videos.rows.forEach(row => {
      oauthVideoMap[row[0]] = { retention: row.length > 5 ? row[5] : null, watchMin: row[3] || null }
    })
  }
  const merged = vids.map(v => {
    const vd = diagMap[v.video_id] || {}
    const ov = oauthVideoMap[v.video_id] || {}
    return { ...v, _score: vd.score || 0, _issues: vd.issues || [], _optTitles: vd.optimized_titles || [], _titleAnalysis: vd.title_analysis || null, _coverSynergy: vd.cover_synergy || null, _retention: ov.retention ?? null, _watchMin: ov.watchMin ?? null }
  })
  merged.sort((a, b) => new Date(b.published_at || 0) - new Date(a.published_at || 0))
  return merged
}

onMounted(async () => {
  try {
    const d = await api('/channel-analysis')
    data.value = d
  } catch (err) { console.error('[ChannelAnalysis]', err) }
  finally { loading.value = false }
})
</script>
