<template>
  <el-card shadow="never" class="recent-analyses-card" :class="{ 'is-compact': compact }">
    <template #header>
      <div class="card-header">
        <span><b>最近分析</b></span>
        <el-button text size="small" @click="goToTaskCenter">
          转到任务中心 <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </template>

    <el-table
      v-if="analyses.length"
      :data="analyses"
      style="width: 100%"
      size="small"
      :fit="!compact"
    >
      <el-table-column label="品种代码" :min-width="compact ? 60 : 180">
        <template #default="{ row }">
          <span style="font-weight: 600">{{ extractVariety(row.full_symbol) }}</span>
          <el-tag
            v-if="!compact && row.variety_name"
            size="small"
            type="info"
            effect="plain"
            style="margin-left: 6px"
          >
            {{ row.variety_name }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        v-if="!compact"
        prop="trade_date"
        label="交易日期"
        width="110"
      />
      <el-table-column label="状态" :min-width="compact ? 70 : 100">
        <template #default="{ row }">
          <el-tag :type="getStatusType(row.status)" size="small">
            {{ getStatusText(row.status) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column
        label="提交时间"
        :min-width="compact ? 110 : 170"
      >
        <template #default="{ row }">
          <span :style="compact ? 'font-size: 12px; color: #909399' : ''">
            {{ formatTime(row.created_at) }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else description="暂无分析记录" :image-size="50" />
  </el-card>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { commodityApi, type CommodityTaskItem } from '@/api/commodity'
import { formatDateTime } from '@/utils/datetime'

const props = withDefaults(
  defineProps<{ compact?: boolean; limit?: number }>(),
  { compact: false, limit: 10 },
)

const router = useRouter()
const analyses = ref<CommodityTaskItem[]>([])
const loading = ref(false)
let pollTimer: ReturnType<typeof setInterval> | null = null

async function load() {
  loading.value = true
  try {
    const res = await commodityApi.getTaskList({ limit: props.limit, offset: 0 })
    const body: any = (res as any)?.data || {}
    analyses.value = body.tasks || []
  } catch {
    analyses.value = []
  } finally {
    loading.value = false
  }
}

function startPoll() {
  stopPoll()
  pollTimer = setInterval(load, 30000)
}
function stopPoll() {
  if (pollTimer !== null) { clearInterval(pollTimer); pollTimer = null }
}

function goToTaskCenter() {
  router.push('/tasks')
}

function extractVariety(fullSymbol: string): string {
  if (!fullSymbol) return ''
  return fullSymbol.split('.')[0]?.replace(/0$/, '') || fullSymbol
}

function getStatusType(status: string): 'success' | 'info' | 'warning' | 'danger' {
  const map: Record<string, 'success' | 'info' | 'warning' | 'danger'> = {
    pending: 'info',
    processing: 'warning',
    running: 'warning',
    completed: 'success',
    failed: 'danger',
    cancelled: 'info',
  }
  return map[status] || 'info'
}

function getStatusText(status: string): string {
  const map: Record<string, string> = {
    pending: '等待中',
    processing: '处理中',
    running: '处理中',
    completed: '已完成',
    failed: '失败',
    cancelled: '已取消',
  }
  return map[status] || status
}

function formatTime(time: string): string {
  return formatDateTime(time)
}

onMounted(() => {
  load()
  startPoll()
})

onUnmounted(() => {
  stopPoll()
})

defineExpose({ reload: load })
</script>

<style scoped>
.recent-analyses-card :deep(.el-card__body) {
  padding: 0;
}
.recent-analyses-card :deep(.el-table__empty-text) {
  padding: 20px 0;
}
/* compact 模式：去掉 el-table 默认的左侧 padding，让内容贴近卡片边缘 */
.recent-analyses-card.is-compact :deep(.el-table .cell) {
  padding: 6px 4px;
}
.recent-analyses-card.is-compact :deep(.el-table th:first-child .cell),
.recent-analyses-card.is-compact :deep(.el-table td:first-child .cell) {
  padding-left: 12px;
}
.recent-analyses-card.is-compact :deep(.el-card__header) {
  padding: 8px 12px;
}
.recent-analyses-card.is-compact :deep(.el-card__body) {
  padding: 0;
}
</style>
