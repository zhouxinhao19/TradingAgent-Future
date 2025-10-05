<template>
  <div class="report-detail">
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-container">
      <el-skeleton :rows="10" animated />
    </div>

    <!-- 报告内容 -->
    <div v-else-if="report" class="report-content">
      <!-- 报告头部 -->
      <el-card class="report-header" shadow="never">
        <div class="header-content">
          <div class="title-section">
            <h1 class="report-title">
              <el-icon><Document /></el-icon>
              {{ report.stock_symbol }} 分析报告
            </h1>
            <div class="report-meta">
              <el-tag type="primary">{{ report.stock_symbol }}</el-tag>
              <el-tag type="success">{{ getStatusText(report.status) }}</el-tag>
              <span class="meta-item">
                <el-icon><Calendar /></el-icon>
                {{ formatTime(report.created_at) }}
              </span>
              <span class="meta-item">
                <el-icon><User /></el-icon>
                {{ report.analysts.join(', ') }}
              </span>
            </div>
          </div>
          
          <div class="action-section">
            <el-button
              v-if="canApplyToTrading"
              type="success"
              @click="applyToTrading"
            >
              <el-icon><ShoppingCart /></el-icon>
              应用到交易
            </el-button>
            <el-button type="primary" @click="downloadReport">
              <el-icon><Download /></el-icon>
              下载报告
            </el-button>
            <el-button @click="goBack">
              <el-icon><Back /></el-icon>
              返回
            </el-button>
          </div>
        </div>
      </el-card>

      <!-- 报告摘要 -->
      <el-card v-if="report.summary" class="summary-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><InfoFilled /></el-icon>
            <span>执行摘要</span>
          </div>
        </template>
        <div class="summary-content markdown-content" v-html="renderMarkdown(report.summary)"></div>
      </el-card>

      <!-- 关键指标 -->
      <el-card v-if="report.key_points && report.key_points.length > 0" class="metrics-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><TrendCharts /></el-icon>
            <span>关键要点</span>
          </div>
        </template>
        <div class="metrics-content">
          <el-row :gutter="16">
            <el-col :span="8">
              <div class="metric-item">
                <div class="metric-label">投资建议</div>
                <div class="metric-value markdown-content" v-html="renderMarkdown(report.recommendation || '暂无')"></div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="metric-item">
                <div class="metric-label">信心评分</div>
                <div class="metric-value">{{ report.confidence_score || 0 }}%</div>
              </div>
            </el-col>
            <el-col :span="8">
              <div class="metric-item">
                <div class="metric-label">风险等级</div>
                <div class="metric-value">{{ report.risk_level || '中等' }}</div>
              </div>
            </el-col>
          </el-row>
          
          <div class="key-points">
            <h4>关键要点：</h4>
            <ul>
              <li v-for="(point, index) in report.key_points" :key="index">
                {{ point }}
              </li>
            </ul>
          </div>
        </div>
      </el-card>

      <!-- 报告模块 -->
      <el-card class="modules-card" shadow="never">
        <template #header>
          <div class="card-header">
            <el-icon><Files /></el-icon>
            <span>分析报告</span>
          </div>
        </template>
        
        <el-tabs v-model="activeModule" type="border-card">
          <el-tab-pane
            v-for="(content, moduleName) in report.reports"
            :key="moduleName"
            :label="getModuleDisplayName(moduleName)"
            :name="moduleName"
          >
            <div class="module-content">
              <div v-if="typeof content === 'string'" class="markdown-content">
                <div v-html="renderMarkdown(content)"></div>
              </div>
              <div v-else class="json-content">
                <pre>{{ JSON.stringify(content, null, 2) }}</pre>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </el-card>
    </div>

    <!-- 错误状态 -->
    <div v-else class="error-container">
      <el-result
        icon="error"
        title="报告加载失败"
        sub-title="请检查报告ID是否正确或稍后重试"
      >
        <template #extra>
          <el-button type="primary" @click="goBack">返回列表</el-button>
        </template>
      </el-result>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, h, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, ElInput, ElInputNumber, ElForm, ElFormItem } from 'element-plus'
import { paperApi } from '@/api/paper'
import { stocksApi } from '@/api/stocks'
import {
  Document,
  Calendar,
  User,
  Download,
  Back,
  InfoFilled,
  TrendCharts,
  Files,
  ShoppingCart
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { marked } from 'marked'

// 路由和认证
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()

// 配置 marked 以获得更完整的 Markdown 支持
marked.setOptions({ breaks: true, gfm: true })

// 响应式数据
const loading = ref(true)
const report = ref(null)
const activeModule = ref('')

// 获取报告详情
const fetchReportDetail = async () => {
  loading.value = true
  try {
    const reportId = route.params.id as string
    
    const response = await fetch(`/api/reports/${reportId}/detail`, {
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      }
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const result = await response.json()
    
    if (result.success) {
      report.value = result.data
      
      // 设置默认激活的模块
      const reports = result.data.reports || {}
      const moduleNames = Object.keys(reports)
      if (moduleNames.length > 0) {
        activeModule.value = moduleNames[0]
      }
    } else {
      throw new Error(result.message || '获取报告详情失败')
    }
  } catch (error) {
    console.error('获取报告详情失败:', error)
    ElMessage.error('获取报告详情失败')
  } finally {
    loading.value = false
  }
}

// 下载报告
const downloadReport = async () => {
  try {
    const response = await fetch(`/api/reports/${report.value.id}/download?format=markdown`, {
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }
    
    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${report.value.stock_symbol}_${report.value.analysis_date}_report.md`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)
    
    ElMessage.success('报告下载成功')
  } catch (error) {
    console.error('下载报告失败:', error)
    ElMessage.error('下载报告失败')
  }
}

// 判断是否可以应用到交易
const canApplyToTrading = computed(() => {
  if (!report.value) return false
  const rec = report.value.recommendation || ''
  // 检查是否包含买入或卖出建议
  return rec.includes('买入') || rec.includes('卖出') || rec.toLowerCase().includes('buy') || rec.toLowerCase().includes('sell')
})

// 解析投资建议
const parseRecommendation = () => {
  if (!report.value) return null

  const rec = report.value.recommendation || ''
  const traderPlan = report.value.reports?.trader_investment_plan || ''

  // 解析操作类型
  let action: 'buy' | 'sell' | null = null
  if (rec.includes('买入') || rec.toLowerCase().includes('buy')) {
    action = 'buy'
  } else if (rec.includes('卖出') || rec.toLowerCase().includes('sell')) {
    action = 'sell'
  }

  if (!action) return null

  // 解析目标价格（从recommendation或trader_investment_plan中提取）
  let targetPrice: number | null = null
  const priceMatch = rec.match(/目标价[格]?[：:]\s*([0-9.]+)/) ||
                     traderPlan.match(/目标价[格]?[：:]\s*([0-9.]+)/)
  if (priceMatch) {
    targetPrice = parseFloat(priceMatch[1])
  }

  return {
    action,
    targetPrice,
    confidence: report.value.confidence_score || 0,
    riskLevel: report.value.risk_level || '中等'
  }
}

// 应用到模拟交易
const applyToTrading = async () => {
  const recommendation = parseRecommendation()
  if (!recommendation) {
    ElMessage.warning('无法解析投资建议，请检查报告内容')
    return
  }

  try {
    // 获取账户信息
    const accountRes = await paperApi.getAccount()
    if (!accountRes.success || !accountRes.data) {
      ElMessage.error('获取账户信息失败')
      return
    }

    const account = accountRes.data.account
    const positions = accountRes.data.positions

    // 查找当前持仓
    const currentPosition = positions.find(p => p.code === report.value.stock_symbol)

    // 获取当前实时价格
    let currentPrice = 10 // 默认价格
    try {
      const quoteRes = await stocksApi.getQuote(report.value.stock_symbol)
      if (quoteRes.success && quoteRes.data && quoteRes.data.price) {
        currentPrice = quoteRes.data.price
      }
    } catch (error) {
      console.warn('获取实时价格失败，使用默认价格')
    }

    // 计算建议交易数量
    let suggestedQuantity = 0
    let maxQuantity = 0

    if (recommendation.action === 'buy') {
      // 买入：根据可用资金和当前价格计算
      const availableCash = account.cash
      maxQuantity = Math.floor(availableCash / currentPrice / 100) * 100 // 100股为单位
      const suggested = Math.floor(maxQuantity * 0.2) // 建议使用20%资金
      suggestedQuantity = Math.floor(suggested / 100) * 100 // 向下取整到100的倍数
      suggestedQuantity = Math.max(100, suggestedQuantity) // 至少100股
    } else {
      // 卖出：根据当前持仓计算
      if (!currentPosition || currentPosition.quantity === 0) {
        ElMessage.warning('当前没有持仓，无法卖出')
        return
      }
      maxQuantity = currentPosition.quantity
      suggestedQuantity = Math.floor(maxQuantity / 100) * 100 // 向下取整到100的倍数
      suggestedQuantity = Math.max(100, suggestedQuantity) // 至少100股
    }

    // 用户可修改的价格和数量（使用reactive）
    const tradeForm = reactive({
      price: currentPrice,
      quantity: suggestedQuantity
    })

    // 显示可编辑的确认对话框
    const actionText = recommendation.action === 'buy' ? '买入' : '卖出'
    const actionColor = recommendation.action === 'buy' ? '#67C23A' : '#F56C6C'

    // 创建一个响应式的消息组件
    const MessageComponent = {
      setup() {
        // 计算预计金额
        const estimatedAmount = computed(() => {
          return (tradeForm.price * tradeForm.quantity).toFixed(2)
        })

        return () => h('div', { style: 'line-height: 2;' }, [
          h('p', [
            h('strong', '股票代码：'),
            h('span', report.value.stock_symbol)
          ]),
          h('p', [
            h('strong', '操作类型：'),
            h('span', { style: `color: ${actionColor}; font-weight: bold;` }, actionText)
          ]),
          recommendation.targetPrice ? h('p', [
            h('strong', '目标价格：'),
            h('span', { style: 'color: #E6A23C;' }, `${recommendation.targetPrice.toFixed(2)}元`),
            h('span', { style: 'color: #909399; font-size: 12px; margin-left: 8px;' }, '(预期最高价)')
          ]) : null,
          h('p', [
            h('strong', '当前价格：'),
            h('span', `${currentPrice.toFixed(2)}元`)
          ]),
          h('div', { style: 'margin: 16px 0;' }, [
            h('p', { style: 'margin-bottom: 8px;' }, [
              h('strong', '交易价格：'),
              h('span', { style: 'color: #909399; font-size: 12px; margin-left: 8px;' }, '(可修改)')
            ]),
            h(ElInputNumber, {
              modelValue: tradeForm.price,
              'onUpdate:modelValue': (val: number) => { tradeForm.price = val },
              min: 0.01,
              max: 9999,
              precision: 2,
              step: 0.01,
              style: 'width: 200px;',
              controls: true
            })
          ]),
          h('div', { style: 'margin: 16px 0;' }, [
            h('p', { style: 'margin-bottom: 8px;' }, [
              h('strong', '交易数量：'),
              h('span', { style: 'color: #909399; font-size: 12px; margin-left: 8px;' }, '(可修改，100股为单位)')
            ]),
            h(ElInputNumber, {
              modelValue: tradeForm.quantity,
              'onUpdate:modelValue': (val: number) => { tradeForm.quantity = val },
              min: 100,
              max: maxQuantity,
              step: 100,
              style: 'width: 200px;',
              controls: true
            })
          ]),
          h('p', [
            h('strong', '预计金额：'),
            h('span', { style: 'color: #409EFF; font-weight: bold;' }, `${estimatedAmount.value}元`)
          ]),
          h('p', [
            h('strong', '置信度：'),
            h('span', `${(recommendation.confidence * 100).toFixed(1)}%`)
          ]),
          h('p', [
            h('strong', '风险等级：'),
            h('span', recommendation.riskLevel)
          ]),
          recommendation.action === 'buy' ? h('p', { style: 'color: #909399; font-size: 12px; margin-top: 12px;' },
            `可用资金：${account.cash.toFixed(2)}元，最大可买：${maxQuantity}股`
          ) : null,
          recommendation.action === 'sell' ? h('p', { style: 'color: #909399; font-size: 12px; margin-top: 12px;' },
            `当前持仓：${maxQuantity}股`
          ) : null
        ])
      }
    }

    await ElMessageBox({
      title: '确认交易',
      message: h(MessageComponent),
      confirmButtonText: '确认下单',
      cancelButtonText: '取消',
      type: 'warning',
      beforeClose: (action, instance, done) => {
        if (action === 'confirm') {
          // 验证输入
          if (tradeForm.quantity < 100 || tradeForm.quantity % 100 !== 0) {
            ElMessage.error('交易数量必须是100的整数倍')
            return
          }
          if (tradeForm.quantity > maxQuantity) {
            ElMessage.error(`交易数量不能超过${maxQuantity}股`)
            return
          }
          if (tradeForm.price <= 0) {
            ElMessage.error('交易价格必须大于0')
            return
          }

          // 检查资金是否充足
          if (recommendation.action === 'buy') {
            const totalAmount = tradeForm.price * tradeForm.quantity
            if (totalAmount > account.cash) {
              ElMessage.error('可用资金不足')
              return
            }
          }
        }
        done()
      }
    })

    // 执行交易
    const orderRes = await paperApi.placeOrder({
      code: report.value.stock_symbol,
      side: recommendation.action,
      quantity: tradeForm.quantity,
      analysis_id: report.value.analysis_id || report.value.id
    })

    if (orderRes.success) {
      ElMessage.success(`${actionText}订单已提交成功！`)
      // 可选：跳转到模拟交易页面
      setTimeout(() => {
        router.push('/paper-trading')
      }, 1500)
    } else {
      ElMessage.error(orderRes.message || '下单失败')
    }

  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('应用到交易失败:', error)
      ElMessage.error(error.message || '操作失败')
    }
  }
}

// 返回列表
const goBack = () => {
  router.push('/reports')
}

// 工具函数
const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    completed: '已完成',
    processing: '生成中',
    failed: '失败'
  }
  return statusMap[status] || status
}

const formatTime = (time: string) => {
  return new Date(time).toLocaleString('zh-CN')
}

const getModuleDisplayName = (moduleName: string) => {
  // 统一与单股分析的中文标签映射
  const nameMap: Record<string, string> = {
    market_report: '📈 市场技术分析',
    fundamentals_report: '💰 基本面分析',
    news_report: '📰 新闻事件分析',
    sentiment_report: '💭 市场情绪分析',
    investment_plan: '📋 投资建议',
    trader_investment_plan: '💼 交易团队计划',
    final_trade_decision: '🎯 最终交易决策',
    research_team_decision: '🔬 研究团队决策',
    risk_management_decision: '⚖️ 风险管理团队',
    // 兼容旧字段
    investment_debate_state: '🔬 研究团队决策',
    risk_debate_state: '⚖️ 风险管理团队',
    detailed_analysis: '📄 详细分析'
  }
  // 未匹配到时，做一个友好的回退：下划线转空格
  return nameMap[moduleName] || moduleName.replace(/_/g, ' ')
}

const renderMarkdown = (content: string) => {
  if (!content) return ''
  try {
    return marked.parse(content) as string
  } catch (e) {
    return `<pre style="white-space: pre-wrap; font-family: inherit;">${content}</pre>`
  }
}

// 生命周期
onMounted(() => {
  fetchReportDetail()
})
</script>

<style lang="scss" scoped>
.report-detail {
  .loading-container {
    padding: 24px;
  }

  .report-content {
    .report-header {
      margin-bottom: 24px;

      .header-content {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;

        .title-section {
          .report-title {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 24px;
            font-weight: 600;
            color: var(--el-text-color-primary);
            margin: 0 0 12px 0;
          }

          .report-meta {
            display: flex;
            align-items: center;
            gap: 16px;
            flex-wrap: wrap;

            .meta-item {
              display: flex;
              align-items: center;
              gap: 4px;
              color: var(--el-text-color-regular);
              font-size: 14px;
            }
          }
        }

        .action-section {
          display: flex;
          gap: 8px;
        }
      }
    }

    .summary-card,
    .metrics-card,
    .modules-card {
      margin-bottom: 24px;

      .card-header {
        display: flex;
        align-items: center;
        gap: 8px;
        font-weight: 600;
      }
    }

    .summary-content {
      line-height: 1.6;
      color: var(--el-text-color-primary);
    }

    .metrics-content {
      .metric-item {
        text-align: center;
        padding: 16px;
        border: 1px solid var(--el-border-color-light);
        border-radius: 8px;

        .metric-label {
          font-size: 14px;
          color: var(--el-text-color-regular);
          margin-bottom: 8px;
        }

        .metric-value {
          font-size: 18px;
          font-weight: 600;
          color: var(--el-color-primary);
        }
      }

      .key-points {
        margin-top: 24px;

        h4 {
          margin: 0 0 12px 0;
          color: var(--el-text-color-primary);
        }

        ul {
          margin: 0;
          padding-left: 20px;

          li {
            margin-bottom: 8px;
            line-height: 1.5;
          }
        }
      }
    }

    .module-content {
      .markdown-content {
        line-height: 1.6;
        
        :deep(h1), :deep(h2), :deep(h3) {
          margin: 16px 0 8px 0;
          color: var(--el-text-color-primary);
        }

        :deep(h1) { font-size: 24px; }
        :deep(h2) { font-size: 20px; }
        :deep(h3) { font-size: 16px; }
      }

      .json-content {
        pre {
          background: var(--el-fill-color-light);
          padding: 16px;
          border-radius: 8px;
          overflow-x: auto;
          font-size: 14px;
          line-height: 1.4;
        }
      }
    }
  }

  .error-container {
    padding: 48px 24px;
  }
}
</style>
