import { ApiClient } from './request'

export interface QuoteResponse {
  code: string
  name?: string
  market?: string
  price?: number
  change_percent?: number
  amount?: number
  prev_close?: number
  turnover_rate?: number
  volume_ratio?: number
  trade_date?: string
  updated_at?: string
}

export interface FundamentalsResponse {
  code: string
  name?: string
  industry?: string
  market?: string
  pe?: number
  pb?: number
  pe_ttm?: number
  pb_mrq?: number
  roe?: number
  total_mv?: number
  circ_mv?: number
  turnover_rate?: number
  volume_ratio?: number
  updated_at?: string
}

export interface KlineBar {
  time: string
  open?: number
  high?: number
  low?: number
  close?: number
  volume?: number
  amount?: number
}

export interface KlineResponse {
  code: string
  period: 'day'|'week'|'month'|'5m'|'15m'|'30m'|'60m'
  limit: number
  adj: 'none'|'qfq'|'hfq'
  source?: string
  items: KlineBar[]
}

export interface NewsItem {
  title: string
  source: string
  time: string
  url: string
  type: 'news' | 'announcement'
}

export interface NewsResponse {
  code: string
  days: number
  limit: number
  include_announcements: boolean
  source?: string
  items: NewsItem[]
}

export const stocksApi = {
  async getQuote(code: string) {
    return ApiClient.get<QuoteResponse>(`/api/stocks/${code}/quote`)
  },
  async getFundamentals(code: string) {
    return ApiClient.get<FundamentalsResponse>(`/api/stocks/${code}/fundamentals`)
  },
  async getKline(code: string, period: KlineResponse['period'] = 'day', limit = 120, adj: KlineResponse['adj'] = 'none') {
    return ApiClient.get<KlineResponse>(`/api/stocks/${code}/kline`, { period, limit, adj })
  },
  async getNews(code: string, days = 2, limit = 50, includeAnnouncements = true) {
    return ApiClient.get<NewsResponse>(`/api/stocks/${code}/news`, { days, limit, include_announcements: includeAnnouncements })
  }
}

