/**
 * 股票分析任务 API (股票系统)
 */

import { ApiClient, type ApiEnvelope } from './request'

export interface AnalysisTaskItem {
  task_id: string
  stock_code: string
  stock_name: string
  status: string
  start_time: string
}

export const analysisApi = {
  async getTaskList(params?: { status?: string; limit?: number }) {
    return ApiClient.get<ApiEnvelope<AnalysisTaskItem[]>>('/api/tasks', params)
  },
}
