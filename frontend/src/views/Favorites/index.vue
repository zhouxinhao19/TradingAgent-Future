<template>
  <div class="favorites-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h2>我的自选品种</h2>
      <div class="header-actions">
        <el-button type="primary" size="small" @click="goToCommodityList">
          + 添加自选
        </el-button>
        <el-button v-if="selectedIds.length > 0" type="danger" size="small" @click="handleBatchRemove">
          批量删除 ({{ selectedIds.length }})
        </el-button>
        <el-button size="small" @click="refreshList" :loading="loading">
          刷新行情
        </el-button>
      </div>
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
import { formatDateTime } from '@/utils/datetime'

const router = useRouter()
const favoritesStore = useFavoritesStore()

const selectedIds = ref<string[]>([])
const loading = computed(() => favoritesStore.loading)

const items = computed(() => favoritesStore.items)

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
  router.push(`/commodity/analysis?symbol=${row.full_symbol}`)
}

const goToCommodityList = () => {
  router.push('/commodity/list')
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
