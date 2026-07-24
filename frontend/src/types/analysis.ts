// 分析状态枚举
export enum AnalysisStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// 批次状态枚举
export enum BatchStatus {
  PENDING = 'pending',
  PROCESSING = 'processing',
  COMPLETED = 'completed',
  PARTIAL_SUCCESS = 'partial_success',
  FAILED = 'failed',
  CANCELLED = 'cancelled'
}

// 分析参数
export interface AnalysisParameters {
  market_type: 'A股' | '美股' | '港股'
  analysis_date?: string
  research_depth: '快速' | '基础' | '标准' | '深度' | '全面'
  selected_analysts: string[]
  custom_prompt?: string
  include_charts: boolean
  language: 'zh-CN' | 'en-US'
}

// 分析结果
export interface AnalysisResult {
  analysis_id: string
  summary?: string
  recommendation?: string
  confidence_score?: number
  risk_level?: string
  key_points: string[]
  detailed_analysis?: Record<string, any>
  charts: string[]
  tokens_used: number
  execution_time: number
  error_message?: string
}

// 分析任务
export interface AnalysisTask {
  id: string
  task_id: string
  batch_id?: string
  user_id: string
  symbol?: string  // 主字段：品种代码
  stock_code?: string  // 兼容字段（已废弃）
  stock_name?: string
  status: AnalysisStatus
  priority: number
  progress: number
  
  // 时间戳
  created_at: string
  started_at?: string
  completed_at?: string
  
  // 执行信息
  worker_id?: string
  parameters: AnalysisParameters
  result?: AnalysisResult
  
  // 重试机制
  retry_count: number
  max_retries: number
  last_error?: string
}

// 分析批次
export interface AnalysisBatch {
  id: string
  batch_id: string
  user_id: string
  title: string
  description?: string
  status: BatchStatus
  
  // 任务统计
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  cancelled_tasks: number
  progress: number
  
  // 时间戳
  created_at: string
  started_at?: string
  completed_at?: string
  
  // 配置参数
  parameters: AnalysisParameters
  
  // 结果摘要
  results_summary?: Record<string, any>
}

// 品种信息（统一字段名）
export interface InstrumentInfo {
  // 基础信息
  symbol: string           // 品种代码（如 CU2608.SHF）
  code?: string            // 简码（如 CU）
  full_symbol?: string     // 完整代码
  name: string             // 品种名称
  market: string           // 市场类型
  industry?: string        // 行业/品类
  area?: string
  board?: string
  exchange?: string        // 交易所

  // 市值信息（亿元）
  total_mv?: number        // 总市值
  circ_mv?: number         // 流通市值

  // 财务指标
  pe?: number
  pb?: number
  pe_ttm?: number
  pb_mrq?: number
  roe?: number

  // 交易数据
  close?: number
  pct_chg?: number
  amount?: number
  turnover_rate?: number
  volume_ratio?: number

  // 技术指标
  ma20?: number
  rsi14?: number
  kdj_k?: number
  kdj_d?: number
  kdj_j?: number
  dif?: number
  dea?: number
  macd_hist?: number
}

// 向后兼容别名（已废弃，请使用 InstrumentInfo）
export type StockInfo = InstrumentInfo

// 单股分析请求
export interface SingleAnalysisRequest {
  symbol?: string  // 主字段：品种代码
  stock_code?: string  // 兼容字段（已废弃）
  parameters?: AnalysisParameters
}

// 批量分析请求
export interface BatchAnalysisRequest {
  title: string
  description?: string
  symbols?: string[]  // 主字段：品种代码列表
  stock_codes?: string[]  // 兼容字段（已废弃）
  parameters?: AnalysisParameters
}

// 分析任务响应
export interface AnalysisTaskResponse {
  task_id: string
  batch_id?: string
  symbol?: string  // 主字段：品种代码
  stock_code?: string  // 兼容字段（已废弃）
  stock_name?: string
  status: AnalysisStatus
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  result?: AnalysisResult
}

// 分析批次响应
export interface AnalysisBatchResponse {
  batch_id: string
  title: string
  description?: string
  status: BatchStatus
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  progress: number
  created_at: string
  started_at?: string
  completed_at?: string
  parameters: AnalysisParameters
}

// 分析历史查询参数
export interface AnalysisHistoryQuery {
  status?: AnalysisStatus
  start_date?: string
  end_date?: string
  symbol?: string  // 主字段：品种代码
  stock_code?: string  // 兼容字段（已废弃）
  batch_id?: string
  page: number
  page_size: number
}

// 分析历史响应
export interface AnalysisHistoryResponse {
  tasks: AnalysisTask[]
  batches: AnalysisBatch[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}

// 任务进度信息
export interface TaskProgress {
  task_id: string
  status: AnalysisStatus
  progress: number
  message?: string
  updated_at: string
}

// 批次进度信息
export interface BatchProgress {
  batch_id: string
  status: BatchStatus
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  progress: number
  updated_at: string
}

// 分析统计信息
export interface AnalysisStats {
  total_analyses: number
  successful_analyses: number
  failed_analyses: number
  success_rate: number
  average_execution_time: number
  total_tokens_used: number
  daily_analyses: number
  monthly_analyses: number
}

// 队列状态信息
export interface QueueStatus {
  pending: number
  processing: number
  completed: number
  failed: number
  queue_size: number
}

// 用户队列状态
export interface UserQueueStatus {
  pending: number
  processing: number
  concurrent_limit: number
  available_slots: number
}

// 分析报告
export interface AnalysisReport {
  id: string
  task_id: string
  batch_id?: string
  title: string
  content: string
  format: 'html' | 'pdf' | 'markdown'
  created_at: string
  download_url?: string
}
