import { ApiClient, ApiResponse } from './request'

export interface ScreeningOrderBy { field: string; direction: 'asc' | 'desc' }
export interface ScreeningRunReq {
  market?: 'CN'
  date?: string | null
  adj?: 'qfq' | 'hfq' | 'none'
  conditions: any
  order_by?: ScreeningOrderBy[]
  limit?: number
  offset?: number
}

export interface ScreeningRunItem {
  code: string
  close?: number
  pct_chg?: number
  amount?: number
  ma20?: number
  rsi14?: number
  kdj_k?: number
  kdj_d?: number
  kdj_j?: number
  dif?: number
  dea?: number
  macd_hist?: number
}

export interface ScreeningRunResp { total: number; items: ScreeningRunItem[] }

export const screeningApi = {
  run: (payload: ScreeningRunReq) => ApiClient.post<ScreeningRunResp>('/screening/run', payload),
}

