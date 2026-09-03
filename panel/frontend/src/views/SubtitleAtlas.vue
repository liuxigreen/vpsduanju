<template>
  <div>
    <div class="card" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">
      <div>
        <h2 style="margin:0;font-size:17px;">🎬 内容库</h2>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">
          {{ total }} 条字幕实证视频 · 内容级分析（题材/钩子/反转/台词/证据引用）· 优先级高于标题推断
        </div>
      </div>
      <button class="btn" @click="load(1)">↻ 刷新</button>
    </div>

    <!-- 过滤栏 -->
    <div class="card" style="margin-top:14px;display:flex;flex-wrap:wrap;gap:8px;align-items:center;">
      <select v-model="f.lang" @change="load(1)" class="filter-sel">
        <option value="">全部语种</option>
        <option v-for="o in langOpts" :key="o.v" :value="o.v">{{ o.t }}</option>
      </select>
      <select v-model="f.genre" @change="load(1)" class="filter-sel">
        <option value="">全部题材</option>
        <option v-for="g in genreOpts" :key="g" :value="g">{{ g }}</option>
      </select>
      <select v-model="f.hook" @change="load(1)" class="filter-sel">
        <option value="">全部钩子</option>
        <option v-for="h in hookOpts" :key="h" :value="h">{{ h }}</option>
      </select>
      <select v-model="f.tier" @change="load(1)" class="filter-sel">
        <option value="">全部批次</option>
        <option value="P0">P0 动量精选</option>
        <option value="P1">P1 全量</option>
      </select>
      <select v-model="f.trans" @change="load(1)" class="filter-sel">
        <option value="">翻译剧全部</option>
        <option value="1">翻译剧</option>
        <option value="0">本地原创</option>
      </select>
      <select v-model="f.min_views" @change="load(1)" class="filter-sel">
        <option value="">播放不限</option>
        <option value="10000">≥1万</option>
        <option value="50000">≥5万</option>
        <option value="200000">≥20万</option>
        <option value="1000000">≥100万</option>
      </select>
      <input v-model.trim="q" @keyup.enter="load(1)" placeholder="搜标题/频道…" class="filter-sel" style="flex:1;min-width:140px;" />
      <button class="btn btn-sm" @click="load(1)">搜索</button>
      <button class="btn btn-sm" @click="reset" title="清空过滤">✕</button>
    </div>

    <!-- 列表 -->
    <div class="card" style="margin-top:14px;">
      <div v-if="error" style="color:#e74c3c;font-size:12px;">{{ error }}</div>
      <div v-else-if="!items.length && !loading" style="color:var(--text-muted);font-size:12px;padding:10px 0;">
        没有匹配的视频，试试放宽过滤条件
      </div>
      <div v-for="it in items" :key="it.video_id" @click="openDetail(it.video_id)"
           style="display:flex;align-items:center;gap:10px;padding:8px 6px;border-bottom:1px solid var(--border-subtle);cursor:pointer;"
           @mouseenter="$event.currentTarget.style.background='var(--bg-elevated)'" @mouseleave="$event.currentTarget.style.background=''">
        <div style="flex:1;min-width:0;">
          <div style="font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{{ it.title || it.video_id }}</div>
          <div style="font-size:10px;color:var(--text-dim);margin-top:2px;display:flex;gap:6px;flex-wrap:wrap;align-items:center;">
            <span>{{ it.channel }}</span>
            <span style="color:#4ecdc4;">{{ langName(it.lang_code) }}</span>
            <span>{{ fmtN(it.views) }} 播放</span>
            <span v-if="it.duration_min">{{ it.duration_min }}min</span>
            <span v-for="g in (it.l1 || []).slice(0, 2)" :key="g" style="background:rgba(52,152,219,0.12);color:#3498db;padding:0 5px;border-radius:3px;">{{ g }}</span>
            <span v-if="it.hook" style="background:rgba(230,126,34,0.12);color:#e67e22;padding:0 5px;border-radius:3px;">🪝 {{ it.hook }}<template v-if="it.hook_sec != null"> {{ it.hook_sec }}s</template></span>
            <span v-if="it.translated" style="color:var(--text-dim);">翻译剧</span>
            <span style="color:var(--text-dim);opacity:0.7;">{{ it.tier }} · {{ it.model_family }}</span>
          </div>
        </div>
        <div style="flex-shrink:0;font-size:11px;color:var(--text-muted);">conf {{ it.confidence != null ? it.confidence : '–' }}</div>
      </div>
      <!-- 分页 -->
      <div style="display:flex;justify-content:space-between;align-items:center;padding-top:10px;font-size:11px;color:var(--text-muted);">
        <span>共 {{ total }} 条 · 第 {{ page }}/{{ totalPages }} 页</span>
        <div style="display:flex;gap:6px;">
          <button class="btn btn-sm" :disabled="page <= 1" @click="load(page - 1)">← 上一页</button>
          <button class="btn btn-sm" :disabled="page >= totalPages" @click="load(page + 1)">下一页 →</button>
        </div>
      </div>
    </div>

    <!-- 详情弹层 -->
    <div v-if="detail" style="position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:1000;overflow-y:auto;padding:20px;" @click.self="detail = null">
      <div style="background:var(--bg-card,#16213e);border:1px solid var(--border,#2a2a4a);border-radius:12px;max-width:760px;margin:30px auto;padding:22px;">
        <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;">
          <h3 style="margin:0;font-size:15px;line-height:1.5;">{{ detail.title }}</h3>
          <button class="btn btn-sm" @click="detail = null">✕</button>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;font-size:10px;margin:10px 0;align-items:center;">
          <span style="color:#4ecdc4;">{{ langName(detail.lang_code) }}</span>
          <span>{{ detail.channel }}</span>
          <span>{{ fmtN(detail.views) }} 播放</span>
          <span v-if="detail.duration_sec">{{ Math.round(detail.duration_sec / 60) }}min</span>
          <span v-for="g in (detail.l1 || [])" :key="g" style="background:rgba(52,152,219,0.12);color:#3498db;padding:1px 6px;border-radius:3px;">{{ g }}</span>
          <span v-for="g in (detail.l2 || []).slice(0, 4)" :key="g" style="color:var(--text-dim);border:1px solid var(--border);padding:1px 6px;border-radius:3px;">{{ g }}</span>
          <span v-if="detail.translated" style="background:rgba(155,89,182,0.15);color:#9b59b6;padding:1px 6px;border-radius:3px;">翻译剧</span>
          <span style="color:var(--text-dim);">{{ detail.tier }} · {{ detail.model_family }} · conf {{ detail.confidence }}</span>
          <a :href="'https://www.youtube.com/watch?v=' + detail.video_id" target="_blank" style="color:#3498db;">▶ YouTube</a>
        </div>

        <div v-if="detail.synopsis" style="font-size:13px;line-height:1.7;margin:10px 0;">{{ detail.synopsis }}</div>

        <div v-if="detail.hook && detail.hook.type" style="margin:12px 0;padding:10px;border:1px solid var(--border);border-radius:8px;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px;">开场钩子</div>
          <div style="font-size:12.5px;">
            <span style="background:rgba(230,126,34,0.15);color:#e67e22;padding:1px 8px;border-radius:4px;">🪝 {{ detail.hook.type }}</span>
            <span v-if="detail.hook.sec != null" style="color:#e67e22;margin-left:6px;">第 {{ detail.hook.sec }} 秒</span>
          </div>
          <div v-if="detail.hook.event" style="font-size:11px;color:var(--text-muted);margin-top:4px;">{{ detail.hook.event }}</div>
        </div>

        <div v-if="reveals.length" style="margin:12px 0;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:6px;">关键反转时间轴（按片长位置）</div>
          <div style="position:relative;height:34px;background:var(--bg-elevated);border-radius:6px;">
            <div v-for="(r, i) in reveals" :key="i"
                 :style="{ position: 'absolute', left: Math.min(Math.max(r.pct, 2), 96) + '%', top: '2px', transform: 'translateX(-50%)', fontSize: '9px', color: '#e67e22', textAlign: 'center' }">
              <div style="width:1px;height:14px;background:#e67e22;margin:0 auto;"></div>
              <div style="margin-top:2px;white-space:nowrap;">{{ r.label }}</div>
            </div>
          </div>
          <div v-for="(r, i) in reveals" :key="'t' + i" style="font-size:10.5px;color:var(--text-muted);margin-top:3px;">
            <span style="color:#e67e22;">{{ r.label }}</span> {{ r.event }}
          </div>
        </div>

        <div v-if="(detail.characters || []).length" style="margin:12px 0;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px;">角色</div>
          <div style="display:flex;gap:6px;flex-wrap:wrap;">
            <span v-for="c in detail.characters" :key="c.name" style="font-size:11px;background:var(--bg-elevated);padding:2px 8px;border-radius:4px;" :title="c.role">{{ c.name }}</span>
          </div>
        </div>

        <div v-if="(detail.distinctive_lines || []).length" style="margin:12px 0;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px;">高辨识度台词（可用于反查国内原剧）</div>
          <div v-for="(l, i) in detail.distinctive_lines" :key="i" style="font-size:11.5px;padding:4px 8px;border-left:2px solid #3498db;margin-top:4px;color:var(--text-muted);">{{ l }}</div>
        </div>

        <div v-if="evidencePairs.length" style="margin:12px 0;">
          <div style="font-size:10px;color:var(--text-muted);margin-bottom:4px;">证据引用（题材判断的字幕原句依据）</div>
          <div v-for="(v, k) in evidencePairs" :key="k" style="font-size:11.5px;margin-top:4px;">
            <span style="background:rgba(46,204,113,0.12);color:#2ecc71;padding:1px 6px;border-radius:3px;">{{ k }}</span>
            <span style="color:var(--text-muted);margin-left:6px;">「{{ v }}」</span>
          </div>
        </div>

        <div v-if="detail.origin_reason" style="font-size:10.5px;color:var(--text-dim);margin-top:10px;">翻译剧判定依据：{{ detail.origin_reason }}</div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, reactive, computed, watch } from 'vue'
import { useRoute } from 'vue-router'

const LANG_NAMES = { en: '英文', id: '印尼', pt: '葡萄牙', es: '西语', 'zh-Hant': '繁中', ja: '日语', tr: '土耳其' }
const HOOKS = ['身份反差', '关系背叛', '情绪爆点', '反转打脸', '补偿回报', '时间改命', '系统异能']

export default {
  name: 'SubtitleAtlas',
  setup() {
    const route = useRoute()
    const items = ref([]), total = ref(0), page = ref(1), loading = ref(false), error = ref('')
    const detail = ref(null), q = ref('')
    const f = reactive({ lang: '', genre: '', hook: '', tier: '', trans: '', min_views: '' })
    const genreOpts = ref([])
    const langOpts = Object.entries(LANG_NAMES).map(([v, t]) => ({ v, t }))
    const pageSize = 50
    const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

    async function load(p = 1) {
      loading.value = true; error.value = ''
      page.value = p
      const qs = new URLSearchParams({ page: p, page_size: pageSize })
      for (const k of ['lang', 'genre', 'hook', 'tier', 'trans', 'min_views']) if (f[k]) qs.set(k, f[k])
      if (q.value) qs.set('q', q.value)
      try {
        const r = await fetch('/api/subtitle-library?' + qs.toString())
        const d = await r.json()
        if (d.error) { error.value = d.error; items.value = [] } else { items.value = d.items || []; total.value = d.total || 0 }
      } catch (e) { error.value = String(e) }
      loading.value = false
    }
    function reset() {
      Object.keys(f).forEach(k => { f[k] = '' }); q.value = ''; load(1)
    }
    async function openDetail(id) {
      detail.value = null
      try { detail.value = await (await fetch('/api/subtitle-detail?id=' + id)).json() } catch (e) { detail.value = { title: '加载失败', video_id: id } }
    }
    function fmtN(n) {
      n = n || 0
      if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M'
      if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K'
      return n
    }
    function langName(c) { return LANG_NAMES[c] || c || '–' }
    // 从图谱接口拿题材选项（已缓存，几乎零成本）；支持 ?genre=&lang= 深链（蓝海雷达跳转用）
    fetch('/api/knowledge-graph').then(r => r.json()).then(d => {
      genreOpts.value = (d.genre_rank || []).map(x => x.genre).slice(0, 40)
    }).catch(() => {})
    function applyQuery() {
      if (route.query.genre) f.genre = String(route.query.genre)
      if (route.query.lang) f.lang = String(route.query.lang)
      if (route.query.hook) f.hook = String(route.query.hook)
      load(1)
    }
    applyQuery()
    watch(() => route.query, applyQuery)

    const reveals = computed(() => {
      const dur = detail.value?.duration_sec || 0
      return (detail.value?.key_reveals || [])
        .filter(r => r.at_sec != null)
        .map(r => ({
          pct: dur ? Math.round(r.at_sec / dur * 100) : 50,
          label: dur ? Math.round(r.at_sec / dur * 100) + '%' : (r.at_sec + 's'),
          event: r.event || '',
        })).slice(0, 6)
    })
    const evidencePairs = computed(() => {
      const ev = detail.value?.evidence || {}
      const out = {}
      for (const [k, v] of Object.entries(ev)) if (typeof v === 'string' && v) out[k] = v.slice(0, 60)
      return out
    })

    return { items, total, page, totalPages, loading, error, detail, q, f, genreOpts, langOpts, hookOpts: HOOKS,
             load, reset, openDetail, fmtN, langName, reveals, evidencePairs }
  },
}
</script>

<style scoped>
.filter-sel {
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 6px;
  padding: 5px 8px;
  font-size: 12px;
}
</style>
