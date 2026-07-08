/**
 * 工具函数 — 从原 index_v3.html 提取，逻辑不变
 */

export function safeChannelUrl(channelId) {
  if (!channelId || typeof channelId !== 'string') return '#'
  if (/^UC[\w-]{22}$/.test(channelId)) {
    return 'https://www.youtube.com/channel/' + encodeURIComponent(channelId)
  }
  return '#'
}

export function escapeHtml(t) {
  if (!t) return ''
  return String(t)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function formatNumber(n) {
  if (n == null) return '-'
  return Number(n).toLocaleString()
}

export function formatSubs(n) {
  if (n == null) return '-'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

export function formatPercent(n) {
  if (n == null) return '-'
  const sign = n >= 0 ? '+' : ''
  return sign + n.toFixed(1) + '%'
}

export function formatDate(d) {
  if (!d) return '-'
  return new Date(d).toLocaleDateString('zh-CN')
}

export function copyText(text) {
  navigator.clipboard.writeText(text).catch(() => {
    // fallback: textarea
    const el = document.createElement('textarea')
    el.value = text
    document.body.appendChild(el)
    el.select()
    document.execCommand('copy')
    document.body.removeChild(el)
  })
}

export function getChannelGenres(ch) {
  if (!ch) return []
  if (ch.genres && ch.genres.length) return ch.genres
  if (ch.tags) return ch.tags.filter(t => !['short drama', 'drama', 'shorts'].includes(t.toLowerCase()))
  return []
}

export function tierClass(tier) {
  const map = { head: 'tier-head', mid: 'tier-mid', rising: 'tier-rising', new: 'tier-new' }
  return map[tier] || 'tier-new'
}

export function tierLabel(tier) {
  const map = { head: '头部', mid: '中部', rising: '新锐', new: '新发现' }
  return map[tier] || tier
}
