<template>
  <div class="commodity-task-center">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        任务中心
      </h1>
      <p class="page-description">查看所有大宗商品品种的分析任务（含提交 → 执行 → 完成/失败）</p>
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
        <el-form-item label="状态">
          <el-select v-model="filters.status" clearable placeholder="全部" style="width: 120px" @change="applyFilters">
            <el-option label="全部" value="" />
            <el-option label="进行中" value="processing" />
            <el-option label="已完成" value="completed" />
            <el-option label="失败" value="failed" />
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

    <!-- 统计卡片:按任务状态分类 -->
    <el-row :gutter="16" style="margin-top: 12px">
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-clickable" @click="filterByStatus('')">
          <div class="stat"><div class="value">{{ stats.total }}</div><div class="label">总任务</div></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-clickable" @click="filterByStatus('processing')">
          <div class="stat"><div class="value processing-color">{{ stats.processing }}</div><div class="label">进行中</div></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-clickable" @click="filterByStatus('completed')">
          <div class="stat"><div class="value completed-color">{{ stats.completed }}</div><div class="label">已完成</div></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-clickable" @click="filterByStatus('failed')">
          <div class="stat"><div class="value failed-color">{{ stats.failed }}</div><div class="label">失败</div></div>
        </el-card>
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
          <el-tag v-if="hasProcessing" type="info" size="small">后台分析中,自动刷新</el-tag>
        </div>
      </div>

      <el-table :data="pagedList" v-loading="loading" style="width: 100%">
        <el-table-column label="合约代码" width="180">
          <template #default="{ row }">
            {{ row.full_symbol }}
            <el-tag v-if="row.variety_name" size="small" type="info" effect="plain" style="margin-left: 6px">
              {{ row.variety_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="任务状态" width="120">
          <template #default="{ row }">
            <el-tag :type="statusTagType(row.status)" size="small">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="trade_date" label="交易日期" width="120" />
        <el-table-column label="提交时间" min-width="170">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="完成时间" min-width="170">
          <template #default="{ row }">
            <span v-if="row.completed_at">{{ formatTime(row.completed_at) }}</span>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="viewReport(row)"
            >查看报告</el-button>
            <el-tooltip
              v-else-if="row.status === 'failed' && row.error_message"
              :content="row.error_message"
              placement="top"
            >
              <el-tag type="danger" size="small" effect="plain">失败原因</el-tag>
            </el-tooltip>
            <el-tag
              v-else-if="row.status === 'processing'"
              type="info"
              size="small"
              effect="plain"
            >分析中…</el-tag>
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

    <!-- 报告详情抽屉(仅 completed 任务可看) -->
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
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { List, Refresh, TrendCharts } from '@element-plus/icons-vue'
import { commodityApi, type CommodityTaskItem, type TaskStatus } from '@/api/commodity'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()

// 状态
const loading = ref(false)
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(50)
const list = ref<CommodityTaskItem[]>([])

// 筛选
const filters = ref<{
  exchange: string
  status: TaskStatus | ''
  dateRange: string[]
}>({
  exchange: '',
  status: '',
  dateRange: [],
})

// 统计(全部状态计数,在 applyFilters / loadList 后刷新)
const stats = ref({ total: 0, processing: 0, completed: 0, failed: 0 })
const allTasks = ref<CommodityTaskItem[]>([]) // 客户端筛选前的全集(做统计用)

// 报告详情抽屉
const detailDrawerVisible = ref(false)
const detailData = ref<Record<string, any> | null>(null)

// 自动轮询:列表里有 processing 状态的任务时每 5s 刷新一次
let pollingTimer: ReturnType<typeof setInterval> | null = null
const POLLING_INTERVAL_MS = 5000

const hasProcessing = computed(() => list.value.some((t) => t.status === 'processing'))

// 任务状态映射
function statusLabel(status: TaskStatus | string): string {
  const map: Record<string, string> = {
    processing: '进行中',
    completed: '已完成',
    failed: '失败',
  }
  return map[status] || status
}
function statusTagType(status: string): 'success' | 'info' | 'warning' | 'danger' {
  const map: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    processing: 'info',
    completed: 'success',
    failed: 'danger',
  }
  return map[status] ?? 'info'
}

function sectionTitle(key: string): string {
  const map: Record<string, string> = {
    market_report: '技术分析',
    fundamentals_report: '基本面分析',
    sentiment_report: '持仓情绪',
    news_report: '新闻分析',
    investment_plan: '投资计划',
    trader_investment_plan: '交易员计划',
    final_trade_decision: '最终交易决策',
    final_decision: 'CIO 决策',
  }
  return map[key] || key
}

const formatTime = (t: string) => (t ? formatDateTime(t) : '-')

// 客户端过滤(按交易所 + 日期 + 关键词)
const filteredList = computed(() => {
  let arr = allTasks.value

  if (filters.value.exchange) {
    const suffixMap: Record<string, string> = {
      SHF: '.SHF', DCE: '.DCE', ZCE: '.ZCE',
      INE: '.INE', GFEX: '.GFEX', CFX: '.CFX',
    }
    const suffix = suffixMap[filters.value.exchange]
    if (suffix) arr = arr.filter((x) => x.full_symbol.endsWith(suffix))
  }
  if (filters.value.status) {
    arr = arr.filter((x) => x.status === filters.value.status)
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

// 列表显示 = 过滤后的分页(映射为 list.value,pollinwatch)
const pagedList = computed(() => {
  const start = (currentPage.value - 1) * pageSize.value
  return filteredList.value.slice(start, start + pageSize.value)
})

function computeStats() {
  const arr = allTasks.value
  stats.value = {
    total: arr.length,
    processing: arr.filter((x) => x.status === 'processing').length,
    completed: arr.filter((x) => x.status === 'completed').length,
    failed: arr.filter((x) => x.status === 'failed').length,
  }
}

async function loadList(opts: { silent?: boolean } = {}) {
  if (!opts.silent) loading.value = true
  try {
    const res = await commodityApi.getTaskList({ limit: 100 })
    const body = (res as any)?.data
    const tasks: CommodityTaskItem[] = body?.tasks || []
    allTasks.value = tasks.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )
    // list = 当前分页(用于表格渲染)
    list.value = [...allTasks.value]
    computeStats()
    ensurePolling()
  } catch (e: any) {
    if (!opts.silent) ElMessage.error(e?.message || '加载失败')
    allTasks.value = []
    list.value = []
  } finally {
    loading.value = false
  }
}

function ensurePolling() {
  if (hasProcessing.value && !pollingTimer) {
    pollingTimer = setInterval(() => loadList({ silent: true }), POLLING_INTERVAL_MS)
  } else if (!hasProcessing.value && pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

async function viewReport(row: CommodityTaskItem) {
  if (row.status !== 'completed' || !row.report_id) {
    ElMessage.warning('该任务尚未生成报告')
    return
  }
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

// 点击统计卡片 → 自动设置状态筛选
function filterByStatus(status: TaskStatus | '') {
  filters.value.status = status
  currentPage.value = 1
}

// 筛选操作
function applyFilters() {
  currentPage.value = 1
}
function resetFilters() {
  filters.value = { exchange: '', status: '', dateRange: [] }
  currentPage.value = 1
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

onUnmounted(() => {
  if (pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
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
  .stat-card-clickable { cursor: pointer; transition: box-shadow .2s; }
  .stat-card-clickable:hover { box-shadow: 0 2px 12px rgba(0,0,0,.1); }
  .stat { text-align: center; padding: 8px 0;
    .value { font-size: 24px; font-weight: 600; color: var(--el-color-primary); }
    .processing-color { color: #909399; }
    .completed-color { color: var(--el-color-success); }
    .failed-color { color: var(--el-color-danger); }
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
  .muted { color: var(--el-text-color-placeholder); }
}
</style>
