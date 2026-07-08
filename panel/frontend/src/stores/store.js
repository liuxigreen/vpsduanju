import { reactive } from 'vue'

export const store = reactive({
  // YouTube 账号管理
  currentYtSlug: 'default',

  // 全局 loading
  loading: { show: false, text: '' },

  // Toast 通知
  toast: { show: false, msg: '', type: 'error' },

  // AI 聊天弹窗
  aiOpen: false
})

// Toast 自动消失
let toastTimer = null
export function showToast(msg, type = 'error', duration = 4000) {
  store.toast = { show: true, msg, type }
  clearTimeout(toastTimer)
  toastTimer = setTimeout(() => { store.toast.show = false }, duration)
}

export function showLoading(text = '加载中…') {
  store.loading = { show: true, text }
}

export function hideLoading() {
  store.loading.show = false
}
