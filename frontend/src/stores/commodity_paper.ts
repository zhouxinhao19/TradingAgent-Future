/**
 * 大宗商品模拟交易 Pinia Store (Phase 4 第四刀)
 *
 * 管理期货模拟交易的全状态:账户/持仓/订单/成交/快照
 * 遵循 commodity.ts store 的设计模式:
 * - 单一 store,组件间共享 state
 * - 幂等 action,失败回滚旧值
 * - loadingFlags / errors 统一管理
 */
import { defineStore } from 'pinia'
import { commodityPaperApi, type PaperAccountItem, type PaperPositionItem, type PaperOrderItem, type PaperFillItem } from '@/api/commodity'

export interface CommodityPaperState {
  // 账户列表(当前用户)
  accounts: PaperAccountItem[]
  activeAccountId: string
  // 当前账户快照
  account: PaperAccountItem | null
  positions: PaperPositionItem[]
  recentOrders: PaperOrderItem[]
  // 订单
  orders: PaperOrderItem[]
  ordersTotal: number
  // 成交
  fills: PaperFillItem[]
  fillsTotal: number
  // 加载位
  loadingFlags: Record<string, boolean>
  errors: Record<string, string>
}

export const useCommodityPaperStore = defineStore('commodityPaper', {
  state: (): CommodityPaperState => ({
    accounts: [],
    activeAccountId: '',
    account: null,
    positions: [],
    recentOrders: [],
    orders: [],
    ordersTotal: 0,
    fills: [],
    fillsTotal: 0,
    loadingFlags: {},
    errors: {},
  }),

  getters: {
    loading: (state) => (key: string) => !!state.loadingFlags[key],
    errorMsg: (state) => (key: string) => state.errors[key] || '',
    activeAccount: (state) => state.accounts.find(a => a.account_id === state.activeAccountId) || null,
    hasAccounts: (state) => state.accounts.length > 0,
  },

  actions: {
    _setLoading(key: string, val: boolean) {
      this.loadingFlags[key] = val
      if (val) delete this.errors[key]
    },
    _setError(key: string, msg: string) {
      this.errors[key] = msg
      this.loadingFlags[key] = false
    },

    // ---- 账户 ----

    async loadAccounts() {
      this._setLoading('accounts', true)
      try {
        const r = await commodityPaperApi.listAccounts()
        this.accounts = (r as any)?.data?.accounts ?? []
        if (this.accounts.length > 0 && !this.activeAccountId) {
          this.activeAccountId = this.accounts[0].account_id
        }
      } catch (e) {
        this._setError('accounts', String(e))
      } finally {
        this.loadingFlags.accounts = false
      }
    },

    async createAccount(name = '默认账户', initialCapital?: number): Promise<boolean> {
      this._setLoading('createAccount', true)
      try {
        const r = await commodityPaperApi.createAccount(name, initialCapital)
        if ((r as any)?.data) {
          await this.loadAccounts()
          return true
        }
        return false
      } catch (e) {
        this._setError('createAccount', String(e))
        return false
      } finally {
        this.loadingFlags.createAccount = false
      }
    },

    async loadSnapshot(accountId?: string) {
      const aid = accountId || this.activeAccountId
      if (!aid) return
      this._setLoading('snapshot', true)
      this.activeAccountId = aid
      try {
        const r = await commodityPaperApi.getAccountSnapshot(aid)
        const data = (r as any)?.data
        if (data) {
          this.account = {
            account_id: data.account_id,
            user_id: data.user_id,
            name: data.name,
            initial_capital: data.initial_capital,
            balance: data.balance,
            available: data.available,
            margin_used: data.margin_used,
            frozen: data.frozen,
            equity: data.equity,
            realized_pnl: data.realized_pnl,
            unrealized_pnl: data.unrealized_pnl,
            risk_ratio: data.risk_ratio,
            status: data.status,
            updated_at: data.updated_at,
          }
          this.positions = data.positions ?? []
          this.recentOrders = data.recent_orders ?? []
        }
      } catch (e) {
        this._setError('snapshot', String(e))
      } finally {
        this.loadingFlags.snapshot = false
      }
    },

    async resetAccount(accountId?: string) {
      const aid = accountId || this.activeAccountId
      if (!aid) return
      this._setLoading('reset', true)
      try {
        await commodityPaperApi.resetAccount(aid)
        await this.loadSnapshot(aid)
      } catch (e) {
        this._setError('reset', String(e))
      } finally {
        this.loadingFlags.reset = false
      }
    },

    // ---- 订单 ----

    async loadOrders(params?: { status?: string; full_symbol?: string; limit?: number; skip?: number }) {
      const aid = params?.full_symbol ? this.activeAccountId : this.activeAccountId
      if (!aid) return
      this._setLoading('orders', true)
      try {
        const r = await commodityPaperApi.listOrders(aid, params)
        const data = (r as any)?.data
        if (data) {
          this.orders = data.orders ?? []
          this.ordersTotal = data.total ?? 0
        }
      } catch (e) {
        this._setError('orders', String(e))
      } finally {
        this.loadingFlags.orders = false
      }
    },

    async submitOrder(params: {
      full_symbol: string
      direction: 'long' | 'short'
      offset?: string
      order_type?: string
      lots: number
      price?: number
      stop_loss?: number
      take_profit?: number
    }): Promise<any> {
      const aid = this.activeAccountId
      if (!aid) return { status: 'rejected', reject_reason: 'no_active_account' }
      this._setLoading('submitOrder', true)
      try {
        const r = await commodityPaperApi.submitOrder({ account_id: aid, ...params })
        const data = (r as any)?.data
        // 刷新订单列表和快照
        if (data?.status === 'accepted') {
          await Promise.all([
            this.loadSnapshot(),
            this.loadOrders({ limit: 5 }),
          ])
        }
        return data ?? { status: 'error' }
      } catch (e) {
        this._setError('submitOrder', String(e))
        return { status: 'rejected', reject_reason: String(e) }
      } finally {
        this.loadingFlags.submitOrder = false
      }
    },

    async cancelOrder(orderId: string) {
      this._setLoading('cancelOrder', true)
      try {
        await commodityPaperApi.cancelOrder(orderId)
        await this.loadOrders({ limit: 5 })
      } catch (e) {
        this._setError('cancelOrder', String(e))
      } finally {
        this.loadingFlags.cancelOrder = false
      }
    },

    // ---- 成交 ----

    async loadFills(params?: { full_symbol?: string; limit?: number; skip?: number }) {
      const aid = this.activeAccountId
      if (!aid) return
      this._setLoading('fills', true)
      try {
        const r = await commodityPaperApi.listFills(aid, params)
        const data = (r as any)?.data
        if (data) {
          this.fills = data.fills ?? []
          this.fillsTotal = data.total ?? 0
        }
      } catch (e) {
        this._setError('fills', String(e))
      } finally {
        this.loadingFlags.fills = false
      }
    },

    // ---- 全量刷新 ----

    async refreshAll() {
      await Promise.all([
        this.loadSnapshot(),
        this.loadOrders({ limit: 10 }),
        this.loadFills({ limit: 10 }),
      ])
    },

    // ---- 清理 ----

    clearAll() {
      this.accounts = []
      this.activeAccountId = ''
      this.account = null
      this.positions = []
      this.recentOrders = []
      this.orders = []
      this.ordersTotal = 0
      this.fills = []
      this.fillsTotal = 0
    },
  },
})
