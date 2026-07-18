<template>
  <div class="commodity-analysis">
    <div class="page-header">
      <h2>大宗商品分析</h2>
      <p class="text-secondary">多智能体决策链 — 技术分析师 → 产业分析师 → 持仓情绪分析师 → 新闻分析师 → 推理分析师 → 投研总监</p>
    </div>

    <el-row :gutter="24">
      <!-- 左侧:分析表单 -->
      <el-col :span="8">
        <el-card shadow="never" class="form-card">
          <template #header>
            <span><b>启动新分析</b></span>
          </template>

          <el-form :model="form" label-position="top" size="large">
            <el-form-item label="交易所" required>
              <el-select v-model="form.exchange" placeholder="选择交易所" style="width: 100%" @change="onExchangeChange">
                <el-option label="上期所" value="SHFE" />
                <el-option label="大商所" value="DCE" />
                <el-option label="郑商所" value="CZCE" />
                <el-option label="能源中心" value="INE" />
                <el-option label="广期所" value="GFEX" />
                <el-option label="中金所" value="CFFEX" />
              </el-select>
            </el-form-item>

            <el-form-item label="品种代码" required>
              <el-select
                v-model="form.variety_symbol"
                placeholder="先选交易所"
                style="width: 100%"
                :loading="loadingVarieties"
                :disabled="!form.exchange"
                filterable
                @change="onVarietyChange"
              >
                <el-option
                  v-for="v in varietyOptions"
                  :key="v.symbol"
                  :label="`${v.symbol} - ${v.name}`"
                  :value="v.symbol"
                />
              </el-select>
            </el-form-item>

            <el-form-item label="交易日期">
              <el-date-picker
                v-model="form.trade_date"
                type="date"
                placeholder="默认当天"
                style="width: 100%"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>

            <el-button
              type="primary"
              size="large"
              :loading="submitting"
              :disabled="submitting || !form.variety_symbol"
              style="width: 100%"
              @click="submitAnalysis"
            >
              {{ submitting ? '提交中...' : '提交分析' }}
            </el-button>

            <!-- 分析中进度提示 -->
            <el-alert
              v-if="pollingActive && progressMessage"
              :title="progressMessage"
              type="info"
              :closable="false"
              show-icon
              style="margin-top: 12px"
            />
          </el-form>
        </el-card>

        <!-- 批量分析卡 -->
        <el-card shadow="never" class="form-card" style="margin-top: 16px">
          <template #header>
            <span><b>批量分析</b></span>
          </template>
          <el-form label-position="top" size="large">
            <el-form-item label="品种代码（每行一个）">
              <el-input
                v-model="batchSymbols"
                type="textarea"
                :rows="5"
                placeholder="CU&#10;RB&#10;I&#10;SA"
              />
            </el-form-item>
            <el-form-item label="交易日期">
              <el-date-picker
                v-model="batchTradeDate"
                type="date"
                placeholder="默认当天"
                style="width: 100%"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>
            <el-button
              type="success"
              size="large"
              :loading="batchSubmitting"
              :disabled="batchSubmitting || !batchSymbols.trim()"
              style="width: 100%"
              @click="submitBatch"
            >
              {{ batchSubmitting ? '提交中…' : '批量提交' }}
            </el-button>
            <div v-if="batchResult" style="margin-top: 12px">
              <el-alert
                :title="batchResult.message"
                :type="batchResult.failed > 0 ? 'warning' : 'success'"
                :closable="false"
                show-icon
              >
                <template #default>
                  <div style="margin-top: 4px; font-size: 13px">
                    成功 {{ batchResult.created }}/{{ batchResult.total }}
                    <el-button text size="small" @click="goToTaskCenter">查看任务中心</el-button>
                  </div>
                </template>
              </el-alert>
            </div>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧:结果面板 -->
      <el-col :span="16">
        <el-card v-if="latestResult" shadow="never" class="result-card">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span><b>分析结果 — {{ latestResult.full_symbol }}</b></span>
              <el-tag :type="directionTagType(latestResult.decision?.action)">
                {{ directionLabel(latestResult.decision?.action) }}
              </el-tag>
            </div>
          </template>

          <el-alert
            v-if="latestResult.final_decision"
            :title="latestResult.final_decision.slice(0, 200) + (latestResult.final_decision.length > 200 ? '...' : '')"
            type="success" :closable="false" show-icon style="margin-bottom: 16px"
          />

          <el-tabs>
            <el-tab-pane label="技术分析" lazy>
              <div class="report-content">{{ latestResult.market_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="基本面" lazy>
              <div class="report-content">{{ latestResult.fundamentals_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="持仓情绪" lazy>
              <div class="report-content">{{ latestResult.sentiment_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="新闻" lazy>
              <div class="report-content">{{ latestResult.news_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="投资计划" lazy>
              <div class="report-content">{{ formatInvestmentPlan(latestResult.investment_plan) || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="投研总监" lazy>
              <div class="report-content">{{ latestResult.final_decision || '(空)' }}</div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <el-card v-if="!latestResult && !reports.length" shadow="never">
          <el-empty description="选择品种并提交分析">
            <p class="text-secondary">
              分析将依次执行:技术分析师 → 产业分析师 → 持仓情绪分析师 → 新闻分析师<br>
              → 推理分析师 → 投研总监
            </p>
          </el-empty>
        </el-card>

        <el-card v-if="reports.length" shadow="never" style="margin-top: 16px">
          <template #header><span><b>历史报告 ({{ reports.length }})</b></span></template>
          <el-table :data="reports" stripe style="width: 100%" @row-click="viewReport">
            <el-table-column prop="trade_date" label="日期" width="120" />
            <el-table-column prop="full_symbol" label="合约" width="140" />
            <el-table-column label="方向" width="80">
              <template #default="{ row }">
                <el-tag :type="directionTagType(row.direction)" size="small">{{ directionLabel(row.direction) }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="confidence" label="置信度" width="80">
              <template #default="{ row }">{{ (row.confidence * 100).toFixed(0) }}%</template>
            </el-table-column>
            <el-table-column prop="created_at" label="分析时间" min-width="160" />
          </el-table>
        </el-card>
      </el-col>
    </el-row>

    <el-dialog v-model="detailVisible" title="报告详情" width="80%" top="5vh">
      <div v-if="detailData" class="report-detail">
        <div v-for="(value, key) in detailData" :key="key" class="detail-section">
          <h4 v-if="typeof value === 'string' && value.length > 20">{{ sectionTitle(key) }}</h4>
          <div v-if="typeof value === 'string' && value.length > 20" class="detail-content">{{ value }}</div>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { commodityApi, type VarietyItem } from '@/api/commodity'

const router = useRouter()

// 交易所 → 后缀映射
const EXCHANGE_SUFFIX: Record<string, string> = {
  SHFE: '.SHF',
  DCE: '.DCE',
  CZCE: '.ZCE',
  INE: '.INE',
  GFEX: '.GFEX',
  CFFEX: '.CFX',
}

const form = ref({
  exchange: '',
  variety_symbol: '',
  trade_date: '',
})

const submitting = ref(false)
const pollingActive = ref(false)
const progressMessage = ref('')
const lastTaskId = ref('')
const latestResult = ref<Record<string, any> | null>(null)
const reports = ref<Array<Record<string, any>>>([])
const detailVisible = ref(false)
const detailData = ref<Record<string, any> | null>(null)

// 批量分析
const batchSymbols = ref('')
const batchTradeDate = ref('')
const batchSubmitting = ref(false)
const batchResult = ref<Record<string, any> | null>(null)

// 品种级联
const loadingVarieties = ref(false)
const varietyOptions = ref<VarietyItem[]>([])
const selectedVarietyName = ref('')

// 根据 form 状态计算 fullSymbol (品种代码 + 0 + 交易所后缀, 如 CU0.SHF)
function computeFullSymbol(): string {
  if (!form.value.exchange || !form.value.variety_symbol) return ''
  const suffix = EXCHANGE_SUFFIX[form.value.exchange] || `.${form.value.exchange}`
  return `${form.value.variety_symbol}0${suffix}`
}

function directionLabel(action?: string): string {
  const map: Record<string, string> = { long: '做多', short: '做空', hold: '持有', flat: '平仓' }
  return map[action || 'hold'] || action || 'hold'
}
function directionTagType(action?: string): string {
  const map: Record<string, string> = { long: 'success', short: 'danger', hold: 'info', flat: 'warning' }
  return map[action || 'hold']
}
function formatInvestmentPlan(text: string): string {
  if (!text) return ''
  try { return JSON.stringify(JSON.parse(text), null, 2) }
  catch { return text }
}
function sectionTitle(key: string): string {
  const map: Record<string, string> = {
    market_report: '技术分析', fundamentals_report: '基本面分析',
    sentiment_report: '持仓情绪', news_report: '新闻分析',
    investment_plan: '投资计划', final_decision: '投研总监决策',
  }
  return map[key] || key
}

async function onExchangeChange() {
  form.value.variety_symbol = ''
  varietyOptions.value = []
  selectedVarietyName.value = ''
  if (!form.value.exchange) return
  loadingVarieties.value = true
  try {
    const res = await commodityApi.getVarieties({ exchange: form.value.exchange })
    if (res?.success && res?.data?.items) {
      varietyOptions.value = res.data.items
    }
  } catch { /* ignore */ }
  loadingVarieties.value = false
}

async function onVarietyChange() {
  selectedVarietyName.value = ''
  if (!form.value.variety_symbol) return
  const found = varietyOptions.value.find(v => v.symbol === form.value.variety_symbol)
  selectedVarietyName.value = found?.name || found?.name_cn || form.value.variety_symbol
}

// 轮询
let pollingTimer: ReturnType<typeof setTimeout> | null = null

function stopPolling() {
  if (pollingTimer !== null) {
    clearTimeout(pollingTimer)
    pollingTimer = null
  }
}

function startPolling(taskId: string) {
  let attempts = 0; const maxAttempts = 60
  const poll = async () => {
    attempts++
    try {
      const res = await commodityApi.getTaskStatus(taskId)
      if (!res?.data) { /* continue */ }
      else if (res.data.status === 'completed') {
        pollingActive.value = false
        progressMessage.value = ''
        const detail = await commodityApi.getTaskResult(taskId)
        if (detail?.data) {
          latestResult.value = detail.data as Record<string, any>
          await loadReports()
          ElMessage.success('分析完成!')
        }
        return
      } else if (res.data.status === 'failed') {
        pollingActive.value = false
        progressMessage.value = ''
        ElMessage.error(res.data.progress_message || '分析失败')
        return
      } else {
        // processing — 更新进度信息
        if (res.data.progress_message) {
          progressMessage.value = res.data.progress_message
        }
      }
    } catch { /* continue polling */ }
    if (attempts < maxAttempts) {
      pollingTimer = setTimeout(poll, 5000)
    } else {
      pollingActive.value = false
      progressMessage.value = ''
      ElMessage.warning('分析超时,请稍后查看任务中心')
    }
  }
  pollingTimer = setTimeout(poll, 5000)
}

async function submitAnalysis() {
  const fullSymbol = computeFullSymbol()
  if (!fullSymbol) { ElMessage.warning('请选择品种'); return }

  submitting.value = true
  progressMessage.value = ''
  lastTaskId.value = ''

  try {
    const res = await commodityApi.submitAnalysis(fullSymbol, {
      trade_date: form.value.trade_date || undefined,
      variety_name: selectedVarietyName.value || undefined,
      exchange: form.value.exchange || undefined,
    })
    if (res?.success) {
      const tid = res.data?.task_id
      lastTaskId.value = tid || ''
      progressMessage.value = '任务已提交,后台分析中...'
      pollingActive.value = true
      submitting.value = false // 立即释放按钮,不等后续异步操作
      await loadReports(fullSymbol)
      startPolling(tid)
    } else {
      ElMessage.error(res?.message || '提交失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '提交异常')
  } finally {
    submitting.value = false
  }
}

async function submitBatch() {
  const symbols = batchSymbols.value
    .split('\n')
    .map(s => s.trim())
    .filter(s => s.length > 0)
  if (!symbols.length) { ElMessage.warning('请输入至少一个品种代码'); return }

  batchSubmitting.value = true
  batchResult.value = null
  try {
    const res = await commodityApi.submitBatchAnalysis({
      symbols,
      trade_date: batchTradeDate.value || undefined,
    })
    if (res?.success && res.data) {
      batchResult.value = res.data
      ElMessage.success(`批量提交成功: ${res.data.created}/${res.data.total}`)
    } else {
      ElMessage.error(res?.message || '批量提交失败')
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '批量提交异常')
  } finally {
    batchSubmitting.value = false
  }
}

function goToTaskCenter() {
  router.push('/tasks')
}

async function loadReports(fullSymbol?: string) {
  const sym = fullSymbol || computeFullSymbol()
  if (!sym) return
  try { const res = await commodityApi.getReports(sym, 20); reports.value = res?.data?.reports || [] }
  catch { reports.value = [] }
}

async function viewReport(row: Record<string, any>) {
  try {
    const res = await commodityApi.getReportDetail(row.report_id)
    if (res?.data) { detailData.value = res.data; detailVisible.value = true }
  } catch { ElMessage.error('获取报告详情失败') }
}

onMounted(() => {
  const params = new URLSearchParams(window.location.search)
  const symbol = params.get('symbol')
  if (symbol) {
    const parts = symbol.split('.')
    if (parts.length === 2) {
      const raw = parts[0]
      const suffix = '.' + parts[1]
      const variety = raw.endsWith('0') ? raw.slice(0, -1) : raw
      for (const [ex, sfx] of Object.entries(EXCHANGE_SUFFIX)) {
        if (sfx === suffix) {
          form.value.exchange = ex
          form.value.variety_symbol = variety
          onExchangeChange().then(() => onVarietyChange())
          break
        }
      }
      loadReports(symbol)
    }
  }
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.commodity-analysis { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h2 { margin: 0 0 4px; }
.text-secondary { color: #909399; font-size: 14px; }
.form-card, .result-card { border: 1px solid var(--el-border-color-light, #e4e7ed); }
.report-content {
  white-space: pre-wrap; font-size: 14px; line-height: 1.7;
  max-height: 500px; overflow-y: auto; padding: 8px;
  background: var(--el-fill-color-light, #f5f7fa); border-radius: 4px;
}
.report-detail { max-height: 70vh; overflow-y: auto; }
.detail-section { margin-bottom: 20px; }
.detail-section h4 {
  margin: 0 0 8px; padding: 8px 12px;
  background: var(--el-color-primary-light-9, #ecf5ff); border-radius: 4px; font-size: 15px;
}
.detail-content { white-space: pre-wrap; font-size: 14px; line-height: 1.6; padding: 0 12px; }
</style>