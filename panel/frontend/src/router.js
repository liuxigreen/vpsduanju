import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/upload' },
  { path: '/upload', name: 'upload', component: () => import('./views/Upload.vue'), meta: { title: '上架助手', icon: '▲' } },
  { path: '/youtube', name: 'youtube', component: () => import('./views/YouTube.vue'), meta: { title: 'YouTube 频道', icon: '▶' } },
  { path: '/channel-analysis', name: 'channel-analysis', component: () => import('./views/ChannelAnalysis.vue'), meta: { title: '自有账号分析', icon: '📊' } },
  { path: '/competitor-channels', name: 'competitor-channels', component: () => import('./views/CompetitorChannels.vue'), meta: { title: '竞品频道', icon: '🔎' } },
  { path: '/distill', name: 'distill', component: () => import('./views/Distill.vue'), meta: { title: '蒸馏数据', icon: '🧪' } },
  { path: '/review', name: 'review', component: () => import('./views/Review.vue'), meta: { title: '待审核', icon: '👁' } }
]

export const router = createRouter({
  history: createWebHashHistory(),
  routes
})

export const navItems = routes
  .filter(r => r.meta)
  .map(r => ({ name: r.name, ...r.meta }))
