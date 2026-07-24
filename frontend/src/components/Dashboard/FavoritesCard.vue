<template>
  <el-card shadow="never" class="favorites-card" :class="{ 'is-compact': compact }">
    <template #header>
      <div class="card-header">
        <span><b>我的自选品种</b></span>
        <el-button text size="small" @click="goToFavorites">
          查看全部 <el-icon><ArrowRight /></el-icon>
        </el-button>
      </div>
    </template>

    <div v-if="favoriteItems.length === 0" class="empty-favorites">
      <el-empty description="暂无自选品种" :image-size="60">
        <el-button v-if="compact" type="primary" size="small" @click="goToFavorites">
          添加自选品种
        </el-button>
        <p v-else class="text-secondary">在商品列表页点击"自选"按钮添加品种</p>
      </el-empty>
    </div>

    <div v-else class="favorites-list">
      <div
        v-for="item in displayItems"
        :key="item.id"
        class="favorite-item"
        @click="viewFavoriteDetail(item)"
      >
        <div class="symbol-info">
          <div class="symbol-code">
            <el-tag
              :type="item.asset_type === 'commodity' ? 'warning' : 'info'"
              size="small"
              effect="plain"
              style="margin-right: 4px"
            >
              {{ item.asset_type === 'commodity' ? '📦' : '📈' }}
            </el-tag>
            <template v-if="item.asset_type === 'commodity'">
              {{ item.commodity_name || extractCommodityCode(item.full_symbol) }}
            </template>
            <span class="symbol-name">
              <template v-if="item.asset_type === 'commodity'">{{ extractCommodityCode(item.full_symbol) }}</template>
              <template v-else>{{ item.display_name || '' }}</template>
            </span>
          </div>
        </div>
        <div class="symbol-price">
          <div class="current-price">
            {{ formatPrice(item) }}
          </div>
          <div
            v-if="getChangePercent(item) != null"
            class="change-percent"
            :class="getPriceChangeClass(getChangePercent(item)!)"
          >
            {{ formatChangePercent(getChangePercent(item)!) }}
          </div>
        </div>
      </div>
    </div>

    <div v-if="favoriteItems.length > maxDisplay" class="favorites-footer">
      <el-button text size="small" @click="goToFavorites">
        查看全部 {{ favoriteItems.length }} 个自选品种
      </el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight } from '@element-plus/icons-vue'
import { useFavoritesStore } from '@/stores/favorites'
import type { FavoriteItem } from '@/api/favorites'

const props = withDefaults(
  defineProps<{ compact?: boolean; maxDisplay?: number; loadAssetType?: 'commodity' | 'all' }>(),
  { compact: false, maxDisplay: 5, loadAssetType: 'all' },
)

const emit = defineEmits<{
  select: [item: FavoriteItem]
}>()

const router = useRouter()
const favoritesStore = useFavoritesStore()
const favoriteItems = computed(() => favoritesStore.items)

const displayItems = computed(() => favoriteItems.value.slice(0, props.maxDisplay))

function extractCommodityCode(fullSymbol?: string): string {
  return fullSymbol?.split('.')[0]?.replace(/\d+$/, '') || fullSymbol || ''
}

function formatPrice(item: FavoriteItem): string {
  const p = item.current_price ?? item.snapshot_price
  return p != null ? `¥${p}` : '--'
}

function getChangePercent(item: FavoriteItem): number | null {
  return item.change_percent != null ? Number(item.change_percent) : (item.snapshot_pct != null ? Number(item.snapshot_pct) : null)
}

function formatChangePercent(v: number): string {
  return `${v > 0 ? '+' : ''}${v.toFixed(2)}%`
}

function getPriceChangeClass(pct: number): string {
  if (pct > 0) return 'price-up'
  if (pct < 0) return 'price-down'
  return 'price-neutral'
}

function goToFavorites() {
  router.push('/favorites')
}

function viewFavoriteDetail(item: FavoriteItem) {
  if (item.full_symbol) {
    if (props.compact) {
      // compact 模式：通知父组件填入表单，不跳转页面
      emit('select', item)
    } else {
      router.push(`/commodity/${item.full_symbol}`)
    }
  }
}

onMounted(async () => {
  await favoritesStore.loadFavorites(props.loadAssetType === 'all' ? undefined : props.loadAssetType)
})

defineExpose({ reload: () => favoritesStore.loadFavorites(props.loadAssetType === 'all' ? undefined : props.loadAssetType) })
</script>

<style scoped>
.favorites-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.favorites-card .empty-favorites {
  text-align: center;
  padding: 20px 0;
}
.favorites-card .favorites-list .favorite-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  cursor: pointer;
  transition: background-color 0.3s ease;
}
.favorites-card .favorites-list .favorite-item:hover {
  background-color: var(--el-fill-color-lighter);
  margin: 0 -16px;
  padding: 12px 16px;
  border-radius: 6px;
}
.favorites-card .favorites-list .favorite-item:last-child {
  border-bottom: none;
}
.favorites-card .symbol-code {
  font-weight: 600;
  font-size: 14px;
  color: var(--el-text-color-primary);
  display: flex;
  align-items: center;
  gap: 6px;
}
.favorites-card .symbol-name {
  font-weight: 400;
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.favorites-card .symbol-price {
  text-align: right;
}
.favorites-card .current-price {
  font-weight: 600;
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.favorites-card .change-percent {
  font-size: 12px;
  margin-top: 2px;
}
.favorites-card .change-percent.price-up {
  color: #f56c6c;
}
.favorites-card .change-percent.price-down {
  color: #67c23a;
}
.favorites-card .change-percent.price-neutral {
  color: var(--el-text-color-regular);
}
.favorites-card .favorites-footer {
  text-align: center;
  padding-top: 12px;
  border-top: 1px solid var(--el-border-color-lighter);
  margin-top: 12px;
}

/* compact 模式：紧凑间距 */
.favorites-card.is-compact :deep(.el-card__header) {
  padding: 8px 12px;
}
.favorites-card.is-compact :deep(.el-card__body) {
  padding: 4px 12px;
}
.favorites-card.is-compact .favorite-item {
  padding: 8px 0;
}
.favorites-card.is-compact .favorite-item:hover {
  margin: 0;
  padding: 8px 8px;
}
.text-secondary {
  color: #909399;
  font-size: 13px;
}
</style>
