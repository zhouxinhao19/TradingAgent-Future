<template>
  <div class="dashboard">
    <!-- 欢迎区域 -->
    <div class="welcome-section">
      <div class="welcome-content">
        <h1 class="welcome-title">
          欢迎使用 TradingAgents-CN
          <span class="version-badge">v1.0.1</span>
        </h1>
        <p class="welcome-subtitle">
          现代化的多智能体股票分析学习平台，辅助你掌握更全面的市场视角分析股票
        </p>
      </div>
      <div class="welcome-actions">
        <el-button type="primary" size="large" @click="goToCommodityAnalysis">
          <el-icon><TrendCharts /></el-icon>
          商品分析
        </el-button>
        <el-button size="large" @click="goToCommodityPaper">
          <el-icon><Box /></el-icon>
          期货模拟
        </el-button>
      </div>
    </div>


    <!-- 学习中心推荐卡片 -->
    <el-card class="learning-highlight-card">
      <div class="learning-highlight">
        <div class="learning-icon">
          <el-icon size="48"><Reading /></el-icon>
        </div>
        <div class="learning-content">
          <h2>📚 AI股票分析学习中心</h2>
          <p>从零开始学习AI、大语言模型和智能股票分析。了解多智能体系统如何协作分析股票，掌握提示词工程技巧，选择合适的大模型，理解AI的能力与局限性。</p>
          <div class="learning-features">
            <span class="feature-tag">🤖 AI基础知识</span>
            <span class="feature-tag">✍️ 提示词工程</span>
            <span class="feature-tag">🎯 模型选择</span>
            <span class="feature-tag">📊 分析原理</span>
            <span class="feature-tag">⚠️ 风险认知</span>
            <span class="feature-tag">🎓 实战教程</span>
          </div>
        </div>
        <div class="learning-action">
          <el-button type="primary" size="large" @click="goToLearning">
            <el-icon><Reading /></el-icon>
            开始学习
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 主要功能区域 -->
    <el-row :gutter="24" class="main-content">
      <!-- 左侧：快速操作 -->
      <el-col :span="16">
        <el-card class="quick-actions-card" header="快速操作">
          <div class="quick-actions">
            <div class="action-item" @click="goToCommodityAnalysis">
              <div class="action-icon">
                <el-icon><Box /></el-icon>
              </div>
              <div class="action-content">
                <h3>商品分析</h3>
                <p>多智能体决策链分析大宗商品期货</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToCommodityPaper">
              <div class="action-icon">
                <el-icon><TrendCharts /></el-icon>
              </div>
              <div class="action-content">
                <h3>期货模拟</h3>
                <p>基于分析决策进行模拟期货交易</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToQueue">
              <div class="action-icon">
                <el-icon><List /></el-icon>
              </div>
              <div class="action-content">
                <h3>任务中心</h3>
                <p>查看和管理商品分析任务列表</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>

        <!-- 最近分析（任务中心联动） -->
        <el-card class="recent-analyses-card" header="最近分析" style="margin-top: 24px;">
          <el-table :data="recentAnalyses" style="width: 100%">
            <el-table-column label="合约代码" width="160">
              <template #default="{ row }">
                <span class="symbol-link" @click="viewCommodityReport(row)">{{ row.full_symbol }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="trade_date" label="交易日期" width="110" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="getStatusType(row.status)" size="small">
                  {{ getStatusText(row.status) }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="提交时间" width="170">
              <template #default="{ row }">
                {{ formatTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column label="操作">
              <template #default="{ row }">
                <el-button type="text" size="small" @click="viewCommodityReport(row)">
                  查看报告
                </el-button>
                <el-tooltip
                  v-if="row.status === 'failed' && row.error_message"
                  :content="row.error_message"
                  placement="top"
                >
                  <el-tag type="danger" size="small" effect="plain">失败原因</el-tag>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>

          <div class="table-footer">
            <el-button type="text" @click="goToQueue">
              查看全部任务 <el-icon><ArrowRight /></el-icon>
            </el-button>
          </div>
        </el-card>

        <!-- 市场快讯 -->
        <el-card class="market-news-card" style="margin-top: 24px;">
          <template #header>
            <span>市场快讯</span>
          </template>
          <div v-if="marketNews.length > 0" class="news-list">
            <div
              v-for="news in marketNews"
              :key="news.id"
              class="news-item"
              @click="openNewsUrl(news.url)"
            >
              <span class="news-title">{{ news.title }}</span>
              <span class="news-time">{{ newsRelativeTime(news.time) }}</span>
            </div>
          </div>
          <div v-else class="empty-state">
            <el-icon class="empty-icon"><InfoFilled /></el-icon>
            <p>暂无市场快讯</p>
          </div>
        </el-card>
      </el-col>

      <!-- 右侧：自选股和快讯 -->
      <el-col :span="8">
        <!-- 我的自选股 -->
        <el-card class="favorites-card">
          <template #header>
            <div class="card-header">
              <span>我的自选股</span>
              <el-button type="text" size="small" @click="goToFavorites">
                查看全部 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>

          <div v-if="favoriteStocks.length === 0" class="empty-favorites">
            <el-empty description="暂无自选股" :image-size="60">
              <el-button type="primary" size="small" @click="goToFavorites">
                添加自选股
              </el-button>
            </el-empty>
          </div>

          <div v-else class="favorites-list">
            <div
              v-for="stock in favoriteStocks.slice(0, 5)"
              :key="stock.stock_code"
              class="favorite-item"
              @click="viewStockDetail(stock)"
            >
              <div class="stock-info">
                <div class="stock-code">{{ stock.stock_code }}</div>
                <div class="stock-name">{{ stock.stock_name }}</div>
              </div>
              <div class="stock-price">
                <div class="current-price">¥{{ stock.current_price }}</div>
                <div
                  class="change-percent"
                  :class="getPriceChangeClass(stock.change_percent)"
                >
                  {{ stock.change_percent > 0 ? '+' : '' }}{{ Number(stock.change_percent).toFixed(2) }}%
                </div>
              </div>
            </div>
          </div>

          <div v-if="favoriteStocks.length > 5" class="favorites-footer">
            <el-button type="text" size="small" @click="goToFavorites">
              查看全部 {{ favoriteStocks.length }} 只自选股
            </el-button>
          </div>
        </el-card>

        <!-- 模拟交易账户 -->
        <el-card class="paper-trading-card" style="margin-top: 24px;">
          <template #header>
            <div class="card-header">
              <span>模拟交易账户</span>
              <el-button type="text" size="small" @click="goToPaperTrading">
                查看详情 <el-icon><ArrowRight /></el-icon>
              </el-button>
            </div>
          </template>

          <div v-if="paperAccount" class="paper-account-info">
            <!-- 期货模拟账户 -->
            <div class="account-section">
              <div class="account-section-title">📦 {{ paperAccount.name }}</div>
              <div class="account-item">
                <div class="account-label">账户权益</div>
                <div class="account-value primary">¥{{ formatMoney(paperAccount.equity) }}</div>
              </div>
              <div class="account-item">
                <div class="account-label">可用资金</div>
                <div class="account-value">¥{{ formatMoney(paperAccount.balance) }}</div>
              </div>
              <div class="account-item">
                <div class="account-label">累计盈亏</div>
                <div class="account-value" :class="paperAccount.realized_pnl >= 0 ? 'price-up' : 'price-down'">
                  {{ paperAccount.realized_pnl >= 0 ? '+' : '' }}¥{{ formatMoney(Math.abs(paperAccount.realized_pnl)) }}
                </div>
              </div>
            </div>
          </div>

          <div v-else class="empty-state">
            <el-icon class="empty-icon"><InfoFilled /></el-icon>
            <p>暂无账户信息</p>
            <el-button type="primary" size="small" @click="goToPaperTrading">
              查看模拟交易
            </el-button>
          </div>
        </el-card>

        <!-- 数据源和 LLM 供应商状态 -->
        <DataSourceLlmStatusCard style="margin-top: 24px;" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  TrendCharts,
  Box,
  List,
  ArrowRight,
  InfoFilled,
  Reading
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { AnalysisStatus } from '@/types/analysis'
import DataSourceLlmStatusCard from '@/components/Dashboard/DataSourceLlmStatusCard.vue'
import { favoritesApi } from '@/api/favorites'
import { commodityApi, commodityPaperApi, type CommodityTaskItem } from '@/api/commodity'

const router = useRouter()

// 响应式数据
const recentAnalyses = ref<CommodityTaskItem[]>([])

/** 商品分析最近记录(用于"最近分析"卡片) */
const recentCommodityRecords = ref<RecentReportItem[]>([])

// 自选股数据
const favoriteStocks = ref<any[]>([])

// 市场快讯数据
const marketNews = ref<any[]>([])

// 模拟交易账户数据
const paperAccount = ref<{ name: string; equity: number; balance: number; realized_pnl: number } | null>(null)

// 实时相对时间 tick（每分钟驱动一次）
const tick = ref(0)
let tickTimer: ReturnType<typeof setInterval> | null = null

// 方法
const goToQueue = () => {
  router.push('/queue')
}

const goToLearning = () => {
  router.push('/learning')
}

// ---------- 商品分析相关 ----------

/** 查看商品分析报告详情 */
function viewCommodityReport(row: CommodityTaskItem) {
  if (row.status === 'completed') {
    router.push(`/commodity/analysis?symbol=${row.full_symbol}`)
  } else {
    router.push('/queue')
  }
}

/** 前往商品分析页 */
function goToCommodityAnalysis() {
  router.push('/commodity/analysis')
}

/** 前往期货模拟 */
function goToCommodityPaper() {
  router.push('/commodity/paper')
}

/** 加载最近商品分析记录 */
async function loadRecentCommodityRecords() {
  try {
    const res = await commodityApi.getRecentReports(10)
    const body = (res as any)?.data
    recentCommodityRecords.value = body?.reports || []
  } catch (error) {
    console.error('加载最近商品分析记录失败:', error)
    recentCommodityRecords.value = []
  }
}



const openNewsUrl = (url?: string) => {
  if (url) {
    window.open(url, '_blank')
  } else {
    ElMessage.info('该新闻暂无详情链接')
  }
}

const getStatusType = (status: string | AnalysisStatus): 'success' | 'info' | 'warning' | 'danger' => {
  const statusMap: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    pending: 'info',
    processing: 'warning',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info'
  }
  return statusMap[status] || 'info'
}

const getStatusText = (status: string | AnalysisStatus) => {
  const statusMap: Record<string, string> = {
    pending: '等待中',
    processing: '处理中',
    running: '处理中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消'
  }
  return statusMap[status] || String(status)
}

import { formatDateTime, formatRelativeTime } from '@/utils/datetime'

const formatTime = (time: string) => {
  return formatDateTime(time)
}

/** 相对时间（依赖 tick 以自动刷新） */
const newsRelativeTime = (timeStr: string) => {
  // 通过 tick.value 触发 Vue 重新求值
  void tick.value
  return formatRelativeTime(timeStr)
}

// 自选股相关方法
const goToFavorites = () => {
  router.push('/favorites')
}

const viewStockDetail = (stock: any) => {
  // 可以跳转到股票详情页或分析页
  router.push(`/analysis/single?stock_code=${stock.stock_code}`)
}

const getPriceChangeClass = (changePercent: number) => {
  if (changePercent > 0) return 'price-up'
  if (changePercent < 0) return 'price-down'
  return 'price-neutral'
}

const loadFavoriteStocks = async () => {
  try {
    const response = await favoritesApi.list()
    if (response.success && response.data) {
      favoriteStocks.value = response.data.map((item: any) => ({
        stock_code: item.stock_code,
        stock_name: item.stock_name,
        current_price: item.current_price || 0,
        change_percent: item.change_percent || 0
      }))
    }
  } catch (error) {
    console.error('加载自选股失败:', error)
  }
}

const loadRecentAnalyses = async () => {
  try {
    // 使用商品分析任务中心接口，获取最近10条
    const res = await commodityApi.getTaskList({ limit: 10, offset: 0 })

    const body: any = (res as any)?.data || {}
    const tasks: CommodityTaskItem[] = body.tasks || []

    recentAnalyses.value = tasks as any
  } catch (error) {
    console.error('加载最近分析失败:', error)
    recentAnalyses.value = []
  }
}

const loadMarketNews = async () => {
  try {
    // 使用期货新闻接口获取市场快讯(global_macro 源慢,改用不依赖外部源的 all)
    const res = await commodityApi.getNews('all', 10)
    const body = (res as any)?.data
    if (body?.items?.length) {
      marketNews.value = body.items.map((item: any) => ({
        id: item.title,
        title: item.title || (item.content || '').substring(0, 60),
        time: item.published_at || item.date,
        url: item.url,
        source: item.source
      }))
    }
  } catch (error) {
    console.error('加载市场快讯失败:', error)
    marketNews.value = []
  }
}

// 加载期货模拟交易账户信息
const loadPaperAccount = async () => {
  try {
    // 取第一个期货模拟账户的快照
    const listRes = await commodityPaperApi.listAccounts()
    const accounts = (listRes as any)?.data?.accounts
    if (accounts?.length) {
      const acc = accounts[0]
      const snap = await commodityPaperApi.getAccountSnapshot(acc.account_id)
      const snapData = (snap as any)?.data
      paperAccount.value = {
        name: acc.name,
        equity: snapData?.equity ?? acc.initial_capital ?? 0,
        balance: snapData?.balance ?? acc.initial_capital ?? 0,
        realized_pnl: snapData?.realized_pnl ?? 0,
      }
    }
  } catch (error) {
    console.error('加载期货模拟交易账户失败:', error)
    paperAccount.value = null
  }
}

// 跳转到期货模拟交易页面
const goToPaperTrading = () => {
  router.push('/commodity/paper')
}

// 格式化金额
const formatMoney = (value: number) => {
  return value.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
}

// 生命周期
onMounted(async () => {
  // 加载自选股数据
  await loadFavoriteStocks()
  // 加载最近分析(商品任务中心)
  await loadRecentAnalyses()
  // 加载最近商品分析记录
  await loadRecentCommodityRecords()
  // 加载市场快讯
  await loadMarketNews()
  // 加载期货模拟交易账户
  await loadPaperAccount()

  // 每分钟刷一次 tick，保持相对时间实时更新
  tickTimer = setInterval(() => { tick.value++ }, 60_000)
})

onUnmounted(() => {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
})
</script>

<style lang="scss" scoped>
.dashboard {
  .welcome-section {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px;
    padding: 40px;
    color: white;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;

    .welcome-content {
      .welcome-title {
        font-size: 32px;
        font-weight: 600;
        margin: 0 0 12px 0;
        display: flex;
        align-items: center;
        gap: 16px;

        .version-badge {
          background: rgba(255, 255, 255, 0.2);
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 14px;
          font-weight: 400;
        }
      }

      .welcome-subtitle {
        font-size: 16px;
        opacity: 0.9;
        margin: 0;
      }
    }

    .welcome-actions {
      display: flex;
      gap: 16px;
    }
  }

  .learning-highlight-card {
    margin-bottom: 24px;
    border: 2px solid var(--el-color-primary);
    box-shadow: 0 4px 12px rgba(102, 126, 234, 0.15);

    .learning-highlight {
      display: flex;
      align-items: center;
      gap: 24px;
      padding: 8px;

      .learning-icon {
        flex-shrink: 0;
        width: 80px;
        height: 80px;
        border-radius: 12px;
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
      }

      .learning-content {
        flex: 1;

        h2 {
          font-size: 20px;
          font-weight: 600;
          margin: 0 0 12px 0;
          color: var(--el-text-color-primary);
        }

        p {
          font-size: 14px;
          color: var(--el-text-color-regular);
          line-height: 1.6;
          margin: 0 0 16px 0;
        }

        .learning-features {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;

          .feature-tag {
            padding: 4px 12px;
            background: var(--el-color-primary-light-9);
            color: var(--el-color-primary);
            border-radius: 16px;
            font-size: 13px;
            font-weight: 500;
          }
        }
      }

      .learning-action {
        flex-shrink: 0;
      }
    }
  }

  .quick-actions-card {
    .quick-actions {
      display: grid;
      gap: 16px;

      .action-item {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 20px;
        border: 1px solid var(--el-border-color-lighter);
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.3s ease;

        &:hover {
          border-color: var(--el-color-primary);
          background-color: var(--el-color-primary-light-9);
        }

        .action-icon {
          width: 40px;
          height: 40px;
          border-radius: 8px;
          background: var(--el-color-primary-light-8);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--el-color-primary);
          font-size: 20px;
        }

        .action-content {
          flex: 1;

          h3 {
            margin: 0 0 4px 0;
            font-size: 16px;
            font-weight: 600;
            color: var(--el-text-color-primary);
          }

          p {
            margin: 0;
            font-size: 14px;
            color: var(--el-text-color-regular);
          }
        }

        .action-arrow {
          color: var(--el-text-color-placeholder);
          transition: transform 0.3s ease;
        }

        &:hover .action-arrow {
          transform: translateX(4px);
        }
      }
    }
  }

  .recent-analyses-card {
    .symbol-link {
      color: var(--el-color-primary);
      cursor: pointer;
      font-weight: 500;
      &:hover { text-decoration: underline; }
    }
    .table-footer {
      text-align: center;
      margin-top: 16px;
    }
  }

  .system-status-card {
    .status-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;

      &:not(:last-child) {
        border-bottom: 1px solid var(--el-border-color-lighter);
      }

      .status-label {
        color: var(--el-text-color-regular);
      }

      .status-value {
        font-weight: 600;
        color: var(--el-text-color-primary);
      }
    }
  }

  .market-news-card {
    .news-list {
      .news-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 12px;
        padding: 10px 0;
        cursor: pointer;
        border-bottom: 1px solid var(--el-border-color-lighter);

        &:last-child {
          border-bottom: none;
        }

        &:hover {
          background-color: var(--el-fill-color-lighter);
          margin: 0 -16px;
          padding: 10px 16px;
          border-radius: 4px;
        }

        .news-title {
          flex: 1;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          font-size: 14px;
          color: var(--el-text-color-primary);
          line-height: 1.4;
        }

        .news-time {
          flex-shrink: 0;
          font-size: 12px;
          color: var(--el-text-color-placeholder);
          white-space: nowrap;
        }
      }
    }
  }

  .tips-card {
    .tip-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 0;
      font-size: 14px;
      color: var(--el-text-color-regular);

      .tip-icon {
        color: var(--el-color-primary);
      }
    }
  }

  .favorites-card {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .empty-favorites {
      text-align: center;
      padding: 20px 0;
    }

    .favorites-list {
      .favorite-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid var(--el-border-color-lighter);
        cursor: pointer;
        transition: background-color 0.3s ease;

        &:hover {
          background-color: var(--el-fill-color-lighter);
          margin: 0 -16px;
          padding: 12px 16px;
          border-radius: 6px;
        }

        &:last-child {
          border-bottom: none;
        }

        .stock-info {
          .stock-code {
            font-weight: 600;
            font-size: 14px;
            color: var(--el-text-color-primary);
          }

          .stock-name {
            font-size: 12px;
            color: var(--el-text-color-regular);
            margin-top: 2px;
          }
        }

        .stock-price {
          text-align: right;

          .current-price {
            font-weight: 600;
            font-size: 14px;
            color: var(--el-text-color-primary);
          }

          .change-percent {
            font-size: 12px;
            margin-top: 2px;

            &.price-up {
              color: #f56c6c;
            }

            &.price-down {
              color: #67c23a;
            }

            &.price-neutral {
              color: var(--el-text-color-regular);
            }
          }
        }
      }
    }

    .favorites-footer {
      text-align: center;
      padding-top: 12px;
      border-top: 1px solid var(--el-border-color-lighter);
      margin-top: 12px;
    }
  }

  .paper-trading-card {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .paper-account-info {
      display: flex;
      flex-direction: column;
      gap: 16px;

      .account-section {
        border: 1px solid var(--el-border-color-lighter);
        border-radius: 8px;
        padding: 12px;
        background-color: var(--el-fill-color-blank);

        .account-section-title {
          font-size: 14px;
          font-weight: 600;
          color: var(--el-text-color-primary);
          margin-bottom: 12px;
          padding-bottom: 8px;
          border-bottom: 1px solid var(--el-border-color-lighter);
        }
      }

      .account-item {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 8px 0;

        .account-label {
          font-size: 13px;
          color: var(--el-text-color-regular);
        }

        .account-value {
          font-size: 15px;
          font-weight: 600;
          color: var(--el-text-color-primary);

          &.primary {
            color: var(--el-color-primary);
            font-size: 16px;
          }

          &.price-up {
            color: #f56c6c;
          }

          &.price-down {
            color: #67c23a;
          }

          &.price-neutral {
            color: var(--el-text-color-regular);
          }
        }
      }
    }

    .empty-state {
      text-align: center;
      padding: 20px 0;

      .empty-icon {
        font-size: 48px;
        color: var(--el-text-color-placeholder);
        margin-bottom: 12px;
      }

      p {
        color: var(--el-text-color-secondary);
        margin-bottom: 16px;
      }
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .dashboard {
    .welcome-section {
      flex-direction: column;
      text-align: center;
      gap: 24px;

      .welcome-actions {
        justify-content: center;
      }
    }

    .learning-highlight-card {
      .learning-highlight {
        flex-direction: column;
        text-align: center;

        .learning-content {
          .learning-features {
            justify-content: center;
          }
        }
      }
    }

    .main-content {
      .el-col {
        margin-bottom: 24px;
      }
    }
  }
}
</style>
