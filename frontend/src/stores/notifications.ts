import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { notificationsApi, type NotificationItem } from '@/api/notifications'
import { useAuthStore } from '@/stores/auth'

export const useNotificationStore = defineStore('notifications', () => {
  const items = ref<NotificationItem[]>([])
  const unreadCount = ref(0)
  const loading = ref(false)
  const drawerVisible = ref(false)

  // SSE 连接状态
  const sse = ref<EventSource | null>(null)
  const sseConnected = ref(false)
  let reconnectTimer: any = null

  const hasUnread = computed(() => unreadCount.value > 0)

  async function refreshUnreadCount() {
    try {
      const res = await notificationsApi.getUnreadCount()
      unreadCount.value = res?.data?.count ?? 0
    } catch {
      // noop
    }
  }

  async function loadList(status: 'unread' | 'all' = 'all') {
    loading.value = true
    try {
      const res = await notificationsApi.getList({ status, page: 1, page_size: 20 })
      items.value = res?.data?.items ?? []
    } catch {
      items.value = []
    } finally {
      loading.value = false
    }
  }

  async function markRead(id: string) {
    await notificationsApi.markRead(id)
    const idx = items.value.findIndex(x => x.id === id)
    if (idx !== -1) items.value[idx].status = 'read'
    if (unreadCount.value > 0) unreadCount.value -= 1
  }

  async function markAllRead() {
    await notificationsApi.markAllRead()
    items.value = items.value.map(x => ({ ...x, status: 'read' }))
    unreadCount.value = 0
  }

  function addNotification(n: Omit<NotificationItem, 'id' | 'status' | 'created_at'> & { id?: string; created_at?: string; status?: 'unread' | 'read' }) {
    const id = n.id || `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const created_at = n.created_at || new Date().toISOString()
    const item: NotificationItem = {
      id,
      title: n.title,
      content: n.content,
      type: n.type,
      status: n.status ?? 'unread',
      created_at,
      link: n.link,
      source: n.source
    }
    items.value.unshift(item)
    if (item.status === 'unread') unreadCount.value += 1
  }

  function connectSSE() {
    try {
      // 若已存在连接，先关闭
      if (sse.value) {
        try { sse.value.close() } catch {}
        sse.value = null
      }
      if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }

      const authStore = useAuthStore()
      const token = authStore.token || localStorage.getItem('auth-token') || ''
      const base = (import.meta.env.VITE_API_BASE_URL || '')
      const url = `${base}/api/notifications/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`.replace(/\/+$/, '')

      const es = new EventSource(url)
      sse.value = es

      es.onopen = () => { sseConnected.value = true }
      es.onerror = () => {
        sseConnected.value = false
        // 简单重连策略
        if (!reconnectTimer) {
          reconnectTimer = setTimeout(() => connectSSE(), 3000)
        }
      }

      es.addEventListener('notification', (ev: MessageEvent) => {
        try {
          const data = JSON.parse(ev.data)
          if (data && data.title && data.type) {
            addNotification({
              id: data.id,
              title: data.title,
              content: data.content,
              type: data.type,
              link: data.link,
              source: data.source,
              created_at: data.created_at,
              status: data.status || 'unread'
            })
          }
        } catch {}
      })

      es.addEventListener('heartbeat', () => { /* 保持连接，无操作 */ })
    } catch {
      sseConnected.value = false
    }
  }

  function disconnectSSE() {
    try { if (sse.value) sse.value.close() } catch {}
    sse.value = null
    sseConnected.value = false
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  }

  function setDrawerVisible(v: boolean) {
    drawerVisible.value = v
  }

  return {
    items,
    unreadCount,
    hasUnread,
    loading,
    drawerVisible,
    sseConnected,
    refreshUnreadCount,
    loadList,
    markRead,
    markAllRead,
    addNotification,
    connectSSE,
    disconnectSSE,
    setDrawerVisible
  }
})
