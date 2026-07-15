/**
 * 市场快讯 API (股票系统)
 */

import { ApiClient, type ApiEnvelope } from './request'

export interface NewsItem {
  id: string
  title: string
  url: string
  time: string
  source: string
}

export const newsApi = {
  async getLatestNews(_type?: string, _limit = 10, _hours = 24) {
    return ApiClient.get<ApiEnvelope<NewsItem[]>>('/api/news/latest', { type: _type, limit: _limit, hours: _hours })
  },
}
