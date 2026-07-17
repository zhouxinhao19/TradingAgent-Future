<template>
  <div class="commodity-task-center">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        任务中心
      </h1>
      <p class="page-description">查看所有大宗商品品种的分析任务（含提交 → 执行 → 完成/失败）</p>
    </div>

    <!-- 标签页 -->
    <el-card class="tabs-card" shadow="never">
      <el-tabs v-model="activeTab" @tab-change="onTabChange">
        <el-tab-pane label="进行中" name="processing" />
        <el-tab-pane label="已完成" name="completed" />
        <el-tab-pane label="失败" name="failed" />
        <el-tab-pane label="全部" name="" />
      </el-tabs>
    </el-card>

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
        <el-card shadow="never" class="stat-card-clickable" @click="switchTab('')">
          <div class="stat"><div class="value">{{ stats.total }}</div><div class="label">总任务</div></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-clickable" @click="switchTab('processing')">
          <div class="stat"><div class="value processing-color">{{ stats.processing }}</div><div class="label">进行中</div></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-clickable" @click="switchTab('completed')">
          <div class="stat"><div class="value completed-color">{{ stats.completed }}</div><div class="label">已完成</div></div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="never" class="stat-card-clickable" @click="switchTab('failed')">
          <div class="stat"><div class="value failed-color">{{ stats.failed }}</div><div class="label">失败</div></div>
        </el-card>
      </el-col>
    </el-row>

    <el-card class="list-card" shadow="never">
      <div class="list-header">
        <div class="left">
          <el-input v-model="keyword" placeholder="搜索合约代码" clearable style="width: 220px" @input="applyFilters" />
          <el-button @click="loadList" :loading="loading">
            <el-icon><Refresh /></el-icon>
            刷新
          </el-button>
          <el-button type="primary" @click="goToCommodityAnalysis">
            <el-icon><TrendCharts /></el-icon>
            新建分析
          </el-button>
          <el-tag v-if="hasProcessing" type="info" size="small">后台分析中，自动刷新</el-tag>
        </div>
      </div>

      <el-table :data="list" v-loading="loading" style="width: 100%">
        <el-table-column label="合约代码" width="180">
          <template #default="{ row }">
            {{ row.full_symbol }}
            <el-tag v-if="row.variety_name" size="small" type="info" effect="plain" style="margin-left: 6px">
              {{ row.variety_name }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态/进度" width="180">
          <template #default="{ row }">
            <div style="display: flex; align-items: center; gap: 8px">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
              <el-progress
                v-if="row.status === 'processing'"
                :percentage="row.progress || 0"
                :width="28"
                type="circle"
                :stroke-width="4"
              />
              <el-progress
                v-else-if="row.status === 'completed'"
                :percentage="100"
                :width="28"
                type="circle"
                :stroke-width="4"
                status="success"
              />
              <el-progress
                v-else-if="row.status === 'failed'"
                :percentage="0"
                :width="28"
                type="circle"
                :stroke-width="4"
                status="exception"
              />
            </div>
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
        <el-table-column label="操作" width="300" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="viewReport(row)"
            >查看报告</el-button>
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="viewResult(row)"
            >查看结果</el-button>
            <el-tooltip
              v-if="row.status === 'failed' && row.error_message"
              :content="row.error_message"
              placement="top"
            >
              <el-tag type="danger" size="small" effect="plain">失败原因</el-tag>
            </el-tooltip>
            <el-button
              v-if="row.status === 'failed'"
              type="text"
              size="small"
              @click="retryTask(row)"
            >重试</el-button>
            <el-button
              v-if="row.status === 'processing'"
              type="text"
              size="small"
              style="color: var(--el-color-warning)"
              @click="markAsFailed(row)"
            >标记失败</el-button>
            <el-button
              type="text"
              size="small"
              style="margin-left: 4px; color: var(--el-color-danger)"
              @click="deleteTask(row)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="total"
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
            {{ sectionTitle(key) }}
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

    <!-- 结果详情弹窗 -->
    <el-dialog v-model="resultDialogVisible" title="分析结果" width="70%" top="5vh">
      <div v-if="resultData" class="result-detail">
        <div v-for="(value, key) in resultData" :key="key" class="detail-section">
          <h4 v-if="typeof value === 'string' && value.length > 20" class="section-title">
            {{ sectionTitle(key) }}
          </h4>
          <div v-if="typeof value === 'string' && value.length > 20" class="section-content">
            {{ value }}
          </div>
        </div>
      </div>
      <div v-else><el-empty description="加载中..." /></div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { List, Refresh, TrendCharts } from '@element-plus/icons-vue'
import { commodityApi, type CommodityTaskItem, type TaskStatus } from '@/api/commodity'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()

// 状态
const loading = ref(false)
const keyword = ref('')
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)
const list = ref<CommodityTaskItem[]>([])

// 标签页
const activeTab = ref<string>('processing')

function switchTab(tab: string) {
  activeTab.value = tab
  currentPage.value = 1
  loadList()
}

// 筛选
const filters = ref<{
  exchange: string
  dateRange: string[]
}>({
  exchange: '',
  dateRange: [],
})

// 统计（通过额外请求获取全部计数,不再依赖全量数据集）
const stats = ref({ total: 0, processing: 0, completed: 0, failed: 0 })

// 报告详情抽屉
const detailDrawerVisible = ref(false)
const detailData = ref<Record<string, any> | null>(null)

// 结果弹窗
const resultDialogVisible = ref(false)
const resultData = ref<Record<string, any> | null>(null)

// 自动轮询
let pollingTimer: ReturnType<typeof setInterval> | null = null
const POLLING_INTERVAL_MS = 5000

const hasProcessing = computed(() => list.value.some((t) => t.status === 'processing'))

// ---- WebSocket 实时进度 ----
let wsConnections: Map<string, WebSocket> = new Map()

function connectTaskWebSocket(taskId: string) {
  if (wsConnections.has(taskId)) return
  try {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const wsUrl = `${wsProtocol}//${host}/api/commodity/ws/task/${taskId}`
    const ws = new WebSocket(wsUrl)

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'progress_update') {
          const idx = list.value.findIndex(t => t.task_id === taskId)
          if (idx >= 0) {
            list.value[idx] = { ...list.value[idx], progress: msg.progress, progress_message: msg.message }
          }
        }
      } catch { /* ignore */ }
    }
    ws.onclose = () => { wsConnections.delete(taskId) }
    ws.onerror = () => { wsConnections.delete(taskId) }
    wsConnections.set(taskId, ws)
  } catch { /* ignore */ }
}

function disconnectAllWebSockets() {
  wsConnections.forEach(ws => { try { ws.close() } catch { /* ignore */ } })
  wsConnections.clear()
}

// ---- 操作 ----
async function deleteTask(row: CommodityTaskItem) {
  try {
    await ElMessageBox.confirm(
      `确定要删除 ${row.full_symbol} 的任务记录吗？${row.status === 'completed' ? '关联的报告文件也会被删除。' : ''}`,
      '确认删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
    await commodityApi.deleteTask(row.task_id)
    ElMessage.success('已删除')
    await loadList()
  } catch { /* ignore */ }
}

async function markAsFailed(row: CommodityTaskItem) {
  try {
    await ElMessageBox.confirm(
      `确定要将 ${row.full_symbol} 的任务标记为失败吗？`,
      '确认操作',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'warning' },
    )
    await commodityApi.markTaskAsFailed(row.task_id)
    ElMessage.success('已标记为失败')
    await loadList()
  } catch { /* ignore */ }
}

async function viewResult(row: CommodityTaskItem) {
  try {
    const res = await commodityApi.getTaskResult(row.task_id)
    resultData.value = (res as any)?.data || null
    resultDialogVisible.value = true
  } catch (e: any) {
    ElMessage.error(e?.message || '获取结果失败')
  }
}

function retryTask(row: CommodityTaskItem) {
  router.push({ path: '/commodity/analysis', query: { symbol: row.full_symbol } })
}

// ---- 状态映射 ----
function statusLabel(status: TaskStatus | string): string {
  const map: Record<string, string> = { processing: '进行中', completed: '已完成', failed: '失败' }
  return map[status] || status
}
function statusTagType(status: string): 'success' | 'info' | 'warning' | 'danger' {
  const map: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    processing: 'info', completed: 'success', failed: 'danger',
  }
  return map[status] ?? 'info'
}
function sectionTitle(key: string): string {
  const map: Record<string, string> = {
    market_report: '技术分析', fundamentals_report: '基本面分析',
    sentiment_report: '持仓情绪', news_report: '新闻分析',
    investment_plan: '投资计划', final_decision: '投研总监决策',
  }
  return map[key] || key
}

const formatTime = (t: string) => (t ? formatDateTime(t) : '-')

// ---- 数据加载（服务端分页） ----
async function loadStats() {
  try {
    const [allRes, procRes, doneRes, failRes] = await Promise.all([
      commodityApi.getTaskList({ limit: 1 }),
      commodityApi.getTaskList({ status: 'processing', limit: 1 }),
      commodityApi.getTaskList({ status: 'completed', limit: 1 }),
      commodityApi.getTaskList({ status: 'failed', limit: 1 }),
    ])
    stats.value = {
      total: ((allRes as any)?.data?.total) ?? 0,
      processing: ((procRes as any)?.data?.total) ?? 0,
      completed: ((doneRes as any)?.data?.total) ?? 0,
      failed: ((failRes as any)?.data?.total) ?? 0,
    }
  } catch { /* stale stats ok */ }
}

async function loadList() {
  loading.value = true
  try {
    const statusParam = activeTab.value || undefined
    const params: Record<string, any> = {
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
    }
    if (statusParam) params.status = statusParam

    const res = await commodityApi.getTaskList(params)
    const body = (res as any)?.data
    const tasks: CommodityTaskItem[] = body?.tasks || []
    total.value = body?.total ?? tasks.length
    list.value = tasks

    // WebSocket: 为 processing 任务建立连接
    tasks.forEach(t => {
      if (t.status === 'processing') connectTaskWebSocket(t.task_id)
    })

    ensurePolling()
    await loadStats()
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
    list.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

function ensurePolling() {
  if (hasProcessing.value && !pollingTimer) {
    pollingTimer = setInterval(() => loadList(), POLLING_INTERVAL_MS)
  } else if (!hasProcessing.value && pollingTimer) {
    clearInterval(pollingTimer)
    pollingTimer = null
  }
}

// ---- 报告查看 ----
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

// ---- 导航 ----
function goToCommodityAnalysis() {
  router.push('/commodity/analysis')
}

// ---- 标签页切换 ----
function onTabChange() {
  currentPage.value = 1
  loadList()
}

// ---- 筛选 ----
function applyFilters() {
  currentPage.value = 1
  loadList()
}
function resetFilters() {
  filters.value = { exchange: '', dateRange: [] }
  currentPage.value = 1
  loadList()
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  loadList()
}
const handleCurrentChange = (page: number) => {
  currentPage.value = page
  loadList()
}

onMounted(() => {
  loadList()
})

onUnmounted(() => {
  if (pollingTimer) { clearInterval(pollingTimer); pollingTimer = null }
  disconnectAllWebSockets()
})
</script>

<style scoped lang="scss">
.commodity-task-center {
  .page-header { margin-bottom: 24px; }
  .page-title { display:flex; align-items:center; gap:8px; font-size:24px; font-weight:600; margin:0 0 8px 0; }
  .page-description { color: var(--el-text-color-regular); margin:0; }
  .tabs-card { margin-bottom: 16px; }
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
  .result-detail { max-height: 70vh; overflow-y: auto; }
}
</style>
