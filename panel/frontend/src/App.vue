<template>
  <!-- Loading Overlay -->
  <div class="loading-overlay" :class="{ active: store.loading.show }">
    <div class="spinner"></div>
    <div class="loading-text">{{ store.loading.text }}</div>
  </div>

  <!-- Toast -->
  <Transition name="fade">
    <div v-if="store.toast.show" class="toast" :class="store.toast.type">
      {{ store.toast.msg }}
    </div>
  </Transition>

  <div class="app">
    <!-- Sidebar -->
    <nav class="sidebar">
      <div class="brand">Duanju</div>
      <div class="brand-sub">短剧出海运营系统</div>

      <router-link
        v-for="item in navItems"
        :key="item.name"
        :to="{ name: item.name }"
        class="nav-item"
        :class="{ active: $route.name === item.name }"
      >
        <span class="icon">{{ item.icon }}</span>
        {{ item.title }}
      </router-link>

      <div style="margin-top: auto; padding-top: 40px; border-top: 1px solid var(--border-subtle);">
        <div style="font-size: 11px; color: var(--text-dim); line-height: 1.8;">
          <div>nuwa v3 engine</div>
          <div class="mono">3 experts active</div>
        </div>
      </div>
    </nav>

    <!-- Main -->
    <main class="main">
      <Transition name="fade" mode="out-in">
        <router-view />
      </Transition>
    </main>
  </div>

  <!-- AI Float Button (可拖动) -->
  <button
    class="ai-float"
    ref="aiFloatBtn"
    :style="{ left: aiBtnPos.x + 'px', top: aiBtnPos.y + 'px', right: 'auto', bottom: 'auto' }"
    @mousedown.prevent="startDrag"
    @touchstart.passive="startDrag"
    @click="handleAiClick"
    title="AI 助手"
  >◇</button>

  <!-- AI Popup -->
  <Transition name="fade">
    <div v-if="store.aiOpen" class="ai-popup">
      <div class="ai-popup-header">
        <span>🤖 AI 助手</span>
        <button class="ai-popup-close" @click="store.aiOpen = false">×</button>
      </div>
      <div class="ai-popup-messages" ref="chatMessages">
        <div class="chat-msg ai">
          你好，我是 nuwa 专家系统。可以帮你分析短剧市场、生成标题封面、诊断频道数据。有什么可以帮你的？
        </div>
        <div v-for="(msg, i) in chatHistory" :key="i" class="chat-msg" :class="msg.role">
          {{ msg.text }}
        </div>
      </div>
      <div class="ai-popup-input">
        <input
          v-model="chatInput"
          type="text"
          placeholder="输入问题…"
          @keydown.enter="sendChat"
        />
        <button class="btn btn-primary btn-sm" @click="sendChat">发送</button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, reactive, nextTick, onMounted, onUnmounted } from 'vue'
import { store } from './stores/store.js'
import { api } from './api/index.js'
import { navItems } from './router.js'

const chatInput = ref('')
const chatHistory = ref([])
const chatMessages = ref(null)
const aiFloatBtn = ref(null)

// ── AI 按钮拖动 ──
const aiBtnPos = reactive({ x: 0, y: 0 })
let dragging = false
let dragMoved = false
let offsetX = 0
let offsetY = 0

function initBtnPos() {
  aiBtnPos.x = window.innerWidth - 84
  aiBtnPos.y = window.innerHeight - 84
}

function startDrag(e) {
  dragging = true
  dragMoved = false
  const touch = e.touches ? e.touches[0] : e
  offsetX = touch.clientX - aiBtnPos.x
  offsetY = touch.clientY - aiBtnPos.y
  document.addEventListener('mousemove', onDrag, { passive: false })
  document.addEventListener('mouseup', stopDrag)
  document.addEventListener('touchmove', onDrag, { passive: false })
  document.addEventListener('touchend', stopDrag)
}

function onDrag(e) {
  if (!dragging) return
  e.preventDefault()
  dragMoved = true
  const touch = e.touches ? e.touches[0] : e
  const x = touch.clientX - offsetX
  const y = touch.clientY - offsetY
  aiBtnPos.x = Math.max(0, Math.min(window.innerWidth - 56, x))
  aiBtnPos.y = Math.max(0, Math.min(window.innerHeight - 56, y))
}

function stopDrag() {
  dragging = false
  document.removeEventListener('mousemove', onDrag)
  document.removeEventListener('mouseup', stopDrag)
  document.removeEventListener('touchmove', onDrag)
  document.removeEventListener('touchend', stopDrag)
}

function handleAiClick() {
  if (!dragMoved) store.aiOpen = !store.aiOpen
}

async function sendChat() {
  const q = chatInput.value.trim()
  if (!q) return
  chatInput.value = ''
  chatHistory.value.push({ role: 'user', text: q })

  try {
    // 传完整历史给后端，后端拼成带上下文的 prompt
    const d = await api('/nuwa_chat', {
      method: 'POST',
      body: JSON.stringify({
        prompt: q,
        history: chatHistory.value.slice(0, -1).slice(-10)  // 最近10条，不含当前
      })
    })
    chatHistory.value.push({ role: 'ai', text: d.response || d.error || '无回复' })
  } catch {
    chatHistory.value.push({ role: 'ai', text: '请求失败，请重试' })
  }

  await nextTick()
  if (chatMessages.value) {
    chatMessages.value.scrollTop = chatMessages.value.scrollHeight
  }
}

onMounted(() => {
  initBtnPos()
  window.addEventListener('resize', initBtnPos)
})

onUnmounted(() => {
  window.removeEventListener('resize', initBtnPos)
  stopDrag()
})
</script>
