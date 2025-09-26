<template>
  <div class="stock-detail">
    <!-- 顶部：代码 / 名称 / 操作 -->
    <div class="header">
      <div class="title">
        <div class="code">{{ code }}</div>
        <div class="name">{{ stockName }}</div>
        <el-tag size="small">{{ market }}</el-tag>
      </div>
      <div class="actions">
        <el-button type="primary" plain @click="onAnalyze">
          <el-icon><TrendCharts /></el-icon> 一键分析
        </el-button>
        <el-button @click="onToggleFavorite">
          <el-icon><Star /></el-icon> {{ isFav ? '已自选' : '加自选' }}
        </el-button>
        <el-button @click="onSetAlert">
          <el-icon><Bell /></el-icon> 预警
        </el-button>
      </div>
    </div>

    <!-- 报价条 -->
    <el-card class="quote-card" shadow="hover">
      <div class="quote">
        <div class="price-row">
          <div class="price" :class="changeClass">{{ fmtPrice(quote.price) }}</div>
          <div class="change" :class="changeClass">
            <span>{{ fmtPercent(quote.changePercent) }}</span>
          </div>
          <el-tag type="info" size="small">{{ refreshText }}</el-tag>
          <el-button text size="small" @click="refreshMockQuote" :icon="Refresh">刷新</el-button>
        </div>
        <div class="stats">
          <div class="item"><span>今开</span><b>{{ fmtPrice(quote.open) }}</b></div>
          <div class="item"><span>最高</span><b>{{ fmtPrice(quote.high) }}</b></div>
          <div class="item"><span>最低</span><b>{{ fmtPrice(quote.low) }}</b></div>
          <div class="item"><span>昨收</span><b>{{ fmtPrice(quote.prevClose) }}</b></div>
          <div class="item"><span>成交量</span><b>{{ fmtVolume(quote.volume) }}</b></div>
          <div class="item"><span>成交额</span><b>{{ fmtAmount(quote.amount) }}</b></div>
          <div class="item"><span>换手率</span><b>{{ fmtPercent(quote.turnover) }}</b></div>
          <div class="item"><span>量比</span><b>{{ quote.volumeRatio?.toFixed(2) }}</b></div>
        </div>
      </div>
    </el-card>

    <el-row :gutter="16" class="body">
      <el-col :span="16">
        <!-- 图表占位 -->
        <el-card shadow="hover">
          <template #header>
            <div class="card-hd">
              <div>价格K线（占位）</div>
              <div class="periods">
                <el-segmented v-model="period" :options="periodOptions" size="small" />
              </div>
            </div>
          </template>
          <div class="chart-placeholder">
            <div class="chart-grid">
              <div v-for="n in 40" :key="n" class="bar" :style="{ height: barHeights[n-1] + '%' }"></div>
            </div>
            <div class="legend">当前周期：{{ period }} · 指标：MA(5/20/60), MACD, RSI（展示占位，无数据对接）</div>
          </div>
        </el-card>

        <!-- 新闻占位 -->
        <el-card shadow="hover" class="news-card">
          <template #header>
            <div class="card-hd">
              <div>近期新闻与情绪（占位）</div>
              <el-select v-model="newsFilter" size="small" style="width: 120px">
                <el-option label="全部" value="all" />
                <el-option label="利好" value="pos" />
                <el-option label="中性" value="neu" />
                <el-option label="利空" value="neg" />
              </el-select>
            </div>
          </template>
          <el-empty v-if="filteredNews.length === 0" description="暂无新闻（占位）" />
          <div v-else class="news-list">
            <div v-for="(n, i) in filteredNews" :key="i" class="news-item">
              <div class="title">
                <span class="sentiment" :class="n.sentiment">●</span>{{ n.title }}
              </div>
              <div class="meta">{{ n.source }} · {{ n.time }}</div>
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :span="8">
        <!-- 基本面快照 -->
        <el-card shadow="hover">
          <template #header><div class="card-hd">基本面快照（占位）</div></template>
          <div class="facts">
            <div class="fact"><span>行业</span><b>{{ basics.industry }}</b></div>
            <div class="fact"><span>板块</span><b>{{ basics.sector }}</b></div>
            <div class="fact"><span>总市值</span><b>{{ fmtAmount(basics.marketCap) }}</b></div>
            <div class="fact"><span>PE(TTM)</span><b>{{ basics.pe?.toFixed(2) }}</b></div>
            <div class="fact"><span>ROE</span><b>{{ fmtPercent(basics.roe) }}</b></div>
            <div class="fact"><span>负债率</span><b>{{ fmtPercent(basics.debtRatio) }}</b></div>
          </div>
        </el-card>

        <!-- 快捷操作 -->
        <el-card shadow="hover" class="actions-card">
          <template #header><div class="card-hd">快捷操作</div></template>
          <div class="quick-actions">
            <el-button type="primary" @click="onAnalyze" icon="TrendCharts" plain>发起分析</el-button>
            <el-button @click="onToggleFavorite" icon="Star">{{ isFav ? '移出自选' : '加入自选' }}</el-button>
            <el-button @click="onSetAlert" icon="Bell">添加预警</el-button>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { TrendCharts, Star, Bell, Refresh } from '@element-plus/icons-vue'
import { stocksApi } from '@/api/stocks'

const route = useRoute()
const router = useRouter()

const code = computed(() => String(route.params.code || '').toUpperCase())
const stockName = ref('示例公司')
const market = ref('A股')
const isFav = ref(false)

// 报价（mock）
const quote = reactive({
  price: 23.56,
  changePercent: 1.82,
  open: 23.10,
  high: 24.20,
  low: 22.95,
  prevClose: 23.14,
  volume: 12_340_000,
  amount: 2_560_000_00,
  turnover: 1.23,
  volumeRatio: 0.96
})

const lastRefreshAt = ref<Date | null>(null)
const refreshText = computed(() => lastRefreshAt.value ? `已刷新 ${lastRefreshAt.value.toLocaleTimeString()}` : '未刷新')
const changeClass = computed(() => quote.changePercent > 0 ? 'up' : quote.changePercent < 0 ? 'down' : '')

async function refreshMockQuote() {
  // 改为调用后端接口获取真实数据
  await fetchQuote()
}

async function fetchQuote() {
  try {
    const res = await stocksApi.getQuote(code.value)
    const d: any = (res as any)?.data || {}
    // 后端为 snake_case，前端状态为 camelCase，这里进行映射
    quote.price = Number(d.price ?? d.close ?? quote.price)
    quote.changePercent = Number(d.change_percent ?? quote.changePercent)
    quote.open = Number(d.open ?? quote.open)
    quote.high = Number(d.high ?? quote.high)
    quote.low = Number(d.low ?? quote.low)
    quote.prevClose = Number(d.prev_close ?? quote.prevClose)
    quote.volume = Number.isFinite(d.volume) ? Number(d.volume) : quote.volume
    quote.amount = Number.isFinite(d.amount) ? Number(d.amount) : quote.amount
    quote.turnover = Number.isFinite(d.turnover_rate) ? Number(d.turnover_rate) : quote.turnover
    quote.volumeRatio = Number.isFinite(d.volume_ratio) ? Number(d.volume_ratio) : quote.volumeRatio
    if (d.name) stockName.value = d.name
    if (d.market) market.value = d.market
    lastRefreshAt.value = new Date()
  } catch (e) {
    console.error('获取报价失败', e)
  }
}

async function fetchFundamentals() {
  try {
    const res = await stocksApi.getFundamentals(code.value)
    const f: any = (res as any)?.data || {}
    // 基本面快照映射到现有占位字段
    if (f.name) stockName.value = f.name
    if (f.market) market.value = f.market
    basics.industry = f.industry || basics.industry
    basics.sector = basics.sector || '—'
    basics.marketCap = Number.isFinite(f.total_mv) ? Number(f.total_mv) * 1e8 : basics.marketCap // 亿元 -> 元
    basics.pe = Number.isFinite(f.pe) ? Number(f.pe) : basics.pe
    basics.roe = Number.isFinite(f.roe) ? Number(f.roe) : basics.roe
    basics.debtRatio = basics.debtRatio // 后端暂未提供
  } catch (e) {
    console.error('获取基本面失败', e)
  }
}

let timer: any = null
onMounted(async () => {
  // 首次加载：打通后端
  await Promise.all([fetchQuote(), fetchFundamentals()])
  // 每30秒刷新一次报价
  timer = setInterval(fetchQuote, 30000)
})
onUnmounted(() => { if (timer) clearInterval(timer) })

// K线占位相关
const periodOptions = ['分时','5分钟','15分钟','60分钟','日K','周K','月K']
const period = ref('日K')
const barHeights = ref<number[]>(Array.from({ length: 40 }, () => 30 + Math.random() * 60))

// 新闻（mock）
const newsFilter = ref('all')
const news = ref([
  { title: '公司发布年度业绩预增公告，营收创历史新高', source: '财联社', time: '2小时前', sentiment: 'pos' },
  { title: '行业监管新规落地，短期扰动不改长期趋势', source: '证券时报', time: '6小时前', sentiment: 'neu' },
  { title: '原材料价格波动或对毛利率产生压力', source: '21财经', time: '1天前', sentiment: 'neg' }
])
const filteredNews = computed(() => newsFilter.value === 'all' ? news.value : news.value.filter(n => n.sentiment === newsFilter.value))

// 基本面（mock）
const basics = reactive({
  industry: '白酒制造',
  sector: '消费品',
  marketCap: 256000000000,
  pe: 18.36,
  roe: 14.2,
  debtRatio: 38.5
})

// 操作
function onAnalyze() { ElMessage.info('前端占位：待接入分析接口') }
function onToggleFavorite() { isFav.value = !isFav.value; ElMessage.success(isFav.value ? '已加入自选（占位）' : '已移出自选（占位）') }
function onSetAlert() { ElMessage.info('前端占位：待接入预警接口') }

// 格式化
function fmtPrice(v: any) { const n = Number(v); return Number.isFinite(n) ? n.toFixed(2) : '-' }
function fmtPercent(v: any) { const n = Number(v); return Number.isFinite(n) ? `${n>0?'+':''}${n.toFixed(2)}%` : '-' }
function fmtVolume(v: any) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  if (n >= 1e8) return (n/1e8).toFixed(2) + '亿手'
  if (n >= 1e4) return (n/1e4).toFixed(2) + '万手'
  return n.toFixed(0)
}
function fmtAmount(v: any) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '-'
  if (n >= 1e12) return (n/1e12).toFixed(2) + '万亿'
  if (n >= 1e8) return (n/1e8).toFixed(2) + '亿'
  if (n >= 1e4) return (n/1e4).toFixed(2) + '万'
  return n.toFixed(0)
}
</script>

<style scoped lang="scss">
.stock-detail {
  display: flex; flex-direction: column; gap: 16px;
}
.header { display: flex; justify-content: space-between; align-items: center; }
.title { display: flex; align-items: center; gap: 12px; }
.code { font-size: 22px; font-weight: 700; }
.name { font-size: 18px; color: var(--el-text-color-regular); }
.actions { display: flex; gap: 8px; }

.quote-card { border-radius: 12px; }
.quote { display: flex; flex-direction: column; gap: 8px; }
.price-row { display: flex; align-items: center; gap: 12px; }
.price { font-size: 32px; font-weight: 800; }
.change { font-size: 16px; font-weight: 700; }
.up { color: #e53935; }
.down { color: #16a34a; }
.stats { display: grid; grid-template-columns: repeat(8, 1fr); gap: 10px; margin-top: 6px; }
.stats .item { display: flex; flex-direction: column; font-size: 12px; color: var(--el-text-color-secondary); }
.stats .item b { color: var(--el-text-color-primary); font-size: 14px; }

.body { margin-top: 4px; }
.card-hd { display: flex; align-items: center; justify-content: space-between; }
.chart-placeholder { height: 280px; display: flex; flex-direction: column; justify-content: space-between; }
.chart-grid { flex: 1; display: grid; grid-template-columns: repeat(40, 1fr); align-items: end; gap: 3px; background: linear-gradient(180deg, rgba(99,102,241,0.05), transparent 60%); padding: 8px; border-radius: 8px; }
.bar { background: linear-gradient(180deg, #60a5fa, #3b82f6); border-radius: 2px; }
.legend { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }

.news-card .news-list { display: flex; flex-direction: column; gap: 12px; }
.news-item .title { font-weight: 600; display: flex; align-items: center; gap: 6px; }
.news-item .meta { font-size: 12px; color: var(--el-text-color-secondary); }
.sentiment { font-size: 12px; }
.sentiment.pos { color: #ef4444; }
.sentiment.neu { color: #64748b; }
.sentiment.neg { color: #10b981; }

.facts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.fact { display: flex; flex-direction: column; font-size: 12px; }
.fact b { font-size: 14px; color: var(--el-text-color-primary); }

.quick-actions { display: flex; flex-direction: column; gap: 8px; }

@media (max-width: 1024px) {
  .stats { grid-template-columns: repeat(4, 1fr); }
}
</style>

