<template>
  <div class="commodity-detail">
    <!-- 顶部 -->
    <el-card class="header-card" shadow="never">
      <div class="header-inner">
        <div class="title-area" v-if="store.info">
          <h2 class="code">{{ store.info.underlying || store.info.code || store.info.full_symbol }}</h2>
          <span class="name">{{ stripFuturesSuffix(store.info.name) }}</span>
          <el-tag size="small" :type="exchangeTagType(store.info.exchange)">{{ store.info.exchange }}</el-tag>
          <el-tag size="small" effect="plain">{{ categoryName(store.info.category) }}</el-tag>
        </div>
        <div class="title-area" v-else>
          <h2 class="code">{{ extractUnderlying(fullSymbol) || fullSymbol }}</h2>
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

      <!-- ② 日 K 线 / 现货价 -->
      <el-tab-pane label="日 K 线" name="kline">
        <el-card shadow="never" v-loading="klineLoading">
          <el-alert
            v-if="klineError"
            type="warning"
            :title="klineError"
            :closable="false"
            show-icon
            style="margin-bottom: 12px"
          />
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:8px;">
              <div style="display:flex; align-items:center; gap:8px;">
                <b v-if="klineMode === 'kline'">日 K 线</b>
                <b v-else>现货价走势</b>
                <span v-if="klineSymbol !== fullSymbol" style="font-size:12px; color:var(--el-text-color-secondary);">
                  {{ klineSymbol }}
                </span>
                <el-radio-group v-model="klineMode" size="small" @change="switchKlineMode">
                  <el-radio-button value="kline">K 线</el-radio-button>
                  <el-radio-button value="spot">现货价</el-radio-button>
                </el-radio-group>
              </div>
              <div style="display:flex; align-items:center; gap:8px;">
                <!-- 合约选择器(K线模式下) -->
                <el-select
                  v-if="klineMode === 'kline' && contractsList.contracts.length"
                  v-model="klineSymbol"
                  size="small"
                  @change="onContractChange"
                  style="width:160px"
                >
                  <el-option-group label="主力连续">
                    <el-option
                      v-if="contractsList.continuous"
                      :value="contractsList.continuous"
                      label="主力连续"
                    />
                  </el-option-group>
                  <el-option-group label="到期合约">
                    <el-option
                      v-for="c in contractsList.contracts"
                      :key="c"
                      :value="c"
                      :label="c.split('.')[0]"
                    />
                  </el-option-group>
                </el-select>
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
          <el-empty v-if="!hasKlineData" :description="klineMode === 'kline' ? '暂无 K 线数据' : '暂无现货价数据'" />
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

      <!-- ④ 基差(按品种) -->
      <el-tab-pane label="基差" name="basis">
        <el-card shadow="never" v-loading="store.loading('basis')">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <b>基差({{ extractUnderlying(fullSymbol) }} 近 30 日)</b>
              <el-button size="small" @click="reloadBasis">刷新</el-button>
            </div>
          </template>
          <div ref="basisChartRef" class="kline-chart" style="height: 360px;"></div>
          <el-empty v-if="!store.basis?.rows?.length" description="暂无基差数据(部分品种无基差接口)" />
          <el-table
            v-if="store.basis?.rows?.length"
            :data="store.basis.rows"
            stripe
            border
            size="small"
            :max-height="280"
            style="margin-top: 12px"
          >
            <el-table-column prop="date" label="日期" width="120" />
            <el-table-column prop="symbol" label="品种" width="80" />
            <el-table-column prop="dominant_contract" label="主力合约" width="100" />
            <el-table-column prop="spot_price" label="现货" />
            <el-table-column prop="dominant_contract_price" label="期货" />
            <el-table-column prop="dom_basis" label="基差" />
            <el-table-column prop="dom_basis_rate" label="基差率" />
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
            <div style="display:flex; align-items:center; gap:8px">
              <b>期货市场新闻</b>
              <el-tag v-if="currentVariety" size="small" type="primary" effect="plain">
                {{ currentVariety }}
              </el-tag>
              <el-tag v-if="newsEmptyRelevant" size="small" type="info" effect="plain">暂无品种相关新闻</el-tag>
            </div>
          </template>
          <el-empty v-if="!store.news.length && !store.loading(newsLoadingKey)" :description="currentVariety ? '暂无品种相关新闻' : '暂无新闻'" />
          <ul class="news-list" v-loading="store.loading(newsLoadingKey)">
            <li v-for="(n, idx) in store.news" :key="idx" class="news-item" :class="importanceClass(n)">
              <div class="news-meta">
                <el-tag size="small" :type="sentimentType(n.llm_sentiment || n.sentiment)">
                  {{ n.llm_sentiment || n.sentiment }}
                </el-tag>
                <span v-if="n.llm_sentiment_confidence !== undefined" class="news-conf">
                  {{ (n.llm_sentiment_confidence * 100).toFixed(0) }}%
                </span>
                <template v-for="rv in (n.relevant_varieties || [])" :key="rv">
                  <el-tag size="small" :type="rv === currentVariety ? 'primary' : 'info'" effect="plain">
                    {{ rv }}
                  </el-tag>
                </template>
                <span v-if="!n.relevant_varieties?.length && n.category" class="news-cat">{{ n.category }}</span>
                <span class="news-time">{{ formatTime(n.published_at) }}</span>
                <span class="news-src">{{ n.source }}</span>
                <el-tag v-if="n.llm_importance === 'high'" size="small" type="warning" effect="dark">重要</el-tag>
              </div>
              <div class="news-title" :title="n.title">{{ n.llm_summary || n.title }}</div>
              <div class="news-content" v-if="n.llm_sentiment_reasoning">{{ n.llm_sentiment_reasoning }}</div>
              <div class="news-content" v-else-if="n.content">{{ n.content }}</div>
            </li>
          </ul>
        </el-card>
      </el-tab-pane>

      <!-- ⑦ 其它扩展(费用/合约信息等折叠) -->
      <el-tab-pane label="扩展数据" name="extra">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-card shadow="never" v-loading="feesLoading">
              <template #header>
                <b>手续费 / 保证金</b>
                <el-tag size="small" type="info" style="margin-left: 8px">
                  交易所维度 · {{ exchangeInfo }}
                </el-tag>
              </template>
              <el-tabs v-if="feesAllLoaded" v-model="feesTab" style="margin-top: 12px">
                <el-tab-pane
                  :label="`当前品种 (${currentFeesRows.length})`"
                  name="current"
                >
                  <el-table
                    v-if="currentFeesRows.length"
                    :data="currentFeesRows"
                    stripe border size="small" :max-height="280"
                  >
                    <el-table-column
                      v-for="col in feesCols" :key="col" :prop="col"
                      :label="col" :min-width="80"
                    />
                  </el-table>
                  <el-empty
                    v-else
                    :description="`当前品种 ${currentUnderlying} 在 ${exchangeInfo} 暂无费率数据,可在'交易所全部'中对比`"
                  />
                </el-tab-pane>
                <el-tab-pane
                  :label="`交易所全部 (${allFeesRows.length} 行)`"
                  name="all"
                >
                  <el-table
                    :data="allFeesRows"
                    stripe border size="small" :max-height="280"
                  >
                    <el-table-column
                      v-for="col in feesCols" :key="col" :prop="col"
                      :label="col" :min-width="80"
                    />
                  </el-table>
                </el-tab-pane>
              </el-tabs>
              <el-empty v-else-if="!feesLoading" description="未拉取" />
            </el-card>
          </el-col>

          <el-col :span="12">
            <el-card shadow="never" v-loading="contractLoading">
              <template #header><b>合约信息 ({{ exchangeInfo }})</b></template>
              <div v-if="contractRows.length" style="margin-top: 12px">
                <el-tag size="small" type="info" style="margin-bottom: 8px">
                  共 {{ contractRows.length }} 行
                </el-tag>
                <el-table
                  :data="contractRows"
                  stripe border size="small" :max-height="320"
                >
                  <el-table-column v-for="col in contractCols" :key="col" :prop="col" :label="col" :min-width="80" />
                </el-table>
              </div>
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
const klineMode = ref<'kline' | 'spot'>('kline')
const klineSymbol = ref<string>('')
const contractsList = ref<{ continuous: string | null; contracts: string[] }>({ continuous: null, contracts: [] })
const holdingIndicator = ref<'成交量' | '多单持仓' | '空单持仓'>('成交量')
const newsCategory = ref<string>('all')

// 当前品种代码(如 CU),用于新闻按品种筛选
const currentVariety = computed(() => extractUnderlying(fullSymbol.value))

// 新闻加载 key,与 store.loadNews 的 key 保持一致
const newsLoadingKey = computed(() =>
  `news:${newsCategory.value}:30${currentVariety.value ? `:${currentVariety.value}` : ''}`,
)

// 品种相关新闻是否已加载但目前为空(区别于还未加载)
const newsEmptyRelevant = computed(() => {
  if (!currentVariety.value) return false
  if (store.loading(newsLoadingKey.value)) return false
  return store.news.length === 0
})

// K 线卡片的 loading/error 状态：根据当前模式动态取不同 key
const klineLoadingKey = computed(() =>
  klineMode.value === 'kline' ? `historical:${klineSymbol.value}` : 'basis',
)
const klineLoading = computed(() => store.loading(klineLoadingKey.value))
const klineError = computed(() => store.errorMsg(klineLoadingKey.value))
const hasKlineData = computed(() =>
  klineMode.value === 'kline'
    ? !!store.historical?.rows?.length
    : !!store.basis?.rows?.length && (store.basis.rows as any[]).some((r: any) => r.spot_price !== undefined),
)

// 后端 /contract-info 接收 SHFE/DCE/CZCE 等长码;前端从 fullSymbol 提取的
// 是短码(SHF/CZC),需要映射成长码才能成功调用
const EXCHANGE_SUFFIX: Record<string, string> = {
  SHF: 'SHFE',
  DCE: 'DCE',
  CZC: 'CZCE',
  INE: 'INE',
  GFEX: 'GFEX',
  CFFEX: 'CFFEX',
  SHFE: 'SHFE',
  CZCE: 'CZCE',
}
const exchangeInfo = computed(() => {
  const raw = fullSymbol.value.split('.').pop() || 'SHFE'
  return EXCHANGE_SUFFIX[raw] || raw
})

// 从 full_symbol 提取品种代码(CU2501.SHF → CU / CU0.SHF → CU / RB2510.DCE → RB)
function extractUnderlying(fs: string): string {
  return fs.replace(/\..*/, '').replace(/\d+$/, '').toUpperCase()
}

// ---- ECharts 实例 ----
const klineRef = ref<HTMLDivElement | null>(null)
const inventoryChartRef = ref<HTMLDivElement | null>(null)
const basisChartRef = ref<HTMLDivElement | null>(null)
let klineChart: echarts.ECharts | null = null
let inventoryChart: echarts.ECharts | null = null
let basisChart: echarts.ECharts | null = null

// ---- 扩展数据(费用 / 合约信息) ----
const feesLoading = ref(false)
// 手续费/保证金是交易所维度数据(AKShare 接口一次性吐整张交易所表),
// 这里把它切成两份:当前品种行 + 全表,UI 上分别用两个 tab 展示
const currentFeesRows = ref<Record<string, unknown>[]>([])
const allFeesRows = ref<Record<string, unknown>[]>([])
const feesCols = ref<string[]>([])
const feesTab = ref<'current' | 'all'>('current')
const feesAllLoaded = ref(false)
const currentUnderlying = ref('')

// 上游 AKShare 费率表里"品种代码"这一列的列名在不同日期/接口下不稳定,
// 列名白名单保证过滤逻辑对这种差异有韧性
const FEE_SYMBOL_COLUMN_CANDIDATES = [
  '品种代码', 'symbol', 'code', 'symbol_code', '品种', '品种简称', '品种名', '品种名称',
] as const

function pickSymbolColumn(row: Record<string, unknown>): string | null {
  for (const key of FEE_SYMBOL_COLUMN_CANDIDATES) {
    if (key in row) return key
  }
  return null
}

// 合约信息表格中"品种代码"列名白名单(不同交易所/接口返回的列名可能不同)
const CONTRACT_SYMBOL_COLUMN_CANDIDATES = [
  '品种代码', 'symbol_code', '品种简称', '品种',
] as const

function pickContractSymbolColumn(row: Record<string, unknown>): string | null {
  for (const key of CONTRACT_SYMBOL_COLUMN_CANDIDATES) {
    if (key in row) return key
  }
  // 无白名单列时,尝试取第一列(部分接口列名不稳定,用第一列作为品种代码列)
  const keys = Object.keys(row)
  return keys.length > 0 ? keys[0] : null
}

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
  const endDate = new Date().toISOString().slice(0, 10)
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - 30)
  const startStr = startDate.toISOString().slice(0, 10)
  const underlying = extractUnderlying(fullSymbol.value)

  // 并行加载:基础数据 + 合约列表 + 扩展数据(手续费/合约信息)
  await Promise.all([
    store.loadSymbolDetail(fullSymbol.value, klineDays.value),
    store.loadInventory(fullSymbol.value),
    store.loadBasisForVars([underlying], startStr, endDate),
    store.loadHoldingPosition(fullSymbol.value, holdingIndicator.value),
    store.loadNewsCategories(),
    loadContractsList(),
    loadFees(),
    loadContractInfo(),
  ])
  await nextTick()
  renderKline()
  renderInventory()
  renderBasis()
}

function reloadKline() {
  if (!fullSymbol.value) return
  const symbol = klineSymbol.value || fullSymbol.value
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - klineDays.value)
  store.loadHistorical(symbol, startDate.toISOString().slice(0, 10))
}

async function loadContractsList() {
  if (!fullSymbol.value) return
  try {
    const r = await commodityApi.getContractsList(fullSymbol.value)
    const data = (r as any)?.data
    if (data?.contracts) {
      contractsList.value = { continuous: data.continuous, contracts: data.contracts }
    }
    // 初始化 klineSymbol 为当前 fullSymbol
    klineSymbol.value = fullSymbol.value
  } catch (e) {
    console.error('[commodity] loadContractsList failed', e)
    klineSymbol.value = fullSymbol.value
  }
}

function switchKlineMode(mode: 'kline' | 'spot') {
  klineMode.value = mode
  if (mode === 'kline') {
    reloadKline()
  } else {
    loadSpotPrice()
  }
}

function onContractChange(newSymbol: string) {
  klineSymbol.value = newSymbol
  reloadKline()
}

async function loadSpotPrice() {
  const underlying = extractUnderlying(fullSymbol.value)
  const endDate = new Date().toISOString().slice(0, 10)
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - klineDays.value)
  await store.loadBasisForVars([underlying], startDate.toISOString().slice(0, 10), endDate)
  nextTick(renderSpotPriceLine)
}

function reloadHolding() {
  if (!fullSymbol.value) return
  store.loadHoldingPosition(fullSymbol.value, holdingIndicator.value)
}

function reloadNews() {
  store.loadNews(newsCategory.value, 30, currentVariety.value)
}

async function loadFees() {
  feesLoading.value = true
  try {
    const r = await commodityApi.getFees(fullSymbol.value)
    const items = (r as any)?.data?.items
    // 1. 上游接口返回的不是数组 → 视为空表,绝不回退展示全量
    if (!Array.isArray(items) || items.length === 0) {
      currentFeesRows.value = []
      allFeesRows.value = []
      feesCols.value = []
      feesAllLoaded.value = true
      currentUnderlying.value = extractUnderlying(fullSymbol.value)
      return
    }

    // 2. 全表先落地(交易所全部 tab 用)
    allFeesRows.value = items
    feesCols.value = Object.keys(items[0] as Record<string, unknown>)

    // 3. 按白名单列名匹配,定位"品种代码"列;再按当前 underlying 过滤出"当前品种"行
    const underlying = extractUnderlying(fullSymbol.value)
    currentUnderlying.value = underlying
    // 用第一行确定白名单列名(避免不同行 schema 不一致)
    const symCol = pickSymbolColumn(items[0] as Record<string, unknown>)
    if (symCol) {
      const target = underlying.toUpperCase()
      currentFeesRows.value = items.filter(
        (it: any) => String(it?.[symCol] ?? '').toUpperCase() === target,
      )
    } else {
      // 找不到品种代码列 → 当前品种 tab 显示空,不由前端猜测/回退
      currentFeesRows.value = []
    }

    feesAllLoaded.value = true
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
      const underlying = extractUnderlying(fullSymbol.value)
      currentUnderlying.value = underlying

      // 找品种代码列,按当前 underlying 过滤
      const symCol = pickContractSymbolColumn(items[0] as Record<string, unknown>)
      let filtered: Record<string, unknown>[]
      if (symCol && underlying) {
        const target = underlying.toUpperCase()
        filtered = items.filter(
          (it: any) => String(it?.[symCol] ?? '').toUpperCase() === target,
        )
        // 若品种代码列匹配不到,降级为按合约代码前缀匹配
        if (filtered.length === 0) {
          const codeCandidates = ['合约代码', 'contract_code', 'code', 'symbol', '品种代码']
          const codeKey = codeCandidates.find(c => c in items[0]) || Object.keys(items[0] as Record<string, unknown>)[0]
          filtered = items.filter(
            (it: any) => String(it?.[codeKey] ?? '').toUpperCase().startsWith(target),
          )
        }
      } else {
        filtered = items
      }

      contractRows.value = filtered
      contractCols.value = Object.keys(items[0] as Record<string, unknown>)
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
  // 自适应铺面:容器宽度变化时重画
  klineChart.resize()
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

// 基差图:柱状=基差,线=基差率(双轴)
// 后端字段为英文:date / symbol / spot_price / near_contract / dominant_contract /
//                 dominant_contract_price / dom_basis / dom_basis_rate
function renderBasis() {
  if (!basisChartRef.value) return
  if (!basisChart) basisChart = echarts.init(basisChartRef.value)
  const rows = (store.basis?.rows || []) as Record<string, unknown>[]
  if (!rows.length) {
    basisChart.clear()
    return
  }
  const dates = rows.map((r) => String(r['date'] || r['日期'] || ''))
  const basisValues = rows.map((r) => Number(r['dom_basis'] ?? r['基差'] ?? 0))
  const basisRateValues = rows.map((r) => Number(r['dom_basis_rate'] ?? r['基差率'] ?? 0))

  basisChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
    legend: { data: ['基差', '基差率'], top: 0 },
    grid: { left: 60, right: 60, top: 40, bottom: 60 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: [
      { type: 'value', name: '基差(元/吨)', position: 'left' },
      { type: 'value', name: '基差率(%)', position: 'right' },
    ],
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 18, bottom: 5 },
    ],
    series: [
      {
        name: '基差', type: 'bar', data: basisValues,
        itemStyle: { color: '#5470c6' },
      },
      {
        name: '基差率', type: 'line', yAxisIndex: 1, data: basisRateValues,
        itemStyle: { color: '#ee6666' }, smooth: true,
      },
    ],
  }, true)
  basisChart.resize()
}

// 现货价走势图(在日K线卡片内渲染,利用基差接口的 spot_price 字段)
function renderSpotPriceLine() {
  if (!klineRef.value) return
  if (!klineChart) klineChart = echarts.init(klineRef.value)
  const rows = (store.basis?.rows || []) as Record<string, unknown>[]
  if (!rows.length) {
    klineChart.clear()
    return
  }
  // 按日期排序
  const sorted = [...rows].sort(
    (a, b) => String(a['date'] || '').localeCompare(String(b['date'] || '')),
  )
  const dates = sorted.map((r) => String(r['date'] || r['日期'] || ''))
  const spotPrices = sorted.map((r) => Number(r['spot_price'] ?? 0))
  const futuresPrices = sorted.map((r) => Number(r['dominant_contract_price'] ?? 0))

  klineChart.setOption({
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'cross' },
      formatter: (params: any) => {
        const idx = params[0]?.dataIndex ?? 0
        const row = sorted[idx]
        const spot = row['spot_price'] ?? '-'
        const fut = row['dominant_contract_price'] ?? '-'
        const basis = row['dom_basis'] ?? '-'
        const rate = row['dom_basis_rate'] ?? '-'
        return [
          `<b>${dates[idx] || ''}</b>`,
          `现货价: ${spot}`,
          `主力期货: ${fut}`,
          `基差: ${basis}`,
          `基差率: ${rate}`,
        ].join('<br/>')
      },
    },
    legend: { data: ['现货价', '主力期货'], top: 0 },
    grid: { left: 60, right: 30, top: 40, bottom: 60 },
    xAxis: { type: 'category', data: dates, axisLabel: { fontSize: 10, rotate: 30 } },
    yAxis: { type: 'value', name: '价格', scale: true },
    dataZoom: [
      { type: 'inside', start: 0, end: 100 },
      { type: 'slider', height: 18, bottom: 5 },
    ],
    series: [
      {
        name: '现货价',
        type: 'line',
        data: spotPrices,
        smooth: true,
        symbol: 'none',
        itemStyle: { color: '#409eff' },
        areaStyle: { color: 'rgba(64,158,255,0.1)' },
      },
      {
        name: '主力期货',
        type: 'line',
        data: futuresPrices,
        smooth: true,
        symbol: 'none',
        lineStyle: { type: 'dashed', width: 1 },
        itemStyle: { color: '#ee6666' },
      },
    ],
  }, true)
  klineChart.resize()
}

async function reloadBasis() {
  const endDate = new Date().toISOString().slice(0, 10)
  const startDate = new Date()
  startDate.setDate(startDate.getDate() - 30)
  const startStr = startDate.toISOString().slice(0, 10)
  const underlying = extractUnderlying(fullSymbol.value)
  await store.loadBasisForVars([underlying], startStr, endDate)
  nextTick(renderBasis)
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
  basisChart?.dispose()
})

watch(activeTab, () => {
  nextTick(() => {
    if (activeTab.value === 'kline') {
      if (klineMode.value === 'kline') renderKline()
      else renderSpotPriceLine()
    }
    if (activeTab.value === 'inventory') renderInventory()
    if (activeTab.value === 'basis') renderBasis()
    if (activeTab.value === 'news') reloadNews()
  })
})

watch(() => store.historical, () => {
  if (activeTab.value === 'kline' && klineMode.value === 'kline') nextTick(renderKline)
})
watch(() => store.inventory, () => {
  if (activeTab.value === 'inventory') nextTick(renderInventory)
})
watch(() => store.basis, () => {
  if (activeTab.value === 'basis') nextTick(renderBasis)
  // 现货价模式也依赖 basis 数据
  if (activeTab.value === 'kline' && klineMode.value === 'spot') nextTick(renderSpotPriceLine)
}, { deep: true })
watch(klineMode, () => {
  if (activeTab.value === 'kline') {
    nextTick(() => {
      if (klineMode.value === 'kline') renderKline()
      else renderSpotPriceLine()
    })
  }
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
function importanceClass(n: any): string {
  if (n.llm_importance === 'high') return 'news-high'
  if (n.llm_importance === 'low') return 'news-low'
  return ''
}
/** 去除中文名中的"期货"字样，与商品列表对齐 */
function stripFuturesSuffix(name: string): string {
  return name?.replace(/期货/g, '') || name
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
.kline-chart { width: 100%; min-width: 900px; height: 460px; }
.news-list { padding: 0; margin: 0; list-style: none; }
.news-item { padding: 12px 0; border-bottom: 1px solid var(--el-border-color-lighter); }
.news-item.news-high { background-color: var(--el-color-warning-light-9); margin: 0 -8px; padding: 12px 8px; border-radius: 4px; }
.news-item.news-low .news-title { font-weight: 400; color: var(--el-text-color-placeholder); }
.news-meta { display: flex; gap: 8px; align-items: center; margin-bottom: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.news-conf { font-size: 11px; color: var(--el-text-color-placeholder); }
.news-title { font-size: 14px; font-weight: 500; margin: 4px 0; }
.news-content { font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
</style>
