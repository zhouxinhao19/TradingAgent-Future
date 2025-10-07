/**
 * 使用统计 API
 */

import request from './request'

export interface UsageRecord {
  id?: string
  timestamp: string
  provider: string
  model_name: string
  input_tokens: number
  output_tokens: number
  cost: number
  session_id: string
  analysis_type: string
}

export interface UsageStatistics {
  total_requests: number
  total_input_tokens: number
  total_output_tokens: number
  total_cost: number
  by_provider: Record<string, any>
  by_model: Record<string, any>
  by_date: Record<string, any>
}

/**
 * 获取使用记录
 */
export function getUsageRecords(params?: {
  provider?: string
  model_name?: string
  start_date?: string
  end_date?: string
  limit?: number
}) {
  return request({
    url: '/api/usage/records',
    method: 'get',
    params
  })
}

/**
 * 获取使用统计
 */
export function getUsageStatistics(params?: {
  days?: number
  provider?: string
  model_name?: string
}) {
  return request({
    url: '/api/usage/statistics',
    method: 'get',
    params
  })
}

/**
 * 按供应商统计成本
 */
export function getCostByProvider(days: number = 7) {
  return request({
    url: '/api/usage/cost/by-provider',
    method: 'get',
    params: { days }
  })
}

/**
 * 按模型统计成本
 */
export function getCostByModel(days: number = 7) {
  return request({
    url: '/api/usage/cost/by-model',
    method: 'get',
    params: { days }
  })
}

/**
 * 每日成本统计
 */
export function getDailyCost(days: number = 7) {
  return request({
    url: '/api/usage/cost/daily',
    method: 'get',
    params: { days }
  })
}

/**
 * 删除旧记录
 */
export function deleteOldRecords(days: number = 90) {
  return request({
    url: '/api/usage/records/old',
    method: 'delete',
    params: { days }
  })
}

