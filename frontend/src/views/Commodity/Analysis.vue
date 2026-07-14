<template>
  <div class="commodity-analysis">
    <div class="page-header">
      <h2>📊 大宗商品分析</h2>
      <p class="text-secondary">多智能体决策链 — 4 分析师 → 多空辩论 → 交易员 → 风控 → CIO</p>
    </div>

    <el-row :gutter="24">
      <!-- 左侧:分析表单 -->
      <el-col :span="8">
        <el-card shadow="never" class="form-card">
          <template #header>
            <span><b>🔍 启动新分析</b></span>
          </template>

          <el-form :model="form" label-position="top" size="large">
            <el-form-item label="合约代码" required>
              <el-input v-model="form.full_symbol" placeholder="如 CU2501.SHF / RB2510.SHF" />
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

            <el-form-item label="品种名称(可选)">
              <el-input v-model="form.variety_name" placeholder="如 螺纹钢 / 铜" />
            </el-form-item>

            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="交易所">
                  <el-select v-model="form.exchange" placeholder="自动" clearable style="width: 100%">
                    <el-option label="上期所" value="SHF" />
                    <el-option label="大商所" value="DCE" />
                    <el-option label="郑商所" value="CZCE" />
                    <el-option label="能源中心" value="INE" />
                    <el-option label="广期所" value="GFEX" />
                    <el-option label="中金所" value="CFFEX" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="品类">
                  <el-select v-model="form.category" placeholder="自动" clearable style="width: 100%">
                    <el-option label="有色金属" value="有色金属" />
                    <el-option label="贵金属" value="贵金属" />
                    <el-option label="能源" value="能源" />
                    <el-option label="化工" value="化工" />
                    <el-option label="农产品" value="农产品" />
                    <el-option label="金融" value="金融" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="报价单位">
                  <el-input v-model="form.quote_unit" placeholder="如 元/吨" />
                </el-form-item>
              </el-col>
            </el-row>

            <el-divider />

            <el-form-item label="辩论轮次">
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="多空辩论">
                    <el-slider v-model="form.max_debate_rounds" :min="0" :max="3" :step="1" show-stops />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="风控辩论">
                    <el-slider v-model="form.max_risk_discuss_rounds" :min="0" :max="3" :step="1" show-stops />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form-item>

            <el-button
              type="primary"
              size="large"
              :loading="submitting"
              :disabled="!form.full_symbol.trim()"
              style="width: 100%"
              @click="submitAnalysis"
            >
              {{ submitting ? '分析执行中...' : '🚀 提交分析' }}
            </el-button>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧:结果面板 -->
      <el-col :span="16">
        <el-card v-if="latestResult" shadow="never" class="result-card">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span><b>📋 分析结果 — {{ latestResult.full_symbol }}</b></span>
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
            <el-tab-pane label="📈 技术分析" lazy>
              <div class="report-content">{{ latestResult.market_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="💼 基本面" lazy>
              <div class="report-content">{{ latestResult.fundamentals_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="🧠 持仓情绪" lazy>
              <div class="report-content">{{ latestResult.sentiment_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="📰 新闻" lazy>
              <div class="report-content">{{ latestResult.news_report || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="💼 交易员计划" lazy>
              <div class="report-content">{{ latestResult.trader_investment_plan || '(空)' }}</div>
            </el-tab-pane>
            <el-tab-pane label="🏛️ CIO 决策" lazy>
              <div class="report-content">{{ latestResult.final_decision || '(空)' }}</div>
            </el-tab-pane>
          </el-tabs>
        </el-card>

        <el-card v-if="!latestResult && !reports.length" shadow="never">
          <el-empty description="输入合约代码并提交分析">
            <template #image><div style="font-size: 64px">📈</div></template>
            <p class="text-secondary">
              分析将依次执行:技术分析师 → 基本面分析师 → 持仓分析师 → 新闻分析师<br>
              → 多空辩论 → 交易员决策 → 风控评估 → CIO 最终决策
            </p>
          </el-empty>
        </el-card>

        <el-card v-if="reports.length" shadow="never" style="margin-top: 16px">
          <template #header><span><b>📚 历史报告 ({{ reports.length }})</b></span></template>
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
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { commodityApi } from '@/api/commodity'

const form = ref({
  full_symbol: '',
  trade_date: '',
  variety_name: '',
  exchange: '',
  category: '',
  quote_unit: '',
  max_debate_rounds: 1,
  max_risk_discuss_rounds: 1,
})
const submitting = ref(false)
const latestResult = ref<Record<string, any> | null>(null)
const reports = ref<Array<Record<string, any>>>([])
const detailVisible = ref(false)
const detailData = ref<Record<string, any> | null>(null)

function directionLabel(action?: string): string {
  const map: Record<string, string> = { long: '📈 做多', short: '📉 做空', hold: '⏸️ 持有', flat: '🔒 平仓' }
  return map[action || 'hold'] || action || 'hold'
}
function directionTagType(action?: string): string {
  const map: Record<string, string> = { long: 'success', short: 'danger', hold: 'info', flat: 'warning' }
  return map[action || 'hold']
}
function sectionTitle(key: string): string {
  const map: Record<string, string> = {
    market_report: '📈 技术分析', fundamentals_report: '💼 基本面分析',
    sentiment_report: '🧠 持仓情绪', news_report: '📰 新闻分析',
    investment_plan: '📋 投资计划', trader_investment_plan: '💼 交易员计划',
    final_trade_decision: '🎯 最终交易决策', final_decision: '🏛️ CIO 决策',
  }
  return map[key] || key
}

async function submitAnalysis() {
  if (!form.value.full_symbol.trim()) { ElMessage.warning('请输入合约代码'); return }
  submitting.value = true; latestResult.value = null
  try {
    const res = await commodityApi.submitAnalysis(form.value.full_symbol.trim(), {
      trade_date: form.value.trade_date || undefined,
      variety_name: form.value.variety_name || undefined,
      exchange: form.value.exchange || undefined,
      category: form.value.category || undefined,
      quote_unit: form.value.quote_unit || undefined,
      max_debate_rounds: form.value.max_debate_rounds,
      max_risk_discuss_rounds: form.value.max_risk_discuss_rounds,
    })
    if (res?.success) {
      ElMessage.success(`分析任务已提交: ${res.data?.task_id}`)
      pollForResult(form.value.full_symbol.trim())
    } else { ElMessage.error(res?.message || '提交失败'); submitting.value = false }
  } catch (e: any) { ElMessage.error(e?.message || '提交异常'); submitting.value = false }
}

async function pollForResult(fullSymbol: string) {
  let attempts = 0; const maxAttempts = 60
  const poll = async () => {
    attempts++
    try {
      const res = await commodityApi.getReports(fullSymbol, 1)
      if (res?.data?.reports?.length) {
        latestResult.value = await fetchLatestReport(fullSymbol)
        await loadReports(fullSymbol); submitting.value = false; ElMessage.success('✅ 分析完成!')
        return
      }
    } catch { /* continue polling */ }
    if (attempts < maxAttempts) { setTimeout(poll, 5000) }
    else { submitting.value = false; ElMessage.warning('分析超时,请稍后查看报告列表') }
  }
  setTimeout(poll, 5000)
}

async function fetchLatestReport(fullSymbol: string): Promise<Record<string, any> | null> {
  try {
    const res = await commodityApi.getReports(fullSymbol, 1)
    if (res?.data?.reports?.length) {
      const detail = await commodityApi.getReportDetail(res.data.reports[0].report_id)
      return detail?.data || null
    }
  } catch { /* ignore */ }
  return null
}

async function loadReports(fullSymbol?: string) {
  const sym = fullSymbol || form.value.full_symbol.trim()
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
  if (symbol) { form.value.full_symbol = symbol; loadReports(symbol) }
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
