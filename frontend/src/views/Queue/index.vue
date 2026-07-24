<template>
  <div class="queue-management">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><List /></el-icon>
        任务中心
      </h1>
      <p class="page-description">
        实时监控和管理分析任务状态（商品分析）
      </p>
    </div>

    <!-- 队列任务列表 -->
    <el-card class="queue-list-card" header="任务队列">
      <template #header>
        <div class="card-header">
          <span>任务队列</span>
          <div class="header-actions">
            <el-button type="text" @click="refreshQueue">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
            <el-button type="text" disabled>
              <el-icon><Delete /></el-icon>
              清理已完成（暂不可用）
            </el-button>
          </div>
        </div>
      </template>

      <el-table :data="queueTasks" v-loading="loading" style="width: 100%">
        <el-table-column label="任务ID" width="220">
          <template #default="{ row }">
            <el-link type="primary" @click="viewTaskDetail(row)">
              {{ row.task_id?.substring(0, 12) || '-' }}...
            </el-link>
          </template>
        </el-table-column>

        <el-table-column prop="symbol" label="品种代码" width="140" />
        <el-table-column prop="name" label="品种名称" width="100" />

        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="progress" label="进度" width="150">
          <template #default="{ row }">
            <el-progress
              :percentage="row.progress"
              :status="getProgressStatus(row.status)"
              :stroke-width="8"
            />
          </template>
        </el-table-column>

        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>

        <el-table-column label="操作" width="140" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="viewResult(row)"
            >
              查看结果
            </el-button>
            <el-button type="text" size="small" @click="viewTaskDetail(row)">
              详情
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
          :total="totalTasks"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 查看结果弹窗 -->
    <el-dialog v-model="resultDialogVisible" title="任务结果" width="60%">
      <div v-if="resultData">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="品种代码">{{ resultData.symbol || resultData.full_symbol || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ getStatusText(resultData.status || currentTaskRow?.status || '') }}</el-descriptions-item>
        </el-descriptions>
        <div style="margin-top: 16px;" v-if="resultData.error_message">
          <h4>错误信息</h4>
          <el-alert :title="resultData.error_message" type="error" show-icon />
        </div>
      </div>
      <template #footer>
        <el-button @click="resultDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- 任务详情弹窗 -->
    <el-dialog v-model="detailDialogVisible" title="任务详情" width="50%">
      <div v-if="detailData">
        <el-descriptions :column="2" border>
          <el-descriptions-item label="任务ID">{{ detailData.task_id || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ getStatusText(detailData.status || '') }}</el-descriptions-item>
          <el-descriptions-item label="合约">{{ detailData.full_symbol || '-' }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(detailData.created_at || '') }}</el-descriptions-item>
          <el-descriptions-item v-if="detailData.completed_at" label="完成时间">{{ formatTime(detailData.completed_at) }}</el-descriptions-item>
          <el-descriptions-item v-if="detailData.error_message" label="错误信息"><span style="color:var(--el-color-danger)">{{ detailData.error_message }}</span></el-descriptions-item>
        </el-descriptions>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'

import { commodityApi, type CommodityTaskItem } from '@/api/commodity'
import { ElMessage } from 'element-plus'
import { useRouter } from 'vue-router'

import {
  List,
  Refresh,
  Delete
} from '@element-plus/icons-vue'

const router = useRouter()

// 响应式数据
const loading = ref(false)
const currentPage = ref(1)
const pageSize = ref(20)
const totalTasks = ref(0)

const queueTasks = ref<any[]>([])

// 当前行引用（用于弹窗状态兜底）
const currentTaskRow = ref<any | null>(null)

// 结果/详情弹窗状态
const resultDialogVisible = ref(false)
const resultData = ref<any | null>(null)
const detailDialogVisible = ref(false)
const detailData = ref<any | null>(null)

const getStatusType = (status: string): 'success' | 'info' | 'warning' | 'danger' => {
  const statusMap: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    processing: 'warning',
    completed: 'success',
    failed: 'danger',
  }
  return statusMap[status] ?? 'info'
}

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    processing: '进行中',
    completed: '已完成',
    failed: '失败',
  }
  return statusMap[status] || status
}

const getProgressStatus = (status: string) => {
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'exception'
  return undefined
}

const formatTime = (time: string) => {
  return time ? new Date(time).toLocaleString('zh-CN') : '-'
}

const refreshQueue = async () => {
  loading.value = true
  try {
    const res = await commodityApi.getTaskList({
      limit: pageSize.value,
      offset: (currentPage.value - 1) * pageSize.value,
    })

    const body = (res as any)?.data || {}
    const tasksRaw: CommodityTaskItem[] = body.tasks || []

    const tasks = tasksRaw.map((t: CommodityTaskItem) => ({
      task_id: t.task_id,
      symbol: t.full_symbol,
      name: t.variety_name || '',
      status: t.status,
      progress: t.status === 'completed' ? 100 : (t.status === 'processing' ? 50 : 0),
      priority: 0,
      created_at: t.created_at,
    }))

    queueTasks.value = tasks
    totalTasks.value = body.total ?? tasks.length
    ElMessage.success('队列数据已刷新')
  } catch (error) {
    ElMessage.error('刷新失败')
  } finally {
    loading.value = false
  }
}

const viewResult = async (task: any) => {
  try {
    currentTaskRow.value = task
    // 如果任务失败，显示错误信息
    if (task.status === 'failed') {
      resultData.value = { status: 'failed', error_message: task.error_message || '分析失败，请查看详情' }
      resultDialogVisible.value = true
      return
    }
    // 如果已完成，尝试获取报告详情
    if (task.report_id) {
      const res = await commodityApi.getReportDetail(task.report_id)
      resultData.value = { ...((res as any)?.data || {}), status: 'completed' }
      resultDialogVisible.value = true
    } else {
      ElMessage.warning('该任务无关联报告')
    }
  } catch (e) {
    ElMessage.error('获取结果失败')
  }
}

const viewTaskDetail = async (task: any) => {
  try {
    currentTaskRow.value = task
    const res = await commodityApi.getTaskStatus(task.task_id)
    const data = (res as any)?.data
    if (data) {
      detailData.value = data
      detailDialogVisible.value = true
    } else {
      ElMessage.warning('暂无详情数据')
    }
  } catch (e) {
    ElMessage.error('获取任务详情失败')
  }
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
}

// 监听分页变化，自动刷新
watch([currentPage, pageSize], () => {
  refreshQueue()
})

onMounted(async () => {
  await refreshQueue()
})
</script>

<style lang="scss" scoped>
.queue-management {
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

  .queue-list-card {
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;

      .header-actions {
        display: flex;
        gap: 8px;
      }
    }

    .pagination-wrapper {
      display: flex;
      justify-content: center;
      margin-top: 24px;
    }
  }
}
</style>
