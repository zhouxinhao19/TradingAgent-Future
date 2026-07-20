/**
 * 大宗商品 Pinia Store(Phase 3a)
 *
 * 设计原则:
 * - 单一 store,Detail.vue 多次异步加载天然共享 state
 * - load*() 是幂等 action,可重复调用覆盖;失败回滚旧值,只在 console.error 打印
 * - 不在 store 内做组件级缓存/去重,留给 Vue Router 缓存(Detail.vue <keep-alive>)
 *
 * 数据访问约定(重要):
 * - 后端 ok(data=..., message=...) 返回 {success, data: actualData, message}
 * - Axios 响应拦截器返回 response.data = {success, data: actualData, message}
 * - 所以 ApiClient.get() 的返回值结构为 {success, data: actualData, message}
 * - Store 中通过 (r as any)?.data 获取 actualData(不再使用 .data.data 双重访问)
 */
import { defineStore } from 'pinia'
import commodityApi, {
  type CategoryItem, type ExchangeItem, type VarietyItem,
  type CommodityInfo, type CommodityQuote, type HistoricalResponse,
  type NewsItem, type NewsCategory,
  type BasisResponse, type RowsResponse, type InventoryResponse,
} from '@/api/commodity'

export interface CommodityState {
  // 字典(全站静态)
  categories: CategoryItem[]
  exchanges: ExchangeItem[]
  varieties: VarietyItem[]
  // 当前标的详情缓存
  currentSymbol: string
  info: CommodityInfo | null
  quotes: CommodityQuote | null
  historical: HistoricalResponse | null
  // 扩展数据
  inventory: InventoryResponse | null
  basis: BasisResponse | null
  spotPrice: BasisResponse | null
  holdingPosition: RowsResponse | null
  // 新闻
  newsCategories: NewsCategory[]
  news: NewsItem[]
  // 加载位
  loadingFlags: Record<string, boolean>
  errors: Record<string, string>
}

const initialLoading: Record<string, boolean> = {}
const initialErrors: Record<string, string> = {}

export const useCommodityStore = defineStore('commodity', {
  state: (): CommodityState => ({
    categories: [],
    exchanges: [],
    varieties: [],
    currentSymbol: '',
    info: null,
    quotes: null,
    historical: null,
    inventory: null,
    basis: null,
    spotPrice: null,
    holdingPosition: null,
    newsCategories: [],
    news: [],
    loadingFlags: { ...initialLoading },
    errors: { ...initialErrors },
  }),

  getters: {
    // 简化 loading 判断(组件 :loading="loading('xxx')" 风格)
    loading: (state) => (key: string) => !!state.loadingFlags[key],
    errorMsg: (state) => (key: string) => state.errors[key] || '',
    // 字典快捷索引
    varietyBySymbol: (state) => (sym: string) =>
      state.varieties.find((v) => v.symbol === sym) || null,
  },

  actions: {
    // ---------- 内部 ----------
    _setLoading(key: string, val: boolean) {
      this.loadingFlags[key] = val
      if (val) delete this.errors[key]
    },
    _setError(key: string, msg: string) {
      this.errors[key] = msg
      this.loadingFlags[key] = false
    },

    // ---------- 字典(全站一次加载,缓存到本地存储) ----------
    async loadDictionaries(force = false) {
      if (!force && this.categories.length && this.exchanges.length) return
      this._setLoading('dict', true)
      try {
        const [cats, exchs] = await Promise.all([
          commodityApi.getCategories(),
          commodityApi.getExchanges(),
        ])
        // 后端 ok() 直接返回 {success, data: [...], message}, ApiClient 返回 response.data
        // 所以 cats/exchs 结构为 {success, data: actualArray, message}
        this.categories = (cats as any)?.data ?? []
        this.exchanges = (exchs as any)?.data ?? []
      } catch (e) {
        this._setError('dict', String(e))
        console.error('[commodity] loadDictionaries failed', e)
      } finally {
        this.loadingFlags.dict = false
      }
    },

    async loadVarieties(params?: { exchange?: string; category?: string }, _force = false) {
      this._setLoading('varieties', true)
      try {
        const r = await commodityApi.getVarieties(params)
        // /api/commodity/varieties 返回 {success, data: {items, count}, message}
        if ((r as any)?.data?.items) {
          this.varieties = (r as any).data.items
        }
      } catch (e) {
        this._setError('varieties', String(e))
        console.error('[commodity] loadVarieties failed', e)
      } finally {
        this.loadingFlags.varieties = false
      }
    },

    // ---------- 单标详情(Detail.vue 入口) ----------
    async loadSymbolDetail(fullSymbol: string, historicalDays = 180) {
      this.currentSymbol = fullSymbol
      // 基础信息 + 实时行情 + 历史 K 并行
      const startDate = new Date()
      startDate.setDate(startDate.getDate() - historicalDays)
      const startStr = startDate.toISOString().slice(0, 10)

      const tasks = [
        this.loadInfo(fullSymbol),
        this.loadQuotes(fullSymbol),
        this.loadHistorical(fullSymbol, startStr),
      ]
      await Promise.all(tasks)
    },

    async loadInfo(fullSymbol: string) {
      const key = `info:${fullSymbol}`
      this._setLoading(key, true)
      try {
        const r = await commodityApi.getInfo(fullSymbol)
        // /api/commodity/{symbol}/info 返回 {success, data: CommodityInfo, message}
        this.info = (r as any)?.data ?? null
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    async loadQuotes(fullSymbol: string) {
      const key = `quotes:${fullSymbol}`
      this._setLoading(key, true)
      try {
        const r = await commodityApi.getQuotes(fullSymbol)
        // /api/commodity/{symbol}/quotes 返回 {success, data: CommodityQuote, message}
        this.quotes = (r as any)?.data ?? null
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    async loadHistorical(fullSymbol: string, startDate: string, endDate?: string) {
      const key = `historical:${fullSymbol}`
      this._setLoading(key, true)
      try {
        const r = await commodityApi.getHistorical(fullSymbol, startDate, endDate)
        // /api/commodity/{symbol}/historical 返回 {success, data: HistoricalResponse, message}
        this.historical = (r as any)?.data ?? null
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    // ---------- 库存 ----------
    async loadInventory(fullSymbol: string) {
      const key = `inventory:${fullSymbol}`
      this._setLoading(key, true)
      try {
        const r = await commodityApi.getInventory(fullSymbol)
        // /api/commodity/{symbol}/inventory 返回 {success, data: InventoryResponse, message}
        this.inventory = (r as any)?.data ?? null
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    // ---------- 基差(用 spot-price 全市场汇总,前端按品种过滤展示) ----------
    async loadBasis(daysBack = 30) {
      this._setLoading('basis', true)
      try {
        const endDate = new Date().toISOString().slice(0, 10)
        const startDate = new Date()
        startDate.setDate(startDate.getDate() - daysBack)
        // AKShare futures_spot_price_daily 需要 vars_list;详情页可调 getBasisHistory
        const r = await commodityApi.getSpotPrice(endDate)
        // /api/commodity/spot-price 返回 {success, data: BasisResponse, message}
        this.spotPrice = (r as any)?.data ?? null
        this.basis = (r as any)?.data ?? null
      } catch (e) {
        this._setError('basis', String(e))
      } finally {
        this.loadingFlags.basis = false
      }
    },

    async loadBasisForVars(vars: string[], startDay: string, endDay: string) {
      const key = `basis:${vars.join(',')}:${startDay}:${endDay}`
      this._setLoading(key, true)
      try {
        const r = await commodityApi.getBasisHistory(vars, startDay, endDay)
        // /api/commodity/basis 返回 {success, data: BasisResponse, message}
        this.basis = (r as any)?.data ?? null
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    // ---------- 持仓 ----------
    async loadHoldingPosition(fullSymbol: string, indicator = '成交量') {
      const key = `holding:${fullSymbol}:${indicator}`
      this._setLoading(key, true)
      try {
        const r = await commodityApi.getHoldingPosition(fullSymbol, indicator)
        // /api/commodity/{symbol}/holding-position 返回 {success, data: RowsResponse, message}
        this.holdingPosition = (r as any)?.data ?? null
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    /**
     * 并行拉取成交/多单/空单 三个指标，按 会员简称 合并为一张表
     * - 总成交量/总多单/总空单（合计统计）
     * - 每会员:成交、多单、空单、净持仓(多-空)、多空比
     */
    async loadHoldingPositionAll(fullSymbol: string) {
      const key = `holding:${fullSymbol}:all`
      this._setLoading(key, true)
      try {
        const indicators = ['成交量', '多单持仓', '空单持仓'] as const
        const responses = await Promise.all(
          indicators.map((ind) => commodityApi.getHoldingPosition(fullSymbol, ind)),
        )

        // 三个指标的 raw rows 收集
        const rawRows: Record<typeof indicators[number], any[]> = {
          成交量: [],
          多单持仓: [],
          空单持仓: [],
        }
        responses.forEach((r, i) => {
          rawRows[indicators[i]] = ((r as any)?.data?.rows ?? []) as any[]
        })

        // 按 会员简称 合并(去全角/半角空格,避免 Sora 看不见的字符差导致重复)
        const normName = (s: any) => String(s ?? '').replace(/[\s　]+/g, '').trim()
        const memberMap = new Map<string, Record<string, any>>()
        indicators.forEach((ind) => {
          rawRows[ind].forEach((row) => {
            const name = normName(row['会员简称'])
            if (!name) return
            if (!memberMap.has(name)) {
              memberMap.set(name, {
                会员简称: String(row['会员简称']).trim(),
                成交量: null,
                多单持仓: null,
                空单持仓: null,
              } as Record<string, any>)
            }
            (memberMap.get(name) as Record<string, any>)[ind] = row[ind]
          })
        })

        // 计算派生字段 + 合计
        let totalVol = 0, totalLong = 0, totalShort = 0
        const rows = Array.from(memberMap.values()).map((m) => {
          const vol = Number(m['成交量'] || 0)
          const long_ = Number(m['多单持仓'] || 0)
          const short_ = Number(m['空单持仓'] || 0)
          const net = long_ - short_
          totalVol += vol
          totalLong += long_
          totalShort += short_
          return {
            ...m,
            净持仓: net,
            多空比: short_ > 0 ? +(long_ / short_).toFixed(2) : null,
          }
        })

        // 默认按 成交量 降序
        rows.sort((a, b) => Number((b as any)['成交量'] || 0) - Number((a as any)['成交量'] || 0))

        this.holdingPosition = {
          symbol: fullSymbol,
          rows,
          count: rows.length,
          totals: {
            成交量: totalVol,
            多单持仓: totalLong,
            空单持仓: totalShort,
            净持仓: totalLong - totalShort,
          },
        }
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    // ---------- 新闻 ----------
    async loadNewsCategories(force = false) {
      if (!force && this.newsCategories.length) return
      this._setLoading('newsCategories', true)
      try {
        const r = await commodityApi.getNewsCategories()
        // /api/commodity/news/categories 返回 {success, data: {items, count}, message}
        this.newsCategories = (r as any)?.data?.items ?? []
      } catch (e) {
        this._setError('newsCategories', String(e))
      } finally {
        this.loadingFlags.newsCategories = false
      }
    },

    async loadNews(category = 'all', limit = 30, variety?: string) {
      const key = `news:${category}:${limit}${variety ? `:${variety}` : ''}`
      this._setLoading(key, true)
      try {
        const r = await commodityApi.getNews(category, limit, variety)
        // /api/commodity/news 返回 {success, data: {items, count, category, limit}, message}
        const items = ((r as any)?.data?.items ?? []) as any[]
        // 按 published_at 降序排列(最新的在前)
        items.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''))
        this.news = items
      } catch (e) {
        this._setError(key, String(e))
      } finally {
        this.loadingFlags[key] = false
      }
    },

    // ---------- 清理 ----------
    clearSymbolData() {
      this.currentSymbol = ''
      this.info = null
      this.quotes = null
      this.historical = null
      this.inventory = null
      this.basis = null
      this.spotPrice = null
      this.holdingPosition = null
    },
  },
})
