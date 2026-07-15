/**
 * 自选股 API (股票系统,与商品自选互不冲突)
 */

import { ApiClient, type ApiEnvelope } from './request'

export interface FavoriteStock {
  stock_code: string
  stock_name: string
  current_price: number
  change_percent: number
}

export const favoritesApi = {
  async list() {
    return ApiClient.get<ApiEnvelope<FavoriteStock[]>>('/api/favorites')
  },
}
