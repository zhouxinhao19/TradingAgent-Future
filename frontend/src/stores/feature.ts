/**
 * Feature Flag Pinia Store(Phase 3a)
 *
 * - 应用启动时从后端 /api/config/features 拉一次,缓存到本地
 * - SidebarMenu 读此 store 条件渲染菜单
 * - Router 守卫(beforeEach)读此 store 决定 commodity 路由是否可访问
 * - 后端进程重启后,前端需要 reload 才会重新拉(简化 V1)
 */
import { defineStore } from 'pinia'
import { configApi, type FeatureFlags } from '@/api/config'

const DEFAULT_FLAGS: FeatureFlags = {
  commodity_enabled: false,
  commodity_data: false,
  commodity_analysis: false,
  commodity_paper: false,
}

interface FeatureState {
  flags: FeatureFlags
  loaded: boolean
  loading: boolean
  error: string | null
}

export const useFeatureStore = defineStore('feature', {
  state: (): FeatureState => ({
    flags: { ...DEFAULT_FLAGS },
    loaded: false,
    loading: false,
    error: null,
  }),

  getters: {
    commodityEnabled: (s) => !!s.flags.commodity_enabled,
    commodityData: (s) => !!s.flags.commodity_data,
    commodityAnalysis: (s) => !!s.flags.commodity_analysis,
    commodityPaper: (s) => !!s.flags.commodity_paper,
  },

  actions: {
    async load(force = false) {
      if (this.loaded && !force) return
      this.loading = true
      this.error = null
      try {
        const flags = await configApi.getFeatureFlags()
        this.flags = { ...DEFAULT_FLAGS, ...flags }
        this.loaded = true
      } catch (e) {
        this.error = String(e)
        // 即使失败也保持默认 false,菜单隐藏,绝不误开
      } finally {
        this.loading = false
      }
    },

    /** 用户从设置页手动刷新 */
    async reload() {
      await this.load(true)
    },

    /** 全部重置(登出时用) */
    reset() {
      this.flags = { ...DEFAULT_FLAGS }
      this.loaded = false
    },
  },
})
