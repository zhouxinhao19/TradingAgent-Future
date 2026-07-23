/**
 * 模拟交易 API (期货版)
 */

import { ApiClient, type ApiEnvelope } from './request'

export interface PaperAccountSummary {
  account_id: string
  balance: number
  positions: number
  pnl: number
}

export const paperApi = {
  async getAccountSummary() {
    return ApiClient.get<ApiEnvelope<PaperAccountSummary>>('/api/paper/summary')
  },
}
