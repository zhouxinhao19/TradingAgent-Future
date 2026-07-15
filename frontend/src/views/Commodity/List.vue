<template>
  <div class="commodity-list">
    <!-- 顶部 -->
    <el-card class="header-card" shadow="never">
      <div class="header-inner">
        <div>
          <h2 class="title">大宗商品列表</h2>
          <p class="subtitle">
            支持沪/大/郑/上能/广/中金 6 大期交所 · {{ store.varieties.length || '—' }} 个品种
          </p>
        </div>
        <div class="header-actions">
          <el-button :loading="store.loading('varieties')" @click="reload">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 筛选 -->
    <el-card class="filter-card" shadow="never">
      <el-form inline :model="filters">
        <el-form-item label="交易所">
          <el-select v-model="filters.exchange" placeholder="全部交易所" clearable style="width: 180px">
            <el-option v-for="e in store.exchanges" :key="e.code" :label="e.name" :value="e.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="品类">
          <el-select v-model="filters.category" placeholder="全部品类" clearable style="width: 140px">
            <el-option v-for="c in store.categories" :key="c.code" :label="c.name" :value="c.code" />
          </el-select>
        </el-form-item>
        <el-form-item label="品种代码">
          <el-input v-model="filters.keyword" placeholder="如 CU / AU / RB" clearable style="width: 200px" />
        </el-form-item>
        <el-form-item>
          <el-button @click="reload" type="primary" :loading="store.loading('varieties')">
            <el-icon><Search /></el-icon> 查询
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 表格 -->
    <el-card class="table-card" shadow="never" v-loading="store.loading('varieties')">
      <el-alert
        v-if="store.errorMsg('varieties')"
        type="error"
        :title="store.errorMsg('varieties')"
        :closable="false"
        show-icon
      />

      <el-table
        v-else
        :data="filteredVarieties"
        stripe
        border
        height="100%"
        empty-text="暂无品种数据"
        @row-click="onRowClick"
        style="cursor: pointer"
      >
        <el-table-column prop="symbol" label="品种代码" width="100" sortable />
        <el-table-column prop="name_cn" label="中文名" min-width="140" sortable />
        <el-table-column prop="exchange" label="交易所" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="exchangeTagType(row.exchange)">{{ row.exchange }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="category" label="品类" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">{{ categoryName(row.category) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="unit" label="单位" width="80" />
        <el-table-column prop="contract_size" label="合约乘数" width="100" align="right">
          <template #default="{ row }">{{ row.contract_size || '-' }}</template>
        </el-table-column>
        <el-table-column prop="tick_size" label="最小变动" width="100" align="right">
          <template #default="{ row }">{{ row.tick_size || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button text type="primary" @click.stop="goDetail(row)">
              <el-icon><View /></el-icon> 详情
            </el-button>
            <el-button text type="success" @click.stop="quickQuote(row)">
              <el-icon><DataLine /></el-icon> 行情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <p class="footer-tip">
        💡 点击行或"详情"按钮进入主力连续合约详情页 · 默认使用最新主力连续代码(如 CU0.SHF / AU0.SHF / RB0.SHF / SC0.INE)
      </p>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Refresh, Search, View, DataLine } from '@element-plus/icons-vue'
import { useCommodityStore } from '@/stores/commodity'
import type { VarietyItem } from '@/api/commodity'

const router = useRouter()
const store = useCommodityStore()

const filters = ref({
  exchange: '' as string,
  category: '' as string,
  keyword: '' as string,
})

const filteredVarieties = computed<VarietyItem[]>(() => {
  const kw = filters.value.keyword.trim().toUpperCase()
  return store.varieties.filter((v) => {
    if (filters.value.exchange && v.exchange !== filters.value.exchange) return false
    if (filters.value.category && v.category !== filters.value.category) return false
    if (kw && !v.symbol.toUpperCase().includes(kw) && !(v.name_cn || '').includes(kw)) return false
    return true
  })
})

onMounted(async () => {
  await Promise.all([store.loadDictionaries(), store.loadVarieties()])
})

async function reload() {
  const params: { exchange?: string; category?: string } = {}
  if (filters.value.exchange) params.exchange = filters.value.exchange
  if (filters.value.category) params.category = filters.value.category
  await store.loadVarieties(params, true)
}

const EXCHANGE_SUFFIX: Record<string, string> = {
  SHFE: 'SHF',
  CZCE: 'CZC',
  DCE: 'DCE',
  INE: 'INE',
  GFEX: 'GFEX',
  CFFEX: 'CFFEX',
}

function buildContinuousSymbol(row: VarietyItem): string {
  const symbol = row.symbol.trim().toUpperCase()
  const exchange = row.exchange.trim().toUpperCase()
  const suffix = EXCHANGE_SUFFIX[exchange] || exchange
  return `${symbol}0.${suffix}`
}

function goDetail(row: VarietyItem) {
  router.push({
    name: 'CommodityDetail',
    params: { fullSymbol: buildContinuousSymbol(row) },
    query: { variety: row.symbol },
  })
}

function onRowClick(row: VarietyItem) {
  goDetail(row)
}

async function quickQuote(row: VarietyItem) {
  router.push({
    name: 'CommodityDetail',
    params: { fullSymbol: buildContinuousSymbol(row) },
    query: { variety: row.symbol, tab: 'quotes' },
  })
}

function exchangeTagType(code: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    SHFE: 'primary', DCE: 'success', CZCE: 'warning', INE: 'info', GFEX: 'danger', CFFEX: 'info',
  }
  return map[code] || 'info'
}

function categoryName(code: string): string {
  return store.categories.find((c) => c.code === code)?.name || code
}
</script>

<style scoped>
.commodity-list {
  padding: 16px;
}
.header-card { margin-bottom: 12px; }
.header-inner {
  display: flex; align-items: center; justify-content: space-between;
}
.title { margin: 0; font-size: 20px; color: var(--el-text-color-primary); }
.subtitle { margin: 4px 0 0; color: var(--el-text-color-secondary); font-size: 13px; }
.filter-card { margin-bottom: 12px; }
.table-card { min-height: 600px; }
.footer-tip { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
</style>
