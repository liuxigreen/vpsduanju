import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/briefing' },
  { path: '/briefing', name: 'briefing', component: () => import('./views/Briefing.vue'), meta: { title: '今日简报', icon: '☀' } },
  { path: '/upload', name: 'upload', component: () => import('./views/Upload.vue'), meta: { title: '上架助手', icon: '▲', hidden: true } },
  { path: '/youtube', name: 'youtube', component: () => import('./views/YouTube.vue'), meta: { title: 'YouTube 频道', icon: '▶' } },
  { path: '/channel-analysis', name: 'channel-analysis', component: () => import('./views/ChannelAnalysis.vue'), meta: { title: '自有账号分析', icon: '📊' } },
  { path: '/competitor-channels', name: 'competitor-channels', component: () => import('./views/CompetitorChannels.vue'), meta: { title: '竞品频道', icon: '🔎' } },
  { path: '/knowledge-graph', name: 'knowledge-graph', component: () => import('./views/KnowledgeGraph.vue'), meta: { title: '知识图谱', icon: '🕸' } },
  { path: '/competitor-alerts', name: 'competitor-alerts', component: () => import('./views/CompetitorAlerts.vue'), meta: { title: '爆款预警', icon: '🔔' } },
  { path: '/distill', name: 'distill', component: () => import('./views/Distill.vue'), meta: { title: '蒸馏数据(已冻结)', icon: '🧪', hidden: true } },
  { path: '/review', name: 'review', component: () => import('./views/Review.vue'), meta: { title: '待审核', icon: '👁' } }
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export const navItems = routes
  .filter(r => r.meta && !r.meta.hidden)
  .map(r => ({ name: r.name, ...r.meta }))
