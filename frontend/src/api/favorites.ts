import { ApiClient } from './request'

export interface FavoriteItem {
  stock_code: string
  stock_name: string
  market: string
  added_at?: string
  tags?: string[]
  notes?: string
  alert_price_high?: number | null
  alert_price_low?: number | null
  current_price?: number | null
  change_percent?: number | null
  volume?: number | null
}

export interface AddFavoriteReq {
  stock_code: string
  stock_name: string
  market?: string
  tags?: string[]
  notes?: string
  alert_price_high?: number | null
  alert_price_low?: number | null
}

export const favoritesApi = {
  list: () => ApiClient.get<FavoriteItem[]>('/api/favorites/'),
  add: (payload: AddFavoriteReq) => ApiClient.post<{ message: string; stock_code: string }>('/api/favorites/', payload),
  update: (stock_code: string, payload: Partial<Pick<FavoriteItem, 'tags' | 'notes' | 'alert_price_high' | 'alert_price_low'>>) =>
    ApiClient.put<{ message: string; stock_code: string }>(`/api/favorites/${stock_code}`, payload),
  remove: (stock_code: string) => ApiClient.delete<{ message: string; stock_code: string }>(`/api/favorites/${stock_code}`),
  check: (stock_code: string) => ApiClient.get<{ stock_code: string; is_favorite: boolean }>(`/api/favorites/check/${stock_code}`),
  tags: () => ApiClient.get<string[]>('/api/favorites/tags')
}

