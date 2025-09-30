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
            <el-button type="primary" @click="downloadReport">
              <el-icon><Download /></el-icon>
              下载报告
            </el-button>
            <el-button @click="shareReport">
              <el-icon><Share /></el-icon>
              分享
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
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Document,
  Calendar,
  User,
  Download,
  Share,
  Back,
  InfoFilled,
  TrendCharts,
  Files
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

// 分享报告
const shareReport = () => {
  ElMessage.info('分享功能开发中...')
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
