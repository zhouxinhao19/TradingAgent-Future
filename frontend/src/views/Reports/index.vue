<template>
  <div class="commodity-reports">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Document /></el-icon>
        商品分析报告
      </h1>
      <p class="page-description">
        查看和管理大宗商品期货分析报告，包含完整的多智能体决策链详情
      </p>
    </div>

    <!-- 筛选和操作栏 -->
    <el-card class="filter-card" shadow="never">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索合约代码"
            clearable
            @input="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>

        <el-col :span="4">
          <el-select v-model="exchangeFilter" clearable placeholder="交易所筛选" @change="handleFilterChange">
            <el-option label="全部" value="" />
            <el-option label="上期所" value="SHF" />
            <el-option label="大商所" value="DCE" />
            <el-option label="郑商所" value="ZCE" />
            <el-option label="能源中心" value="INE" />
            <el-option label="广期所" value="GFEX" />
            <el-option label="中金所" value="CFX" />
          </el-select>
        </el-col>

        <el-col :span="4">
          <el-select v-model="directionFilter" clearable placeholder="方向筛选" @change="handleFilterChange">
            <el-option label="全部" value="" />
            <el-option label="做多" value="long" />
            <el-option label="做空" value="short" />
            <el-option label="持有" value="hold" />
            <el-option label="平仓" value="flat" />
          </el-select>
        </el-col>

        <el-col :span="6">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="handleFilterChange"
          />
        </el-col>

        <el-col :span="4">
          <div class="action-buttons">
            <el-button type="primary" @click="goToCommodityAnalysis">
              <el-icon><TrendCharts /></el-icon>
              新建分析
            </el-button>
            <el-button @click="fetchReports">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 报告列表 -->
    <el-card class="reports-list-card" shadow="never">
      <el-table
        :data="filteredReports"
        v-loading="loading"
        style="width: 100%"
        @row-click="viewReport"
      >
        <el-table-column prop="full_symbol" label="合约代码" width="140" />

        <el-table-column label="方向" width="90">
          <template #default="{ row }">
            <el-tag :type="directionTagType(row.direction)" size="small">
              {{ directionLabel(row.direction) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="置信度" width="90">
          <template #default="{ row }">
            {{ (row.confidence * 100).toFixed(0) }}%
          </template>
        </el-table-column>

        <el-table-column prop="trade_date" label="交易日期" width="120" />

        <el-table-column label="分析时间" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button type="text" size="small" @click.stop="viewReport(row)">
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="totalReports"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 报告详情抽屉 -->
    <el-drawer
      v-model="detailDrawerVisible"
      title="报告详情"
      size="60%"
      direction="rtl"
    >
      <template v-if="detailData">
        <div v-for="(value, key) in detailData" :key="key" class="detail-section">
          <h4 v-if="typeof value === 'string' && value.length > 20" class="section-title">
            {{ sectionTitle(key as string) }}
          </h4>
          <div v-if="typeof value === 'string' && value.length > 20" class="section-content">
            {{ value }}
          </div>
        </div>
      </template>
      <div v-else class="empty-detail">
        <el-empty description="加载报告详情中..." />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  Document,
  Search,
  Refresh,
  TrendCharts,
} from '@element-plus/icons-vue'
import { commodityApi, type RecentReportItem } from '@/api/commodity'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()

// 响应式数据
const loading = ref(false)
const searchKeyword = ref('')
const exchangeFilter = ref('')
const directionFilter = ref('')
const dateRange = ref<[string, string] | null>(null)
const currentPage = ref(1)
const pageSize = ref(20)
const totalReports = ref(0)

const reports = ref<RecentReportItem[]>([])

// 报告详情
const detailDrawerVisible = ref(false)
const detailData = ref<Record<string, any> | null>(null)

// 交易所后缀映射
const EXCHANGE_SUFFIX: Record<string, string> = {
  SHF: '.SHF', DCE: '.DCE', ZCE: '.ZCE',
  INE: '.INE', GFEX: '.GFEX', CFX: '.CFX',
}

// 方向标签
function directionLabel(direction: string): string {
  const map: Record<string, string> = { long: '做多', short: '做空', hold: '持有', flat: '平仓' }
  return map[direction] || direction
}
function directionTagType(direction: string): string {
  const map: Record<string, string> = { long: 'success', short: 'danger', hold: 'info', flat: 'warning' }
  return map[direction] || 'info'
}

function sectionTitle(key: string): string {
  const map: Record<string, string> = {
    market_report: '📈 技术分析',
    fundamentals_report: '💼 基本面分析',
    sentiment_report: '🧠 持仓情绪',
    news_report: '📰 新闻分析',
    investment_plan: '📋 投资计划',
    trader_investment_plan: '💼 交易员计划',
    final_trade_decision: '🎯 最终交易决策',
    final_decision: '🏛️ CIO 决策',
  }
  return map[key] || key
}

const formatTime = (t: string) => (t ? formatDateTime(t) : '-')

// 计算属性：客户端过滤
const filteredReports = computed(() => {
  let arr = reports.value

  if (searchKeyword.value) {
    const k = searchKeyword.value.toLowerCase()
    arr = arr.filter((x) => x.full_symbol.toLowerCase().includes(k))
  }
  if (exchangeFilter.value) {
    const suffix = EXCHANGE_SUFFIX[exchangeFilter.value]
    if (suffix) arr = arr.filter((x) => x.full_symbol.endsWith(suffix))
  }
  if (directionFilter.value) {
    arr = arr.filter((x) => x.direction === directionFilter.value)
  }
  if (dateRange.value && dateRange.value.length === 2) {
    const [start, end] = dateRange.value
    arr = arr.filter((x) => x.trade_date >= start && x.trade_date <= end)
  }
  return arr
})

const pagedReports = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredReports.value.slice(start, start + pageSize.value)
})

// API 调用
const fetchReports = async () => {
  loading.value = true
  try {
    const res = await commodityApi.getRecentReports(50)
    const body = (res as any)?.data
    const items: RecentReportItem[] = body?.reports || []
    reports.value = items.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    totalReports.value = filteredReports.value.length
  } catch (e) {
    console.error('获取报告列表失败:', e)
    ElMessage.error('获取报告列表失败')
    reports.value = []
  } finally {
    loading.value = false
  }
}

// 方法
const handleSearch = () => {
  currentPage.value = 1
  totalReports.value = filteredReports.value.length
}
const handleFilterChange = () => {
  currentPage.value = 1
  totalReports.value = filteredReports.value.length
}

const viewReport = async (row: RecentReportItem) => {
  detailDrawerVisible.value = true
  detailData.value = null
  try {
    const res = await commodityApi.getReportDetail(row.report_id)
    detailData.value = (res as any)?.data || null
  } catch {
    ElMessage.error('获取报告详情失败')
    detailDrawerVisible.value = false
  }
}

const goToCommodityAnalysis = () => {
  router.push('/commodity/analysis')
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  totalReports.value = filteredReports.value.length
}
const handleCurrentChange = (page: number) => {
  currentPage.value = page
}

// 生命周期
onMounted(() => {
  fetchReports()
})
</script>

<style lang="scss" scoped>
.commodity-reports {
  .page-header {
    margin-bottom: 24px;

    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 24px;
      font-weight: 600;
      color: var(--el-text-color-primary);
      margin: 0 0 8px 0;
    }

    .page-description {
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }

  .filter-card {
    margin-bottom: 24px;

    .action-buttons {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    }
  }

  .reports-list-card {
    .pagination-wrapper {
      display: flex;
      justify-content: center;
      margin-top: 24px;
    }
  }

  .detail-section { margin-bottom: 20px; }
  .section-title {
    margin: 0 0 8px; padding: 8px 12px;
    background: var(--el-color-primary-light-9, #ecf5ff);
    border-radius: 4px; font-size: 15px;
  }
  .section-content {
    white-space: pre-wrap; font-size: 14px; line-height: 1.6; padding: 0 12px;
    max-height: 400px; overflow-y: auto;
  }
  .empty-detail { display: flex; align-items: center; justify-content: center; height: 300px; }
}
</style>
