import { showToast } from '../stores/store.js'

// ── 请求去重 ──
const inflight = new Map()

// ── 内存缓存 ──
const cache = new Map()

// 缓存 TTL 配置（毫秒），未列出的默认不缓存
const CACHE_TTL = {
  '/channel-analysis': 5 * 60_000,
  '/competitor-channels': 5 * 60_000,
  '/market-insights': 10 * 60_000,
  '/distill': 10 * 60_000,
  '/distill-detail': 10 * 60_000,
  '/yt-accounts': 2 * 60_000,
  '/yt-analytics': 3 * 60_000,
  '/proposal-history': 2 * 60_000,
  '/review': 1 * 60_000,
}

function getCacheTTL(path) {
  // 精确匹配
  if (CACHE_TTL[path]) return CACHE_TTL[path]
  // 前缀匹配（如 /api/distill-detail?lang=xxx）
  for (const [prefix, ttl] of Object.entries(CACHE_TTL)) {
    if (path.startsWith(prefix)) return ttl
  }
  return 0 // 默认不缓存
}

/**
 * 统一 API 封装
 * - GET 请求自动内存缓存（TTL 按端点配置）
 * - 并发去重
 * - 4xx/5xx 统一 toast
 */
export async function api(path, opts = {}) {
  const url = `/api${path}`
  const method = (opts.method || 'GET').toUpperCase()
  const cacheKey = url + (opts.body || '')

  // GET 请求：检查缓存
  if (method === 'GET') {
    const ttl = getCacheTTL(path)
    if (ttl > 0) {
      const cached = cache.get(cacheKey)
      if (cached && Date.now() - cached.time < ttl) {
        return cached.data
      }
    }
  }

  // 去重
  const inflightKey = method + ':' + cacheKey
  if (inflight.has(inflightKey)) return inflight.get(inflightKey)

  const promise = fetch(url, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts
  })
    .then(async r => {
      if (!r.ok) {
        let msg = `${r.status} ${r.statusText}`
        try {
          const body = await r.json()
          if (body.error || body.detail) msg = body.error || body.detail
        } catch (err) { console.error('[index]', err) }
        throw new Error(msg)
      }
      return r.json()
    })
    .then(data => {
      // GET 成功：写入缓存
      if (method === 'GET' && getCacheTTL(path) > 0) {
        cache.set(cacheKey, { data, time: Date.now() })
      }
      return data
    })
    .catch(err => {
      showToast(err.message || '请求失败', 'error')
      throw err
    })
    .finally(() => {
      inflight.delete(inflightKey)
    })

  inflight.set(inflightKey, promise)
  return promise
}

/**
 * POST 请求快捷方法
 * 自动清除相关缓存
 */
export function apiPost(path, data) {
  return api(path, {
    method: 'POST',
    body: JSON.stringify(data)
  }).then(result => {
    // POST 成功后清除相关 GET 缓存
    invalidateRelated(path)
    return result
  })
}

/**
 * 清除与 POST 端点相关的 GET 缓存
 */
function invalidateRelated(postPath) {
  const invalidations = {
    '/review/approve': ['/review'],
    '/review/reject': ['/review'],
    '/review/run': ['/review'],
    '/proposal': ['/proposal-history'],
    '/generate-titles': ['/proposal-history'],
    '/generate': [],
    '/yt-new-auth': ['/yt-accounts'],
    '/yt-auth-url': ['/yt-accounts'],
  }
  const targets = invalidations[postPath]
  if (!targets) return

  for (const [key] of cache) {
    if (targets.some(t => key.includes(t))) {
      cache.delete(key)
    }
  }
}

/**
 * 手动清除指定端点缓存
 */
export function invalidateCache(path) {
  const url = `/api${path}`
  for (const [key] of cache) {
    if (key.startsWith(url)) cache.delete(key)
  }
}
