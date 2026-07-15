<template>
  <div class="commodity-detail">
    <!-- 顶部 -->
    <el-card class="header-card" shadow="never">
      <div class="header-inner">
        <div class="title-area" v-if="store.info">
          <h2 class="code">{{ store.info.full_symbol }}</h2>
          <span class="name">{{ store.info.name }}</span>
          <el-tag size="small" :type="exchangeTagType(store.info.exchange)">{{ store.info.exchange }}</el-tag>
          <el-tag size="small" effect="plain">{{ categoryName(store.info.category) }}</el-tag>
        </div>
        <div class="title-area" v-else>
          <h2 class="code">{{ fullSymbol }}</h2>
          <span class="name">加载中…</span>
        </div>

        <div class="quote-area" v-if="store.quotes">
          <div class="price" :class="changeClass">{{ formatPrice(store.quotes.current_price) }}</div>
          <div class="change" :class="changeClass">
            <span>{{ formatChange(store.quotes.change) }}</span>
            <span class="pct">({{ formatPercent(store.quotes.pct_chg) }}%)</span>
          </div>
        </div>

        <div class="actions">
          <el-button @click="reload">
            <el-icon><Refresh /></el-icon> 刷新
          </el-button>
          <el-button @click="goBack">
            <el-icon><Back /></el-icon> 返回
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- Tab -->
    <el-tabs v-model="activeTab" class="detail-tabs">
      <!-- ① 报价 + 基础信息 -->
      <el-tab-pane label="报价 & 基础信息" name="quotes">
        <el-row :gutter="12">
          <el-col :xs="24" :md="12">
            <el-card shadow="hover" v-loading="store.loading(`quotes:${fullSymbol}`)">
              <el-alert
                v-if="store.errorMsg(`quotes:${fullSymbol}`)"
                type="warning"
                :title="store.errorMsg(`quotes:${fullSymbol}`)"
                :closable="false"
                show-icon
                style="margin-bottom: 12px"
              />
              <template #header>
                <b>实时报价</b>
                <el-tag size="small" type="info" style="margin-left: 8px">{{ store.quotes?.trade_date }}</el-tag>
              </template>
              <el-descriptions :column="2" border size="small" v-if="store.quotes">
                <el-descriptions-item label="开盘">{{ formatPrice(store.quotes.open) }}</el-descriptions-item>
                <el-descriptions-item label="最高">{{ formatPrice(store.quotes.high) }}</el-descriptions-item>
                <el-descriptions-item label="最低">{{ formatPrice(store.quotes.low) }}</el-descriptions-item>
                <el-descriptions-item label="昨收">{{ formatPrice(store.quotes.pre_close) }}</el-descriptions-item>
                <el-descriptions-item label="结算价">{{ formatPrice(store.quotes.settlement_price) }}</el-descriptions-item>
                <el-descriptions-item label="单位">{{ store.quotes.unit }}</el-descriptions-item>
                <el-descriptions-item label="成交量">{{ formatNumber(store.quotes.volume) }}</el-descriptions-item>
                <el-descriptions-item label="持仓量">{{ formatNumber(store.quotes.open_interest) }}</el-descriptions-item>
              </el-descriptions>
              <el-empty v-else description="暂无行情" />
            </el-card>
          </el-col>

          <el-col :xs="24" :md="12">
            <el-card shadow="hover" v-loading="store.loading(`info:${fullSymbol}`)">
              <el-alert
                v-if="store.errorMsg(`info:${fullSymbol}`)"
                type="warning"
                :title="store.errorMsg(`info:${fullSymbol}`)"
                :closable="false"
                show-icon
                style="margin-bottom: 12px"
              />
              <template #header><b>基础信息</b></template>
              <el-descriptions :column="1" border size="small" v-if="store.info">
                <el-descriptions-item label="品种代码">{{ store.info.code }}</el-descriptions-item>
                <el-descriptions-item label="全名">{{ store.info.name }}</el-descriptions-item>
                <el-descriptions-item label="交易所">{{ store.info.exchange_name || store.info.exchange }}</el-descriptions-item>
                <el-descriptions-item label="品类">{{ store.info.category }}</el-descriptions-item>
                <el-descriptions-item label="合约乘数">{{ store.info.contract_size }}</el-descriptions-item>
                <el-descriptions-item label="单位">{{ store.info.unit }}</el-descriptions-item>
                <el-descriptions-item label="货币">{{ store.info.currency || 'CNY' }}</el-descriptions-item>
                <el-descriptions-item label="数据来源">{{ store.info.data_source || 'akshare' }}</el-descriptions-item>
                <el-descriptions-item label="更新时间">{{ formatTime(store.info.updated_at) }}</el-descriptions-item>
              </el-descriptions>
              <el-empty v-else description="暂无基础信息" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>

      <!-- ② 日 K 线 -->
      <el-tab-pane label="日 K 线" name="kline">
        <el-card shadow="never" v-loading="store.loading(`historical:${fullSymbol}`)">
          <el-alert
            v-if="store.errorMsg(`historical:${fullSymbol}`)"
            type="warning"
            :title="store.errorMsg(`historical:${fullSymbol}`)"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
          />
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <b>日 K 线(最近 {{ klineDays }} 天)</b>
              <div>
                <el-radio-group v-model="klineDays" size="small" @change="reloadKline">
                  <el-radio-button :value="30">30 天</el-radio-button>
                  <el-radio-button :value="90">90 天</el-radio-button>
                  <el-radio-button :value="180">180 天</el-radio-button>
                  <el-radio-button :value="365">1 年</el-radio-button>
                </el-radio-group>
              </div>
            </div>
          </template>
          <div ref="klineRef" class="kline-chart"></div>
          <el-empty v-if="!store.historical?.rows?.length" description="暂无 K 线数据" />
        </el-card>
      </el-tab-pane>

      <!-- ③ 库存(按品种) -->
      <el-tab-pane label="库存" name="inventory">
        <el-card shadow="never" v-loading="store.loading(`inventory:${fullSymbol}`)">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <b>库存数据</b>
              <el-tag size="small">东方财富(近 60 交易日) / 99 期货(长期)</el-tag>
            </div>
          </template>
          <div ref="inventoryChartRef" class="kline-chart"></div>
          <el-empty v-if="!store.inventory?.rows?.length" description="该品种暂无库存数据(部分品种无库存接口)" />
          <el-table
            v-if="store.inventory?.rows?.length"
            :data="store.inventory.rows"
            stripe
            border
            size="small"
            :max-height="280"
            style="margin-top: 12px"
          >
            <el-table-column prop="日期" label="日期" width="120" />
            <el-table-column prop="库存" label="库存(万吨)" />
            <el-table-column prop="增减" label="增减" />
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ④ 基差(全市场汇总) -->
      <el-tab-pane label="基差" name="basis">
        <el-card shadow="never" v-loading="store.loading('basis')">
          <template #header><b>当日现货 + 基差(全品种 51 行)</b></template>
          <el-empty v-if="!store.basis?.rows?.length" description="暂无基差数据" />
          <el-table
            v-if="store.basis?.rows?.length"
            :data="store.basis.rows"
            stripe
            border
            size="small"
            :max-height="420"
          >
            <el-table-column prop="品种" label="品种" width="80" />
            <el-table-column prop="现货价格" label="现货" />
            <el-table-column prop="主力合约代码" label="主力合约" />
            <el-table-column prop="基差" label="基差" />
            <el-table-column prop="基差率" label="基差率" />
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ⑤ 持仓 -->
      <el-tab-pane label="持仓" name="position">
        <el-card shadow="never" v-loading="store.loading(`holding:${fullSymbol}:成交量`)">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <b>期货成交持仓</b>
              <el-radio-group v-model="holdingIndicator" size="small" @change="reloadHolding">
                <el-radio-button value="成交量">成交量</el-radio-button>
                <el-radio-button value="多单持仓">多单持仓</el-radio-button>
                <el-radio-button value="空单持仓">空单持仓</el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <el-empty v-if="!store.holdingPosition?.rows?.length" description="暂无持仓数据" />
          <el-table
            v-if="store.holdingPosition?.rows?.length"
            :data="store.holdingPosition.rows"
            stripe
            border
            size="small"
            :max-height="420"
          >
            <el-table-column prop="合约代码" label="合约" width="100" />
            <el-table-column prop="成交量" label="成交量" />
            <el-table-column prop="多单持仓" label="多单持仓" />
            <el-table-column prop="空单持仓" label="空单持仓" />
          </el-table>
        </el-card>
      </el-tab-pane>

      <!-- ⑥ 新闻 -->
      <el-tab-pane label="新闻" name="news">
        <el-card shadow="never">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <b>期货市场新闻</b>
              <el-select v-model="newsCategory" size="small" placeholder="选择分类" @change="reloadNews" style="width: 180px">
                <el-option v-for="c in store.newsCategories" :key="c.code" :label="c.name" :value="c.code" />
              </el-select>
            </div>
          </template>
          <el-empty v-if="!store.news.length && !store.loading(`news:${newsCategory}:30`)" description="暂无新闻" />
          <ul class="news-list" v-loading="store.loading(`news:${newsCategory}:30`)">
            <li v-for="(n, idx) in store.news" :key="idx" class="news-item">
              <div class="news-meta">
                <el-tag size="small" :type="sentimentType(n.sentiment)">{{ n.sentiment }}</el-tag>
                <span class="news-cat">{{ n.category }}</span>
                <span class="news-time">{{ formatTime(n.published_at) }}</span>
                <span class="news-src">{{ n.source }}</span>
              </div>
              <div class="news-title">{{ n.title }}</div>
              <div class="news-content" v-if="n.content">{{ n.content }}</div>
            </li>
          </ul>
        </el-card>
      </el-tab-pane>

      <!-- ⑦ 其它扩展(费用/合约信息等折叠) -->
      <el-tab-pane label="扩展数据" name="extra">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-card shadow="never">
              <template #header><b>手续费 / 保证金(全交易所 769 行)</b></template>
              <el-button type="primary" plain @click="loadFees" :loading="feesLoading">拉取数据</el-button>
              <el-table
                v-if="feesRows.length"
                :data="feesRows.slice(0, 50)"
                stripe border size="small" :max-height="280" style="margin-top:12px"
              >
                <el-table-column v-for="col in feesCols" :key="col" :prop="col" :label="col" :min-width="80" />
              </el-table>
              <el-empty v-else-if="!feesLoading" description="未拉取" />
            </el-card>
          </el-col>

          <el-col :span="12">
            <el-card shadow="never">
              <template #header><b>合约信息({{ exchangeInfo }})</b></template>
              <el-button type="primary" plain @click="loadContractInfo" :loading="contractLoading">
                拉取 {{ exchangeInfo }} 合约
              </el-button>
              <el-table
                v-if="contractRows.length"
                :data="contractRows.slice(0, 50)"
                stripe border size="small" :max-height="280" style="margin-top:12px"
              >
                <el-table-column v-for="col in contractCols" :key="col" :prop="col" :label="col" :min-width="80" />
              </el-table>
              <el-empty v-else-if="!contractLoading" description="未拉取" />
            </el-card>
          </el-col>
        </el-row>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Back } from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import { useCommodityStore } from '@/stores/commodity'
import commodityApi from '@/api/commodity'

const route = useRoute()
const router = useRouter()
const store = useCommodityStore()

const fullSymbol = computed<string>(() => String(route.params.fullSymbol || ''))
const activeTab = ref<string>((route.query.tab as string) || 'quotes')
const klineDays = ref<number>(180)
const holdingIndicator = ref<'成交量' | '多单持仓' | '空单持仓'>('成交量')
const newsCategory = ref<string>('all')

const exchangeInfo = computed(() => fullSymbol.value.split('.').pop() || 'SHFE')

// ---- ECharts 实例 ----
const klineRef = ref<HTMLDivElement | null>(null)
const inventoryChartRef = ref<HTMLDivElement | null>(null)
let klineChart: echarts.ECharts | null = null
let inventoryChart: echarts.ECharts | null = null

// ---- 扩展数据(费用 / 合约信息) ----
const feesLoading = ref(false)
const feesRows = ref<Record<string, unknown>[]>([])
const feesCols = ref<string[]>([])

const contractLoading = ref(false)
const contractRows = ref<Record<string, unknown>[]>([])
const contractCols = ref<string[]>([])

// ---- 加载流程 ----
async function reload() {
  store.clearSymbolData()
  await store.loadDictionaries()
  if (!fullSymbol.value) {
    ElMessage.warning('缺少标的代码')
    return
  }
  await Promise.all([
    store.loadSymbolDetail(fullSymbol.value, klineDays.value),
    store.loadInventory(fullSymbol.value),
    store.loadBasis(30),
    store.loadHoldingPosition(fullSymbol.value, holdingIndicator.value),
    store.loadNewsCategories(),
  ])
  await nextTick()
  renderKline()
  renderInventory()
}

function reloadKline() {
  if (!fullSymbol.value) return
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - klineDays.value)
  store.loadHistorical(fullSymbol.value, startDate.toISOString().slice(0, 10))
}

function reloadHolding() {
  if (!fullSymbol.value) return
  store.loadHoldingPosition(fullSymbol.value, holdingIndicator.value)
}

function reloadNews() {
  store.loadNews(newsCategory.value, 30)
}

async function loadFees() {
  feesLoading.value = true
  try {
    const r = await commodityApi.getFees(fullSymbol.value)
    const items = (r as any)?.data?.items
    if (Array.isArray(items) && items.length) {
      feesRows.value = items
      feesCols.value = Object.keys(items[0] as Record<string, unknown>)
      ElMessage.success(`拉取费用/保证金成功(共 ${items.length} 行)`)
    } else {
      feesRows.value = []
    }
  } catch (e) {
    ElMessage.error('拉取失败: ' + String(e))
  } finally {
    feesLoading.value = false
  }
}

async function loadContractInfo() {
  contractLoading.value = true
  try {
    const r = await commodityApi.getContractInfo(exchangeInfo.value)
    const items = (r as any)?.data?.rows
    if (Array.isArray(items) && items.length) {
      contractRows.value = items
      contractCols.value = Object.keys(items[0] as Record<string, unknown>)
      ElMessage.success(`拉取 ${exchangeInfo.value} 合约信息成功(共 ${items.length} 行)`)
    } else {
      contractRows.value = []
    }
  } catch (e) {
    ElMessage.error('拉取失败: ' + String(e))
  } finally {
    contractLoading.value = false
  }
}

// ---- Echarts 渲染 ----
function renderKline() {
  if (!klineRef.value) return
  if (!klineChart) klineChart = echarts.init(klineRef.value)
  const rows = store.historical?.rows || []
  if (!rows.length) {
    klineChart.clear()
    return
  }
  const dates = rows.map((r) => r.date)
  // 简化渲染:candlestick 数据格式 = [open, close, low, high]
  // 由于我们后端只返 open/high/low/close 5 个,合并为 [open, close, low, high]
  const candleData = rows.map((r) => [r.open, r.close, r.low, r.high])
  const volData = rows.map((r, i) => [i, r.volume])

  klineChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    grid: [
      { left: 50, right: 20, top: 30, height: '60%' },
      { left: 50, right: 20, top: '75%', height: '18%' },
    ],
    xAxis: [
      { type: 'category', data: dates, scale: true, boundaryGap: false, axisLabel: { show: false } },
      { type: 'category', data: dates, gridIndex: 1, axisLabel: { fontSize: 10 } },
    ],
    yAxis: [
      { scale: true, splitArea: { show: true } },
      { gridIndex: 1, splitNumber: 2, axisLabel: { fontSize: 10 } },
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1], start: 50, end: 100 },
      { show: true, xAxisIndex: [0, 1], type: 'slider', bottom: 5, height: 20 },
    ],
    series: [
      {
        type: 'candlestick',
        name: 'K线',
        data: candleData,
        itemStyle: {
          color: '#ef232a', color0: '#14b143',
          borderColor: '#ef232a', borderColor0: '#14b143',
        },
      },
      {
        name: '成交量',
        type: 'bar',
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: volData,
        itemStyle: { color: '#7f7f7f' },
      },
    ],
  }, true)
}

function renderInventory() {
  if (!inventoryChartRef.value) return
  if (!inventoryChart) inventoryChart = echarts.init(inventoryChartRef.value)
  const rows = (store.inventory?.rows || []) as Record<string, unknown>[]
  if (!rows.length) {
    inventoryChart.clear()
    return
  }
  const dates = rows.map((r) => String(r['日期'] || ''))
  const values = rows.map((r) => Number(r['库存'] || 0))

  inventoryChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 60, right: 20, top: 30, bottom: 60 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', name: '库存(万吨)' },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 18, bottom: 5 },
    ],
    series: [{
      type: 'line', data: values, smooth: true,
      itemStyle: { color: '#409eff' },
      areaStyle: { color: 'rgba(64,158,255,0.15)' },
    }],
  }, true)
}

// ---- 路由/生命周期 ----
function goBack() {
  if (window.history.length > 1) router.back()
  else router.push('/commodity/list')
}

onMounted(async () => {
  await reload()
  reloadNews()
})

onUnmounted(() => {
  klineChart?.dispose()
  inventoryChart?.dispose()
})

watch(activeTab, () => {
  nextTick(() => {
    if (activeTab.value === 'kline') renderKline()
    if (activeTab.value === 'inventory') renderInventory()
  })
})

watch(() => store.historical, () => {
  if (activeTab.value === 'kline') nextTick(renderKline)
})
watch(() => store.inventory, () => {
  if (activeTab.value === 'inventory') nextTick(renderInventory)
})

// ---- 格式化 ----
function formatPrice(v: number | undefined | null): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toFixed(2)
}
function formatChange(v: number | undefined | null): string {
  if (v === undefined || v === null) return '-'
  const n = Number(v)
  return (n > 0 ? '+' : '') + n.toFixed(2)
}
function formatPercent(v: number | undefined | null): string {
  const n = Number(v)
  return Number.isFinite(n) ? n.toFixed(2) : '-'
}
function formatNumber(v: number | undefined | null): string {
  if (v === undefined || v === null) return '-'
  return Number(v).toLocaleString('zh-CN')
}
function formatTime(s: string | undefined | null): string {
  if (!s) return '-'
  return s.replace('T', ' ').slice(0, 19)
}
const changeClass = computed(() => {
  const c = store.quotes?.change ?? 0
  return c > 0 ? 'up' : c < 0 ? 'down' : ''
})
function exchangeTagType(code: string): 'primary' | 'success' | 'warning' | 'info' | 'danger' {
  const map: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
    SHFE: 'primary', DCE: 'success', CZCE: 'warning', INE: 'info', GFEX: 'danger', CFFEX: 'info',
  }
  return map[code] || 'info'
}
function categoryName(code: string): string {
  return store.categories.find((c) => c.code === code)?.name || code
}
function sentimentType(sent: string): 'success' | 'danger' | 'info' {
  if (sent === 'positive') return 'success'
  if (sent === 'negative') return 'danger'
  return 'info'
}
</script>

<style scoped>
.commodity-detail { padding: 16px; }
.header-card { margin-bottom: 12px; }
.header-inner { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.title-area { display: flex; align-items: center; gap: 8px; }
.title-area .code { margin: 0; font-size: 22px; }
.title-area .name { font-size: 14px; color: var(--el-text-color-secondary); }
.quote-area { display: flex; align-items: baseline; gap: 12px; }
.quote-area .price { font-size: 26px; font-weight: 600; }
.quote-area .change.up { color: #ef232a; }
.quote-area .change.down { color: #14b143; }
.quote-area .pct { font-size: 12px; margin-left: 4px; }
.actions { display: flex; gap: 8px; }
.detail-tabs { background: #fff; border-radius: 4px; padding: 12px; }
.kline-chart { width: 100%; height: 420px; }
.news-list { padding: 0; margin: 0; list-style: none; }
.news-item { padding: 12px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.news-meta { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.news-title { font-size: 14px; font-weight: 500; margin: 4px 0; }
.news-content { font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
</style>
