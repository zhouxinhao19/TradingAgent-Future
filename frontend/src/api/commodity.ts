/**
 * 大宗商品 API 模块(Phase 3a)
 *
 * 22 端点(Phase 1:5 / Phase 3a:17),统一 ApiClient 出口
 * 类型定义贯穿全组件,供 views/Commodity + stores/commodity 复用
 */
import { ApiClient } from './request'

// ============================================================
// 通用响应包装 (与后端 ok() 格式一致)
// ============================================================
export interface ApiEnvelope<T = unknown> {
  success: boolean
  message?: string
  data?: T
}

// ============================================================
// 品类 / 交易所 / 品种字典
// ============================================================

export interface CategoryItem {
  code: string
  name: string
}

export interface ExchangeItem {
  code: string
  name: string
  abbrev?: string
}

export interface VarietyItem {
  variety_code?: string
  symbol: string
  name_cn: string
  abbreviation_akshare?: string
  category: string
  unit?: string
  contract_size?: number
  tick_size?: number | string
  list_date?: string
  exchange: string
}

export interface ListResponse<T> {
  items: T[]
  count: number
}

// ============================================================
// 基础信息 / 实时行情 / 历史 K 线
// ============================================================

export interface CommodityInfo {
  full_symbol: string
  code: string
  name: string
  exchange: string
  exchange_name?: string
  category: string
  underlying?: string
  currency?: string
  unit: string
  contract_size: number
  is_china_futures?: boolean
  is_international?: boolean
  is_spot_cn?: boolean
  data_source?: string
  data_version?: number
  updated_at?: string
}

export interface CommodityQuote {
  full_symbol: string
  code: string
  exchange: string
  name: string
  category: string
  currency?: string
  unit: string
  contract_size: number
  open: number
  high: number
  low: number
  close: number
  pre_close: number
  current_price: number
  settlement_price: number
  change: number
  pct_chg: number
  volume: number
  open_interest: number
  trade_date: string
  data_source?: string
  updated_at?: string
}

export interface KlineBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  open_interest: number
  settlement: number
}

export interface HistoricalResponse {
  full_symbol: string
  rows: KlineBar[]
  count: number
  start_date: string
  end_date: string
}

// ============================================================
// 13 扩展接口响应
// ============================================================

export interface RowsResponse<T = Record<string, unknown>> {
  rows?: T[]
  count: number
  // 仓单/持仓排名可能按品种分组
  by_variety?: Record<string, T[]>
}

export interface InventoryResponse extends RowsResponse {
  symbol: string
}

export interface BasisResponse extends RowsResponse {
  vars_list?: string[]
  start_day?: string
  end_day?: string
  date?: string
}

export interface RollYieldResponse extends RowsResponse {
  type_method: string
  var?: string
}

export interface ContractInfoResponse extends RowsResponse {
  exchange: string
  date: string
}

export interface TradingCalendarResponse extends RowsResponse {
  date: string
}

export interface RealtimeQuoteResponse extends RowsResponse {
  symbols: string
  market: string
}

export interface MinuteKlineResponse extends RowsResponse {
  symbol: string
  period: number
}

export interface DeliveryInfoResponse extends RowsResponse {
  exchange: string
  date: string
}

export interface HoldingPositionResponse extends RowsResponse {
  symbol: string
  indicator: string
  date: string
}

export interface WarehouseReceiptResponse extends RowsResponse {
  exchange: string
  date: string
}

// ============================================================
// 新闻
// ============================================================

export interface NewsCategory {
  code: string
  name: string
}

export interface NewsItem {
  published_at: string
  title: string
  content?: string
  category: string
  metal?: string
  sentiment: 'positive' | 'negative' | 'neutral'
  sentiment_score: number
  source: string
  url?: string
}

export interface NewsResponse {
  items: NewsItem[]
  count: number
  category: string
  limit: number
}


// ============================================================
// API 方法
// ============================================================

export const commodityApi = {
  // ---- Phase 1:基础 5 端点 ----
  async getCategories() {
    return ApiClient.get<ApiEnvelope<CategoryItem[]>>(`/api/commodity/categories`)
  },

  async getExchanges() {
    return ApiClient.get<ApiEnvelope<ExchangeItem[]>>(`/api/commodity/exchanges`)
  },

  async getInfo(fullSymbol: string) {
    return ApiClient.get<ApiEnvelope<CommodityInfo>>(`/api/commodity/${encodeURIComponent(fullSymbol)}/info`)
  },

  async getQuotes(fullSymbol: string) {
    return ApiClient.get<ApiEnvelope<CommodityQuote>>(`/api/commodity/${encodeURIComponent(fullSymbol)}/quotes`)
  },

  async getHistorical(fullSymbol: string, startDate: string, endDate?: string) {
    return ApiClient.get<ApiEnvelope<HistoricalResponse>>(
      `/api/commodity/${encodeURIComponent(fullSymbol)}/historical`,
      { start_date: startDate, end_date: endDate },
    )
  },

  // ---- Phase 3a:品种字典(15 端点之一) ----
  async getVarieties(params?: { exchange?: string; category?: string }) {
    return ApiClient.get<ApiEnvelope<ListResponse<VarietyItem>>>(`/api/commodity/varieties`, params)
  },

  // ---- 14 扩展数据端点 ----
  async getFees(fullSymbol: string, date?: string) {
    return ApiClient.get<ApiEnvelope<{ items: Record<string, unknown>[]; count: number; exchange: string | null }>>(
      `/api/commodity/${encodeURIComponent(fullSymbol)}/fees`,
      date ? { date } : undefined,
    )
  },

  async getInventory(fullSymbol: string, params?: { start_date?: string; end_date?: string }) {
    return ApiClient.get<ApiEnvelope<InventoryResponse>>(
      `/api/commodity/${encodeURIComponent(fullSymbol)}/inventory`,
      params,
    )
  },

  async getWarehouseReceipt(exchange: string, date?: string) {
    return ApiClient.get<ApiEnvelope<WarehouseReceiptResponse>>(
      `/api/commodity/${exchange}/warehouse-receipt`,
      date ? { date } : undefined,
    )
  },

  async getPositionRank(exchange: string, date?: string, varsList?: string[]) {
    return ApiClient.get<ApiEnvelope<RowsResponse>>(
      `/api/commodity/${exchange}/position-rank`,
      { date, vars_list: varsList?.join(',') },
    )
  },

  async getSpotPrice(date?: string) {
    return ApiClient.get<ApiEnvelope<BasisResponse>>(`/api/commodity/spot-price`, date ? { date } : undefined)
  },

  async getBasisHistory(varsList: string[], startDay: string, endDay: string) {
    return ApiClient.get<ApiEnvelope<BasisResponse>>(
      `/api/commodity/basis`,
      { vars_list: varsList.join(','), start_day: startDay, end_day: endDay },
    )
  },

  async getBasisSpotPrevious(date?: string) {
    return ApiClient.get<ApiEnvelope<BasisResponse>>(
      `/api/commodity/basis-spot-previous`,
      date ? { date } : undefined,
    )
  },

  async getRollYield(typeMethod: 'date' | 'symbol' | 'var', params?: {
    var?: string; date?: string; start_day?: string; end_day?: string;
  }) {
    return ApiClient.get<ApiEnvelope<RollYieldResponse>>(`/api/commodity/roll-yield`, {
      type_method: typeMethod,
      ...params,
    })
  },

  async getContractInfo(exchange: string, date?: string) {
    return ApiClient.get<ApiEnvelope<ContractInfoResponse>>(
      `/api/commodity/${exchange}/contract-info`,
      date ? { date } : undefined,
    )
  },

  async getContractsList(fullSymbol: string) {
    return ApiClient.get<ApiEnvelope<{
      underlying: string
      chinese_name: string
      exchange: string
      continuous: string | null
      current: string
      contracts: string[]
      count: number
    }>>(`/api/commodity/${encodeURIComponent(fullSymbol)}/contracts-list`)
  },

  async getTradingCalendar(date?: string) {
    return ApiClient.get<ApiEnvelope<TradingCalendarResponse>>(
      `/api/commodity/trading-calendar`,
      date ? { date } : undefined,
    )
  },

  async getRealtimeQuote(symbols: string | string[], market: 'CF' | 'FF' = 'CF') {
    const sym = Array.isArray(symbols) ? symbols.join(',') : symbols
    return ApiClient.get<ApiEnvelope<RealtimeQuoteResponse>>(`/api/commodity/realtime-quote`, { symbols: sym, market })
  },

  async getMinuteKline(fullSymbol: string, period: 1 | 5 | 15 | 30 | 60 = 5) {
    return ApiClient.get<ApiEnvelope<MinuteKlineResponse>>(
      `/api/commodity/${encodeURIComponent(fullSymbol)}/minute-kline`,
      { period },
    )
  },

  async getDeliveryInfo(exchange: string, date: string) {
    return ApiClient.get<ApiEnvelope<DeliveryInfoResponse>>(`/api/commodity/${exchange}/delivery-info`, { date })
  },

  async getHoldingPosition(fullSymbol: string, indicator: string = '成交量', date?: string) {
    return ApiClient.get<ApiEnvelope<HoldingPositionResponse>>(
      `/api/commodity/${encodeURIComponent(fullSymbol)}/holding-position`,
      { indicator, date },
    )
  },

  // ---- 2 新闻端点 ----
  async getNewsCategories() {
    return ApiClient.get<ApiEnvelope<ListResponse<NewsCategory>>>(`/api/commodity/news/categories`)
  },

  async getNews(category: string = 'all', limit: number = 50) {
    return ApiClient.get<ApiEnvelope<NewsResponse>>(`/api/commodity/news`, { category, limit })
  },

  // ---- Phase 3b-ii-D:分析端点 ----
  async submitAnalysis(fullSymbol: string, params?: {
    trade_date?: string
    variety_name?: string
    exchange?: string
    category?: string
    quote_unit?: string
    max_debate_rounds?: number
    max_risk_discuss_rounds?: number
  }) {
    // 后端 AnalysisRequest 必填 full_symbol(虽然也在 URL 里,但 Pydantic 仍校验 body)
    const body = { full_symbol: fullSymbol, ...(params || {}) }
    return ApiClient.post<ApiEnvelope<{
      task_id: string
      full_symbol: string
      trade_date: string
      status: string
    }>>(`/api/commodity/${encodeURIComponent(fullSymbol)}/analyze`, body)
  },

  async getReports(fullSymbol: string, limit: number = 20) {
    return ApiClient.get<ApiEnvelope<{
      full_symbol: string
      total: number
      reports: Array<{
        report_id: string
        full_symbol: string
        trade_date: string
        direction: string
        confidence: number
        created_at: string
      }>
    }>>(`/api/commodity/${encodeURIComponent(fullSymbol)}/reports`, { limit })
  },

  async getReportDetail(reportId: string) {
    return ApiClient.get<ApiEnvelope<Record<string, unknown>>>(`/api/commodity/reports/${reportId}`)
  },

  /** 全局最近商品分析报告(所有品种混合) */
  async getRecentReports(limit: number = 10) {
    return ApiClient.get<ApiEnvelope<{
      total: number
      reports: Array<RecentReportItem>
    }>>(`/api/commodity/reports/recent`, { limit })
  },

  /**
   * 任务中心 — 商品分析任务列表 (Phase 5+)
   * @param params.status 可选过滤 processing/completed/failed
   */
  async getTaskList(params?: {
    status?: TaskStatus
    limit?: number
    offset?: number
  }) {
    return ApiClient.get<ApiEnvelope<{
      total: number
      tasks: Array<CommodityTaskItem>
    }>>(`/api/commodity/tasks`, params)
  },

  /** 查询单个任务状态 */
  async getTaskStatus(taskId: string) {
    return ApiClient.get<ApiEnvelope<CommodityTaskItem>>(
      `/api/commodity/tasks/${encodeURIComponent(taskId)}`,
    )
  },

  /** 删除任务及关联报告 */
  async deleteTask(taskId: string) {
    return ApiClient.delete<ApiEnvelope<null>>(
      `/api/commodity/tasks/${encodeURIComponent(taskId)}`,
    )
  },

  /** 标记任务为失败（仅限 stuck processing 任务） */
  async markTaskAsFailed(taskId: string) {
    return ApiClient.post<ApiEnvelope<null>>(
      `/api/commodity/tasks/${encodeURIComponent(taskId)}/mark-failed`,
    )
  },

  /** 获取已完成任务的完整分析结果 */
  async getTaskResult(taskId: string) {
    return ApiClient.get<ApiEnvelope<Record<string, unknown>>>(
      `/api/commodity/tasks/${encodeURIComponent(taskId)}/result`,
    )
  },
}

/**
 * 最近报告摘要类型 — 供全局列表复用
 */
export interface RecentReportItem {
  report_id: string
  full_symbol: string
  trade_date: string
  direction: string
  confidence: number
  created_at: string
}

/**
 * 商品分析任务状态 (Phase 5+: task center)
 */
export type TaskStatus = 'processing' | 'completed' | 'failed'

export interface CommodityTaskItem {
  task_id: string
  full_symbol: string
  trade_date: string
  variety_name?: string
  exchange?: string
  status: TaskStatus
  progress?: number
  progress_message?: string
  created_at: string
  completed_at?: string
  report_id?: string
  error_message?: string
}

// ============================================================
// 模拟交易 API (Phase 4)
// ============================================================

export interface PaperAccountItem {
  account_id: string
  user_id: string
  name: string
  initial_capital: number
  balance: number
  available: number
  margin_used: number
  frozen: number
  equity: number
  realized_pnl: number
  unrealized_pnl: number
  risk_ratio: number
  status: string
  updated_at?: string
}

export interface PaperPositionItem {
  id: string
  account_id: string
  full_symbol: string
  direction: 'long' | 'short'
  lots: number
  avg_cost: number
  current_price: number
  floating_pnl: number
  margin_used: number
  stop_loss?: number | null
  take_profit?: number | null
  opened_at?: string
  updated_at?: string
}

export interface PaperOrderItem {
  id: string
  account_id: string
  full_symbol: string
  direction: 'long' | 'short'
  offset: string
  order_type: 'market' | 'limit' | 'stop' | 'stop_limit'
  lots: number
  price?: number | null
  stop_price?: number | null
  status: string
  filled_lots: number
  filled_avg_price: number
  commission: number
  source: string
  decision_id?: string | null
  created_at?: string
  filled_at?: string
  cancelled_at?: string
}

export interface PaperFillItem {
  id: string
  order_id: string
  account_id: string
  full_symbol: string
  direction: string
  offset: string
  lots: number
  price: number
  commission: number
  slippage: number
  matched_at?: string
}

export const commodityPaperApi = {
  // ---- 账户 ----
  async createAccount(name = '默认账户', initialCapital?: number) {
    const params: Record<string, any> = { name }
    if (initialCapital !== undefined) params.initial_capital = initialCapital
    return ApiClient.post<ApiEnvelope<PaperAccountItem>>(`/api/commodity/paper/accounts`, params)
  },

  async listAccounts() {
    return ApiClient.get<ApiEnvelope<{ accounts: PaperAccountItem[] }>>(`/api/commodity/paper/accounts`)
  },

  async getAccount(accountId: string) {
    return ApiClient.get<ApiEnvelope<PaperAccountItem>>(`/api/commodity/paper/accounts/${accountId}`)
  },

  async getAccountSnapshot(accountId: string) {
    return ApiClient.get<ApiEnvelope<PaperAccountItem & { positions: PaperPositionItem[]; recent_orders: PaperOrderItem[] }>>(
      `/api/commodity/paper/accounts/${accountId}/snapshot`,
    )
  },

  async getAccountMetrics(accountId: string) {
    return ApiClient.get<ApiEnvelope<Record<string, number>>>(`/api/commodity/paper/accounts/${accountId}/metrics`)
  },

  async resetAccount(accountId: string) {
    return ApiClient.post<ApiEnvelope<PaperAccountItem>>(`/api/commodity/paper/accounts/${accountId}/reset`)
  },

  // ---- 订单 ----
  async submitOrder(params: {
    account_id: string
    full_symbol: string
    direction: 'long' | 'short'
    offset?: string
    order_type?: string
    lots: number
    price?: number
    stop_price?: number
    stop_loss?: number
    take_profit?: number
  }) {
    return ApiClient.post<ApiEnvelope<{ status: string; fill?: PaperFillItem; reject_reason?: string }>>(
      `/api/commodity/paper/orders`, params,
    )
  },

  async listOrders(accountId: string, params?: { status?: string; full_symbol?: string; limit?: number; skip?: number }) {
    return ApiClient.get<ApiEnvelope<{ orders: PaperOrderItem[]; total: number }>>(
      `/api/commodity/paper/orders`, { account_id: accountId, ...params },
    )
  },

  async getOrder(orderId: string, accountId: string) {
    return ApiClient.get<ApiEnvelope<PaperOrderItem>>(`/api/commodity/paper/orders/${orderId}`, { account_id: accountId })
  },

  async cancelOrder(orderId: string) {
    return ApiClient.post<ApiEnvelope<{ order_id: string; status: string }>>(`/api/commodity/paper/orders/${orderId}/cancel`)
  },

  // ---- 持仓 ----
  async listPositions(accountId: string, openOnly = true) {
    return ApiClient.get<ApiEnvelope<{ positions: PaperPositionItem[] }>>(
      `/api/commodity/paper/positions`, { account_id: accountId, open_only: openOnly },
    )
  },

  // ---- 成交 ----
  async listFills(accountId: string, params?: { full_symbol?: string; limit?: number; skip?: number }) {
    return ApiClient.get<ApiEnvelope<{ fills: PaperFillItem[]; total: number }>>(
      `/api/commodity/paper/fills`, { account_id: accountId, ...params },
    )
  },

  // ---- 决策下单 ----
  async fromDecision(accountId: string, decisionId: string, lots?: number) {
    return ApiClient.post<ApiEnvelope<{ status: string; lots?: number; reason?: string }>>(
      `/api/commodity/paper/from-decision`,
      { account_id: accountId, decision_id: decisionId, lots },
    )
  },

  // ---- 快照 ----
  async listSnapshots(accountId: string, limit = 30) {
    return ApiClient.get<ApiEnvelope<{ snapshots: Array<{ date: string; equity: number; balance: number }> }>>(
      `/api/commodity/paper/snapshots`, { account_id: accountId, limit },
    )
  },
}

export default commodityApi
