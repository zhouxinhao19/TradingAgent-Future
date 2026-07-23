/**
 * 自选品种 API（统一支持商品期货+历史兼容）
 */
import { ApiClient } from './request'

export interface FavoriteItem {
  id: string
  user_id: string
  asset_type: 'stock' | 'commodity'
  // 历史兼容（旧股票数据）
  stock_code?: string
  stock_name?: string
  market?: string
  // 商品
  full_symbol?: string
  commodity_name?: string
  exchange?: string
  category?: string
  // 展示
  display_name: string
  // 价格（可选，前端富化后填入）
  current_price?: number
  change_percent?: number
  change?: number
  // 通用
  added_at: string
  tags: string[]
  notes: string
  alert_price_high?: number
  alert_price_low?: number
  snapshot_price?: number
  snapshot_change?: number
  snapshot_pct?: number
}

export interface AddFavoriteParams {
  asset_type: 'stock' | 'commodity'
  stock_code?: string
  stock_name?: string
  market?: string
  full_symbol?: string
  commodity_name?: string
  exchange?: string
  category?: string
  display_name?: string
  tags?: string[]
  notes?: string
  alert_price_high?: number
  alert_price_low?: number
  snapshot_price?: number
}

export const favoritesApi = {
  /** 获取自选列表，可选 ?asset_type=stock|commodity 过滤 */
  list: (assetType?: string) => {
    const params = assetType ? { asset_type: assetType } : undefined
    return ApiClient.get<FavoriteItem[]>('/api/favorites', params)
  },

  /** 添加自选品种 */
  add: (params: AddFavoriteParams) =>
    ApiClient.post<FavoriteItem>('/api/favorites', params),

  /** 删除自选品种 */
  remove: (id: string) =>
    ApiClient.delete<null>(`/api/favorites/${id}`),

  /** 更新自选品种（标签/备注/价格提醒） */
  update: (id: string, params: {
    tags?: string[]
    notes?: string
    alert_price_high?: number
    alert_price_low?: number
    display_name?: string
  }) =>
    ApiClient.put<FavoriteItem>(`/api/favorites/${id}`, params),

  /** 批量删除 */
  batchRemove: (ids: string[]) =>
    ApiClient.post<{ deleted: number }>('/api/favorites/batch-remove', { ids }),
}
