<template>
  <div class="commodity-analysis">
    <div class="page-header">
      <h2>大宗商品分析</h2>
      <p class="text-secondary">多智能体决策链 — 技术分析师 → 产业分析师 → 持仓情绪分析师 → 新闻分析师 → 推理分析师 → 总结</p>
    </div>

    <el-row :gutter="24">
      <!-- 左侧:分析表单 -->
      <el-col :span="8">
        <el-card shadow="never" class="form-card">
          <el-tabs v-model="activeTab">
            <!-- ===== 单品种分析 Tab ===== -->
            <el-tab-pane label="单品种分析" name="single">
              <el-form :model="form" label-position="top" size="default">
                <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;">
                  <el-button text size="small" @click="clearForm">
                    清空表单
                  </el-button>
                </div>
                <el-row :gutter="12">
                  <el-col :span="12">
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
                  </el-col>
                  <el-col :span="12">
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
                  </el-col>
                </el-row>

                <el-row :gutter="12">
                  <el-col :span="16">
                    <el-form-item label="交易日期">
                      <el-date-picker
                        v-model="form.trade_date"
                        type="date"
                        placeholder="默认当天"
                        style="width: 100%"
                        value-format="YYYY-MM-DD"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="&nbsp;">
                      <el-button
                        type="primary"
                        :loading="submitting"
                        :disabled="submitting || !form.variety_symbol"
                        style="width: 100%"
                        @click="submitAnalysis"
                      >
                        {{ submitting ? '提交中...' : '分析' }}
                      </el-button>
                    </el-form-item>
                  </el-col>
                </el-row>

                <!-- 自定义数据文件上传 -->
                <el-collapse style="margin-top: 8px">
                  <el-collapse-item title="📎 附加数据文件（可选）" name="upload">
                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                      <el-upload
                        ref="uploadRef"
                        :auto-upload="true"
                        :http-request="handleFileUpload"
                        :show-file-list="false"
                        accept=".xlsx,.xls,.csv"
                      >
                        <el-button size="small" plain>
                          <el-icon style="margin-right: 4px"><UploadFilled /></el-icon>选择文件
                        </el-button>
                      </el-upload>
                      <span style="color: #909399; font-size: 12px">支持 .xlsx / .xls / .csv</span>
                    </div>
                    <el-tag
                      v-for="f in uploadedFiles"
                      :key="f.file_id"
                      closable
                      size="small"
                      style="margin: 4px 4px 0 0"
                      @close="removeFile(f.file_id)"
                    >
                      {{ f.original_name }}
                    </el-tag>
                    <el-form-item label="分析技能" style="margin-top: 8px">
                      <el-select
                        v-model="skillName"
                        placeholder="选择分析技能"
                        style="width: 100%"
                        size="small"
                      >
                        <el-option
                          v-for="s in skillOptions"
                          :key="s.name"
                          :label="`${s.title} — ${s.description}`"
                          :value="s.name"
                        />
                      </el-select>
                    </el-form-item>
                    <el-form-item label="数据描述（可选）" style="margin-top: 8px">
                      <el-input
                        v-model="userContext"
                        type="textarea"
                        :rows="2"
                        placeholder="描述文件内容和分析目的，例如：2024 年铜库存与价格数据"
                      />
                    </el-form-item>
                  </el-collapse-item>
                </el-collapse>

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
            </el-tab-pane>

            <!-- ===== 批量分析 Tab ===== -->
            <el-tab-pane label="批量分析" name="batch">
              <el-form label-position="top" size="default">
                <el-form-item label="品种代码（每行一个）">
                  <el-input
                    v-model="batchSymbols"
                    type="textarea"
                    :rows="5"
                    placeholder="CU&#10;RB&#10;I&#10;SA"
                  />
                </el-form-item>
                <el-row :gutter="12">
                  <el-col :span="16">
                    <el-form-item label="交易日期">
                      <el-date-picker
                        v-model="batchTradeDate"
                        type="date"
                        placeholder="默认当天"
                        style="width: 100%"
                        value-format="YYYY-MM-DD"
                      />
                    </el-form-item>
                  </el-col>
                  <el-col :span="8">
                    <el-form-item label="&nbsp;">
                      <el-button
                        type="success"
                        :loading="batchSubmitting"
                        :disabled="batchSubmitting || !batchSymbols.trim()"
                        style="width: 100%"
                        @click="submitBatch"
                      >
                        {{ batchSubmitting ? '提交中…' : '批量提交' }}
                      </el-button>
                    </el-form-item>
                  </el-col>
                </el-row>
                <div v-if="batchResult" style="margin-top: 4px">
                  <el-alert
                    :title="batchResult.message"
                    :type="batchResult.failed > 0 ? 'warning' : 'success'"
                    :closable="false"
                    show-icon
                  >
                    <template #default>
                      <div style="margin-top: 4px; font-size: 13px">
                        成功 {{ batchResult.created }}/{{ batchResult.total }}
                        <el-button text size="small" @click="router.push('/tasks')">查看任务中心</el-button>
                      </div>
                    </template>
                  </el-alert>
                </div>
              </el-form>
            </el-tab-pane>
          </el-tabs>
        </el-card>
      </el-col>

      <!-- 右侧:结果面板 -->
      <el-col :span="16">
        <CommodityReportDetail v-if="latestResult" :data="latestResult" />

        <!-- 无结果时显示自选品种 + 最近分析（与 Dashboard 共享组件） -->
        <template v-if="!latestResult">
          <FavoritesCard compact @select="onFavoriteSelect" />
          <div style="margin-top: 16px;"></div>
          <RecentAnalysesCard compact />
        </template>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { commodityApi, type VarietyItem } from '@/api/commodity'
import type { FavoriteItem } from '@/api/favorites'
import CommodityReportDetail from '@/components/Commodity/CommodityReportDetail.vue'
import FavoritesCard from '@/components/Dashboard/FavoritesCard.vue'
import RecentAnalysesCard from '@/components/Dashboard/RecentAnalysesCard.vue'

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

const activeTab = ref('single')

const submitting = ref(false)
const pollingActive = ref(false)
const progressMessage = ref('')
const lastTaskId = ref('')
const latestResult = ref<Record<string, any> | null>(null)

// 批量分析
const batchSymbols = ref('')
const batchTradeDate = ref('')
const batchSubmitting = ref(false)
const batchResult = ref<Record<string, any> | null>(null)

// 文件上传
const uploadRef = ref<any>(null)
const uploadedFiles = ref<Array<{ file_id: string; original_name: string }>>([])
const userContext = ref('')
const skillName = ref('general-analysis')
const skillOptions = ref<Array<{ name: string; title: string; description: string; content_types: string[] }>>([])

// 品种级联
const loadingVarieties = ref(false)
const varietyOptions = ref<VarietyItem[]>([])
const selectedVarietyName = ref('')

// ---- 文件上传 ----
async function loadSkills() {
  try {
    const res = await commodityApi.listCustomSkills()
    if (res?.data && Array.isArray(res.data)) {
      skillOptions.value = res.data
    }
  } catch { /* ignore */ }
}

async function handleFileUpload(options: any) {
  const { file, onSuccess, onError } = options
  try {
    const res = await commodityApi.uploadCustomData(file)
    const fileInfo = res?.data?.file_id ? res.data : (res?.file_id ? res : null)
    if (fileInfo?.file_id) {
      uploadedFiles.value.push({ file_id: fileInfo.file_id, original_name: fileInfo.original_name || file.name })
      onSuccess?.(fileInfo)
      ElMessage.success(`已上传: ${fileInfo.original_name || file.name}`)
    } else {
      onError?.(new Error('上传失败'))
    }
  } catch (e: any) {
    ElMessage.error(`上传失败: ${e?.message || e}`)
    onError?.(e)
  }
}

function removeFile(fileId: string) {
  uploadedFiles.value = uploadedFiles.value.filter(f => f.file_id !== fileId)
}

// 根据 form 状态计算 fullSymbol (品种代码 + 交易所后缀, 如 CU.SHF)
function computeFullSymbol(): string {
  if (!form.value.exchange || !form.value.variety_symbol) return ''
  const suffix = EXCHANGE_SUFFIX[form.value.exchange] || `.${form.value.exchange}`
  return `${form.value.variety_symbol}${suffix}`
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

// 自选品种点击 → 填入表单（不跳转）
const EXCHANGE_SUFFIX_TO_KEY: Record<string, string> = {
  '.SHF': 'SHFE', '.DCE': 'DCE', '.ZCE': 'CZCE',
  '.INE': 'INE', '.GFEX': 'GFEX', '.CFX': 'CFFEX',
}

async function onFavoriteSelect(item: FavoriteItem) {
  if (item.asset_type !== 'commodity' || !item.full_symbol) return
  const dotIdx = item.full_symbol.lastIndexOf('.')
  if (dotIdx < 0) return
  const variety = item.full_symbol.slice(0, dotIdx).replace(/\d+$/, '')
  const suffix = item.full_symbol.slice(dotIdx)
  const exchange = EXCHANGE_SUFFIX_TO_KEY[suffix] || item.exchange || ''
  if (!exchange) { ElMessage.warning(`无法识别交易所后缀: ${suffix}`); return }

  latestResult.value = null
  form.value.exchange = exchange
  form.value.variety_symbol = ''
  selectedVarietyName.value = item.commodity_name || ''

  await onExchangeChange()
  form.value.variety_symbol = variety
  if (varietyOptions.value.length && !varietyOptions.value.find(v => v.symbol === variety)) {
    // 自选里的品种在交易所列表中找不到（已退市），提示但保留表单
    ElMessage.warning(`品种 ${variety} 不在 ${exchange} 当前列表中，可能已退市`)
  }
  await onVarietyChange()
  ElMessage.success(`已填入: ${variety} (${exchange})`)
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
          ElMessage.success('分析完成!')
        }
        return
      } else if (res.data.status === 'failed') {
        pollingActive.value = false
        progressMessage.value = ''
        ElMessage.error(res.data.progress_message || '分析失败')
        return
      } else {
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
    const params: Record<string, any> = {
      trade_date: form.value.trade_date || undefined,
      variety_name: selectedVarietyName.value || undefined,
      exchange: form.value.exchange || undefined,
    }
    if (uploadedFiles.value.length) {
      params.file_ids = uploadedFiles.value.map(f => f.file_id)
      params.user_context = userContext.value || ''
      params.skill_name = skillName.value || 'general-analysis'
    }
    const res = await commodityApi.submitAnalysis(fullSymbol, params)
    if (res?.success) {
      const tid = res.data?.task_id
      lastTaskId.value = tid || ''
      progressMessage.value = '任务已提交,后台分析中...'
      pollingActive.value = true
      submitting.value = false
      // 任务成功入队 → 重置附加数据 + skill 上下文,品种/交易所不变
      uploadedFiles.value = []
      userContext.value = ''
      skillName.value = 'general-analysis'
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

function clearForm() {
  form.value = { exchange: '', variety_symbol: '', trade_date: '' }
  selectedVarietyName.value = ''
  varietyOptions.value = []
  uploadedFiles.value = []
  userContext.value = ''
  skillName.value = 'general-analysis'
}

onMounted(() => {
  loadSkills()
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
      // 加载该品种最新报告（如存在）
      const sym = symbol.includes('.') ? symbol : `${symbol}0.SHF`
      commodityApi.getReports(sym, 1).then(res => {
        const rpts = res?.data?.reports || []
        if (rpts.length > 0) {
          commodityApi.getReportDetail(rpts[0].report_id).then(res => {
            if (res?.data) latestResult.value = res.data as Record<string, any>
          }).catch(() => {})
        }
      }).catch(() => {})
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
.form-card { border: 1px solid var(--el-border-color-light, #e4e7ed); }
</style>