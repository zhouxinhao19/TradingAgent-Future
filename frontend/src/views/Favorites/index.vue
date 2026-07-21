<template>
  <div class="favorites-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>我的自选品种</h2>
      <div class="header-actions">
        <el-button type="primary" size="small" @click="goToCommodityList">
          + 添加自选
        </el-button>
        <el-button v-if="selectedIds.length > 0" type="primary" size="small" :loading="batchSubmitting" @click="handleBatchAnalyze">
          批量分析 ({{ selectedIds.length }})
        </el-button>
        <el-button v-if="selectedIds.length > 0" type="danger" size="small" @click="handleBatchRemove">
          批量删除 ({{ selectedIds.length }})
        </el-button>
        <el-button size="small" @click="refreshList" :loading="loading">
          刷新行情
        </el-button>
      </div>
    </div>

    <!-- 批量分析结果提示 -->
    <div v-if="batchResult" style="margin: 0 0 16px">
      <el-alert
        :title="batchResult.message"
        :type="batchResult.failed > 0 ? 'warning' : 'success'"
        :closable="true"
        show-icon
        @close="batchResult = null"
      >
        <template #default>
          <div style="margin-top: 4px; font-size: 13px">
            成功 {{ batchResult.created }}/{{ batchResult.total }}
            <el-button text size="small" @click="goToTaskCenter">查看任务中心</el-button>
          </div>
        </template>
      </el-alert>
    </div>

    <!-- 空状态 -->
    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="5" animated />
    </div>

    <div v-else-if="items.length === 0" class="empty-state">
      <el-empty description="暂无自选品种，快去商品列表添加吧" :image-size="80">
        <template #actions>
          <el-button type="primary" size="small" @click="goToCommodityList">
            去商品列表添加
          </el-button>
        </template>
      </el-empty>
    </div>

    <!-- 列表 -->
    <el-table
      v-else
      :data="items"
      style="width: 100%"
      @row-click="viewDetail"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column label="品种代码" width="100">
        <template #default="{ row }">
          <span class="symbol-text">{{ row.asset_type === 'commodity' ? (row.full_symbol?.split('.')[0]?.replace(/\d+$/, '') || row.full_symbol) : (row.stock_code || row.full_symbol) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="品种名称" min-width="140">
        <template #default="{ row }">
          {{ row.asset_type === 'commodity' ? (row.commodity_name || '-') : (row.display_name || row.stock_name || '-') }}
        </template>
      </el-table-column>
      <el-table-column label="交易所" width="100">
        <template #default="{ row }">
          <el-tag size="small" effect="plain">{{ row.exchange || '-' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="品类" width="100">
        <template #default="{ row }">
          {{ row.category || '-' }}
        </template>
      </el-table-column>
      <el-table-column label="最新价" width="120" align="right">
        <template #default="{ row }">
          <span v-if="row.current_price != null">¥{{ row.current_price }}</span>
          <span v-else-if="row.snapshot_price != null" class="snapshot-price">¥{{ row.snapshot_price }}</span>
          <span v-else class="no-price">--</span>
        </template>
      </el-table-column>
      <el-table-column label="涨跌幅" width="100" align="right">
        <template #default="{ row }">
          <span
            v-if="row.change_percent != null"
            :class="row.change_percent > 0 ? 'price-up' : row.change_percent < 0 ? 'price-down' : ''"
          >
            {{ row.change_percent > 0 ? '+' : '' }}{{ Number(row.change_percent).toFixed(2) }}%
          </span>
          <span v-else class="no-price">--</span>
        </template>
      </el-table-column>
      <el-table-column label="添加时间" width="170">
        <template #default="{ row }">
          {{ formatTime(row.added_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button text type="danger" size="small" @click.stop="handleRemove(row)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useFavoritesStore } from '@/stores/favorites'
import commodityApi from '@/api/commodity'
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()
const favoritesStore = useFavoritesStore()

const selectedIds = ref<string[]>([])
const loading = computed(() => favoritesStore.loading)

const items = computed(() => favoritesStore.items)

const batchSubmitting = ref(false)
const batchResult = ref<{
  batch_id?: string
  total: number
  created: number
  failed: number
  message: string
} | null>(null)

const formatTime = (time: string) => {
  return formatDateTime(time)
}

const onSelectionChange = (selection: any[]) => {
  selectedIds.value = selection.map((s: any) => s.id)
}

const refreshList = async () => {
  await favoritesStore.loadFavorites()
  ElMessage.success('行情已刷新')
}

const handleRemove = async (item: any) => {
  try {
    await ElMessageBox.confirm(
      `确定将 ${item.full_symbol || item.display_name} 从自选中移除吗？`,
      '确认删除'
    )
    const ok = await favoritesStore.removeFavorite(item.id)
    if (ok) {
      ElMessage.success('已删除')
    }
  } catch {
    // 取消操作
  }
}

const handleBatchRemove = async () => {
  if (selectedIds.value.length === 0) return
  try {
    await ElMessageBox.confirm(
      `确定批量删除 ${selectedIds.value.length} 个自选品种吗？`,
      '确认批量删除'
    )
    const ok = await favoritesStore.batchRemove(selectedIds.value)
    if (ok) {
      ElMessage.success(`已删除 ${selectedIds.value.length} 个品种`)
      selectedIds.value = []
    }
  } catch {
    // 取消操作
  }
}

const viewDetail = (row: any) => {
  if (row.asset_type === 'commodity' && row.full_symbol) {
    router.push(`/commodity/analysis?symbol=${row.full_symbol}`)
  } else if (row.asset_type === 'stock' && row.stock_code) {
    router.push(`/analysis/single?stock_code=${row.stock_code}`)
  }
}

const goToCommodityList = () => {
  router.push('/commodity/list')
}

const goToTaskCenter = () => {
  router.push('/tasks')
}

const handleBatchAnalyze = async () => {
  // 仅取选中行的品种全代码（商品才有 full_symbol，股票本功能暂不支持）
  const symbols = items.value
    .filter(it => selectedIds.value.includes(it.id) && it.asset_type === 'commodity' && it.full_symbol)
    .map(it => it.full_symbol as string)
  if (symbols.length === 0) {
    ElMessage.warning('请至少选择一个商品自选品种')
    return
  }
  if (selectedIds.value.length > symbols.length) {
    ElMessage.warning(`已忽略 ${selectedIds.value.length - symbols.length} 个股票项目（批量分析仅支持商品）`)
  }
  // 后端 max=50
  const limited = symbols.slice(0, 50)
  if (limited.length < symbols.length) {
    ElMessage.warning(`批量分析最多 50 个品种，超出部分已忽略`)
  }

  batchSubmitting.value = true
  batchResult.value = null
  try {
    const res = await commodityApi.submitBatchAnalysis({ symbols: limited })
    if (res?.success && res.data) {
      batchResult.value = {
        batch_id: res.data.batch_id,
        total: res.data.total,
        created: res.data.created,
        failed: res.data.failed,
        message: res.message || `批量任务已入队`,
      }
      ElMessage.success(`批量提交成功: ${res.data.created}/${res.data.total}`)
      selectedIds.value = []
    } else {
      ElMessage.error(res?.message || '批量提交失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '批量提交异常')
  } finally {
    batchSubmitting.value = false
  }
}

onMounted(async () => {
  await favoritesStore.loadFavorites()
})
</script>

<style lang="scss" scoped>
.favorites-page {
  padding: 24px;

  .page-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;

    h2 {
      margin: 0;
      font-size: 20px;
      font-weight: 600;
    }

    .header-actions {
      display: flex;
      gap: 8px;
    }
  }

  .loading-state {
    padding: 40px;
  }

  .empty-state {
    padding: 60px 0;
    text-align: center;
  }

  .symbol-text {
    font-weight: 600;
    color: var(--el-color-primary);
    cursor: pointer;
  }

  .price-up {
    color: #f56c6c;
    font-weight: 500;
  }

  .price-down {
    color: #67c23a;
    font-weight: 500;
  }

  .snapshot-price {
    color: var(--el-text-color-secondary);
  }

  .no-price {
    color: var(--el-text-color-placeholder);
  }
}
</style>
