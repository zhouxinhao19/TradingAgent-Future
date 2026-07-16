<template>
  <div class="commodity-task-center">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        商品分析记录
      </h1>
      <p class="page-description">查看所有大宗商品品种的历史分析报告</p>
    </div>

    <!-- 筛选表单 -->
    <el-card class="filter-card" shadow="never">
      <el-form :inline="true" @submit.prevent>
        <el-form-item label="交易所">
          <el-select v-model="filters.exchange" clearable placeholder="全部" style="width: 120px" @change="applyFilters">
            <el-option label="全部" value="" />
            <el-option label="上期所" value="SHF" />
            <el-option label="大商所" value="DCE" />
            <el-option label="郑商所" value="ZCE" />
            <el-option label="能源中心" value="INE" />
            <el-option label="广期所" value="GFEX" />
            <el-option label="中金所" value="CFX" />
          </el-select>
        </el-form-item>
        <el-form-item label="方向">
          <el-select v-model="filters.direction" clearable placeholder="全部" style="width: 120px" @change="applyFilters">
            <el-option label="全部" value="" />
            <el-option label="做多" value="long" />
            <el-option label="做空" value="short" />
            <el-option label="持有" value="hold" />
            <el-option label="平仓" value="flat" />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker v-model="filters.dateRange" type="daterange" range-separator="至" start-placeholder="开始日期" end-placeholder="结束日期" format="YYYY-MM-DD" value-format="YYYY-MM-DD" style="width: 260px" @change="applyFilters" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="applyFilters" :loading="loading">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 统计卡片 -->
    <el-row :gutter="16" style="margin-top: 12px">
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.total }}</div><div class="label">总报告</div></div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.longCount }}</div><div class="label">做多</div></div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.shortCount }}</div><div class="label">做空</div></div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never"><div class="stat"><div class="value">{{ stats.holdCount }}</div><div class="label">持有/平仓</div></div></el-card>
      </el-col>
    </el-row>

    <el-card class="list-card" shadow="never">
      <div class="list-header">
        <div class="left">
          <el-input v-model="keyword" placeholder="搜索合约代码" clearable style="width: 220px" />
          <el-button @click="loadList" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
          <el-button type="primary" @click="goToCommodityAnalysis">
            <el-icon><TrendCharts /></el-icon>
            新建分析
          </el-button>
        </div>
      </div>

      <el-table :data="pagedList" v-loading="loading" style="width: 100%">
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
            <el-button type="text" size="small" @click="viewReport(row)">查看报告</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="filteredList.length"
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
import { List, Refresh, TrendCharts } from '@element-plus/icons-vue'
import { commodityApi, type RecentReportItem } from '@/api/commodity'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()

// 状态
const loading = ref(false)
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const list = ref<RecentReportItem[]>([])

// 筛选
const filters = ref<{
  exchange: string
  direction: string
  dateRange: string[]
}>({
  exchange: '',
  direction: '',
  dateRange: [],
})

// 统计
const stats = ref({ total: 0, longCount: 0, shortCount: 0, holdCount: 0 })

// 报告详情
const detailDrawerVisible = ref(false)
const detailData = ref<Record<string, any> | null>(null)

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

// 客户端过滤（按交易所 + 方向 + 日期 + 关键词）
const filteredList = computed(() => {
  let arr = list.value

  if (filters.value.exchange) {
    const suffixMap: Record<string, string> = {
      SHF: '.SHF', DCE: '.DCE', ZCE: '.ZCE',
      INE: '.INE', GFEX: '.GFEX', CFX: '.CFX',
    }
    const suffix = suffixMap[filters.value.exchange]
    if (suffix) arr = arr.filter((x) => x.full_symbol.endsWith(suffix))
  }
  if (filters.value.direction) {
    arr = arr.filter((x) => x.direction === filters.value.direction)
  }
  if (filters.value.dateRange && filters.value.dateRange.length === 2) {
    const [start, end] = filters.value.dateRange
    arr = arr.filter((x) => x.trade_date >= start && x.trade_date <= end)
  }
  if (keyword.value) {
    const k = keyword.value.toLowerCase()
    arr = arr.filter((x) => x.full_symbol.toLowerCase().includes(k))
  }
  return arr
})

// 分页数据
const pagedList = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredList.value.slice(start, start + pageSize.value)
})

function computeStats() {
  const arr = filteredList.value
  stats.value = {
    total: arr.length,
    longCount: arr.filter((x) => x.direction === 'long').length,
    shortCount: arr.filter((x) => x.direction === 'short').length,
    holdCount: arr.filter((x) => x.direction === 'hold' || x.direction === 'flat').length,
  }
}

async function loadList() {
  loading.value = true
  try {
    const res = await commodityApi.getRecentReports(50)
    const body = (res as any)?.data
    const reports: RecentReportItem[] = body?.reports || []
    list.value = reports.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    computeStats()
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
    list.value = []
  } finally {
    loading.value = false
  }
}

async function viewReport(row: RecentReportItem) {
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

function goToCommodityAnalysis() {
  router.push('/commodity/analysis')
}

// 筛选操作
function applyFilters() {
  currentPage.value = 1
  computeStats()
}
function resetFilters() {
  filters.value = { exchange: '', direction: '', dateRange: [] }
  currentPage.value = 1
  computeStats()
}
const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
}
const handleCurrentChange = (page: number) => {
  currentPage.value = page
}

onMounted(() => {
  loadList()
})
</script>

<style scoped lang="scss">
.commodity-task-center {
  .page-header { margin-bottom: 24px; }
  .page-title { display:flex; align-items:center; gap:8px; font-size:24px; font-weight:600; margin:0 0 8px 0; }
  .page-description { color: var(--el-text-color-regular); margin:0; }
  .filter-card { margin-bottom: 16px; }
  .list-header { display:flex; justify-content: space-between; align-items: center; margin-bottom: 12px; gap:8px; }
  .pagination-wrapper { display:flex; justify-content:center; margin-top: 16px; }
  .stat { text-align: center; padding: 8px 0;
    .value { font-size: 24px; font-weight: 600; color: var(--el-color-primary); }
    .label { font-size: 13px; color: var(--el-text-color-secondary); margin-top: 4px; }
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
