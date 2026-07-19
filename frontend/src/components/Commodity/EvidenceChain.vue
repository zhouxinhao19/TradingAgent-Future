<template>
  <div class="evidence-chain">
    <!-- 顶层摘要 -->
    <div v-if="data?.summary" class="chain-summary">
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="summary-item">
            <span class="summary-label">品种</span>
            <span class="summary-value">{{ summaryVarietyDisplay }}</span>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="summary-item">
            <span class="summary-label">分析日期</span>
            <span class="summary-value">{{ data.summary.date }}</span>
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 时间线：分析师报告 -->
    <div class="chain-layer">
      <h3 class="layer-title">
        <el-icon><TrendCharts /></el-icon>
        分析师报告
      </h3>
      <el-timeline>
        <el-timeline-item
          v-for="entry in l1Entries"
          :key="entry.id"
          :timestamp="entry.name"
          :type="entry.direction === 'bullish' || entry.direction === 'long' ? 'success'
                 : entry.direction === 'bearish' || entry.direction === 'short' ? 'danger'
                 : entry.direction === 'skip' ? 'info' : 'warning'"
          placement="top"
        >
          <div class="l1-card">
            <div class="l1-header">
              <el-tag
                :type="directionTagType(entry.direction)"
                size="small"
                effect="dark"
              >
                {{ entry.direction === 'skip' ? '跳过' : directionLabel(entry.direction) }}
              </el-tag>
              <el-tag v-if="entry.status !== 'ok'" :type="statusTagType(entry.status)" size="small">
                {{ statusLabel(entry.status) }}
              </el-tag>
              <span class="confidence-bar">
                置信度: {{ (entry.confidence * 100).toFixed(0) }}%
                <span v-if="entry.calibrated_confidence !== entry.confidence" class="calibrated">
                  (校准后: {{ (entry.calibrated_confidence * 100).toFixed(0) }}%)
                </span>
              </span>
            </div>
            <div v-if="entry.summary" class="l1-summary">{{ entry.summary }}</div>
            <div v-if="entry.signals?.length" class="l1-signals">
              <el-tag
                v-for="(sig, si) in entry.signals"
                :key="si"
                size="small"
                style="margin-right: 4px; margin-bottom: 4px"
              >
                {{ sig }}
              </el-tag>
            </div>
            <div v-if="Object.keys(entry.key_metrics || {}).length" class="l1-metrics">
              <el-descriptions :column="3" size="small" border>
                <el-descriptions-item
                  v-for="(val, mk) in entry.key_metrics"
                  :key="mk"
                  :label="metricLabel(mk)"
                >
                  {{ formatMetric(val) }}
                </el-descriptions-item>
              </el-descriptions>
            </div>
            <div class="l1-id">
              <code>{{ shortenRefId(entry.id) }}</code>
              <span v-if="entry.conclusion_id" class="conclusion-id"> / {{ entry.conclusion_id }}</span>
            </div>
          </div>
        </el-timeline-item>
      </el-timeline>
    </div>

    <!-- 推理分析 + 情景推演 -->
    <div class="chain-layer">
      <h3 class="layer-title">
        <el-icon><DataAnalysis /></el-icon>
        推理分析
        <el-tag v-if="l2Conflict" :type="l2Conflict.type" size="small" style="margin-left: 8px">
          {{ l2Conflict.text }}
        </el-tag>
      </h3>

      <el-collapse v-model="activeL2Panels">
        <!-- 多因子矩阵 -->
        <el-collapse-item v-if="l2Valuation?.length" title="多因子矩阵" name="valuation">
          <el-table :data="l2Valuation" stripe size="small" border>
            <el-table-column prop="维度" label="维度" width="100" />
            <el-table-column prop="当前状态" label="状态" min-width="120" />
            <el-table-column prop="估值判断" label="估值" width="80" />
            <el-table-column prop="驱动方向" label="驱动" width="80">
              <template #default="{ row }">
                <el-tag
                  :type="row['驱动方向'] === 'bullish' ? 'success'
                         : row['驱动方向'] === 'bearish' ? 'danger' : 'info'"
                  size="small"
                >
                  {{ row['驱动方向'] === 'bullish' ? '↑' : row['驱动方向'] === 'bearish' ? '↓' : '→' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="数据来源" label="引用" min-width="160">
              <template #default="{ row }">
                <code
                  v-for="(src, si) in (row['数据来源'] || [])"
                  :key="si"
                  class="ref-link"
                  @click="scrollToL1(src)"
                >
                  {{ shortenRefId(src) }}
                </code>
              </template>
            </el-table-column>
          </el-table>
        </el-collapse-item>

        <!-- 看涨看跌对照 -->
        <el-collapse-item v-if="l2BullBear?.length" title="看涨看跌对照" name="bullbear">
          <div v-for="(item, ii) in l2BullBear" :key="ii" class="bullbear-item">
            <el-alert
              :title="item['分歧点'] || item.title || '关键分歧 ' + (ii + 1)"
              type="warning"
              :closable="false"
              show-icon
              style="margin-bottom: 8px"
            />
            <el-row :gutter="12">
              <el-col :span="12">
                <el-card shadow="never" class="bull-card">
                  <template #header><span style="color: #67c23a">▲ 看涨</span></template>
                  <div>{{ item['看涨逻辑'] || item.bull || '(空)' }}</div>
                </el-card>
              </el-col>
              <el-col :span="12">
                <el-card shadow="never" class="bear-card">
                  <template #header><span style="color: #f56c6c">▼ 看跌</span></template>
                  <div>{{ item['看跌逻辑'] || item.bear || '(空)' }}</div>
                </el-card>
              </el-col>
            </el-row>
          </div>
        </el-collapse-item>

        <!-- 情景推演 -->
        <el-collapse-item v-if="l2Scenarios" title="情景推演" name="scenarios">
          <el-row :gutter="12">
            <el-col
              v-for="(sc, si) in l2ScenarioList"
              :key="si"
              :span="Math.min(8, 24 / l2ScenarioList.length)"
            >
              <el-card
                :shadow="sc['推演方向'] === '做多' ? 'always' : 'never'"
                :class="'scenario-card scenario-' + (sc['推演方向'] === '做多' ? 'bull' : sc['推演方向'] === '做空' ? 'bear' : 'neutral')"
              >
                <template #header>
                  <span>
                    {{ scenarioLabel(sc) }}
                    <el-tag
                      :type="sc['推演方向'] === '做多' ? 'success' : sc['推演方向'] === '做空' ? 'danger' : 'info'"
                      size="small"
                    >
                      {{ sc['推演方向'] }}
                    </el-tag>
                  </span>
                </template>
                <div v-if="toList(sc['触发条件']).length" class="scenario-section">
                  <strong>触发条件:</strong>
                  <ul>
                    <li v-for="(cond, ci) in toList(sc['触发条件'])" :key="ci">{{ cond }}</li>
                  </ul>
                </div>
                <div v-if="toList(sc['关注焦点']).length" class="scenario-section">
                  <strong>关注焦点:</strong>
                  <ul>
                    <li v-for="(foc, fi) in toList(sc['关注焦点'])" :key="fi">{{ foc }}</li>
                  </ul>
                </div>
                <div v-if="toList(sc['失效条件'] || sc['风险节点']).length" class="scenario-section">
                  <strong>失效条件:</strong>
                  <ul>
                    <li v-for="(risk, ri) in toList(sc['失效条件'] || sc['风险节点'])" :key="ri">{{ risk }}</li>
                  </ul>
                </div>
                <div v-if="sc['置信度']" class="scenario-confidence">
                  置信度: <el-progress
                    :percentage="Math.round((sc['置信度'] || 0) * 100)"
                    :stroke-width="14"
                    style="width: 80px; display: inline-block; margin-left: 8px"
                  />
                </div>
              </el-card>
            </el-col>
          </el-row>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 总结 + 风控 -->
    <div class="chain-layer">
      <h3 class="layer-title">
        <el-icon><SetUp /></el-icon>
        总结
      </h3>

      <!-- SafetyOverride 高亮 -->
      <el-alert
        v-if="safetyOverride?.overridden"
        :title="'⚠️ SafetyOverride 风控硬约束已触发'"
        type="error"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #default>
          <div class="override-detail">
            <p><strong>原因:</strong> {{ safetyOverride.override_reason }}</p>
            <p><strong>触发的规则:</strong>
              <el-tag
                v-for="(rule, ri) in (safetyOverride.override_rules_triggered || [])"
                :key="ri"
                type="danger"
                size="small"
                style="margin-right: 4px"
              >
                {{ rule }}
              </el-tag>
            </p>
            <p v-if="safetyOverride.original_llm_direction">
              <strong>LLM 原始方向:</strong> {{ safetyOverride.original_llm_direction }}
              → <strong>覆盖后:</strong> {{ safetyOverride.overridden_action }}
            </p>
            <p v-if="safetyOverride.max_position_pct">
              <strong>仓位上限:</strong> {{ safetyOverride.max_position_pct }}%
            </p>
          </div>
        </template>
      </el-alert>

      <!-- CIO 投研备忘录：估值审核 -->
      <el-card v-if="cioMemo && cioValuationRows.length" shadow="never" style="margin-bottom: 12px">
        <template #header><b>估值审核</b></template>
        <el-table :data="cioValuationRows" stripe size="small" border>
          <el-table-column prop="dimension" label="维度" width="100" />
          <el-table-column prop="judgment" label="判断" width="80">
            <template #default="{ row }">
              <el-tag
                :type="row.judgment === '同意' ? 'success' : row.judgment === '修正' ? 'warning' : 'info'"
                size="small"
              >
                {{ row.judgment }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="reason" label="理由" min-width="240" show-overflow-tooltip />
          <el-table-column prop="refId" label="引用" width="100">
            <template #default="{ row }">
              <code v-if="row.refId" class="ref-link" @click="scrollToL1(row.refId)">{{ shortenRefId(row.refId) }}</code>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- CIO 风险裁定 -->
      <el-card v-if="cioMemo?.情景裁决" shadow="never" style="margin-bottom: 12px">
        <template #header><b>情景裁决</b></template>
        <div class="cio-scenario">
          <el-alert
            v-if="cioMemo['情景裁决']['选定情景']"
            :title="'选定: ' + cioMemo['情景裁决']['选定情景']"
            type="success"
            :closable="false"
            show-icon
          />
          <p v-if="cioMemo['情景裁决']['理由']" style="margin-top: 8px">
            <strong>理由:</strong> {{ cioMemo['情景裁决']['理由'] }}
          </p>
          <p v-if="cioMemo['情景裁决']['排除理由']" style="margin-top: 8px">
            <strong>排除理由:</strong> {{ cioMemo['情景裁决']['排除理由'] }}
          </p>
        </div>
      </el-card>

      <!-- CIO 三方视角 -->
      <el-row v-if="cioRiskCard?.['三方视角']" :gutter="12" style="margin-bottom: 12px">
        <el-col v-for="(v, vk) in cioRiskCard['三方视角']" :key="String(vk)" :span="8">
          <el-card shadow="never" class="cio-perspective-card">
            <template #header><b>{{ vk }}</b></template>
            <div v-if="v['概率权重']"><strong>概率权重:</strong> {{ (v['概率权重'] * 100).toFixed(0) }}%</div>
            <div v-if="v['条件']" style="margin-top: 4px"><strong>条件:</strong> {{ v['条件'] }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- CIO 风险裁定+提示 -->
      <el-card v-if="cioRiskCard?.['风险裁定'] || cioRiskCard?.['风险提示']?.length" shadow="never" style="margin-bottom: 12px">
        <template #header><b>风险裁定</b></template>
        <el-descriptions v-if="cioRiskCard['风险裁定']" :column="2" border size="small">
          <el-descriptions-item v-for="(val, key) in cioRiskCard['风险裁定']" :key="String(key)" :label="String(key)">
            {{ val }}
          </el-descriptions-item>
        </el-descriptions>
        <div v-if="cioRiskCard['风险提示']?.length" style="margin-top: 8px">
          <strong>风险提示:</strong>
          <el-alert v-for="(tip, ti) in cioRiskCard['风险提示']" :key="ti" :title="tip" type="warning" :closable="false" show-icon style="margin-top: 8px" />
        </div>
      </el-card>

      <!-- 量化风险评级 -->
      <el-row v-if="l3RiskKeys.length" :gutter="12" style="margin-bottom: 12px">
        <el-col v-for="key in l3RiskKeys" :key="key" :span="4">
          <el-card shadow="never" :class="'risk-card risk-' + riskLevel(key)">
            <div class="risk-label">{{ riskLabel(key) }}</div>
            <div class="risk-value">{{ riskAssessment[key] }}</div>
            <div v-if="riskDescription(key)" class="risk-desc">{{ riskDescription(key) }}</div>
          </el-card>
        </el-col>
      </el-row>

      <!-- 最终决策文本 -->
      <el-card v-if="l3FinalText" shadow="never">
        <template #header>
          <span>
            <b>最终决策</b>
            <el-tag v-if="data?.summary?.final_action" :type="directionTagType(data.summary.final_action)" size="small" style="margin-left: 8px">
              {{ directionLabel(data.summary.final_action) }}
            </el-tag>
          </span>
        </template>
        <div class="final-decision-text" v-html="renderedFinalDecision" />
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { TrendCharts, DataAnalysis, SetUp } from '@element-plus/icons-vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  data: Record<string, any> | null
}>()

// ---- L1 computed ----
const l1Entries = computed(() => {
  const layers = props.data?.layers
  if (!layers?.L1) return []
  return layers.L1
})

/** 品种显示: 品种代码（中文名），不要合约名 */
const summaryVarietyDisplay = computed(() => {
  const s = props.data?.summary
  if (!s) return ''
  const sym = s.symbol || ''
  const variety = sym.split('.')[0]?.replace(/0$/, '') || sym
  const name = s.variety || ''
  return name ? `${variety}（${name}）` : variety
})

/** 缩短 REF-ID 显示 */
function shortenRefId(id: string): string {
  if (!id || !id.includes('-')) return id || ''
  const parts = id.split('-')
  if (parts.length >= 3) {
    // REF-TECH-a1b2c3d4 → TECH-a1b2c3d4
    return parts.slice(1).join('-')
  }
  return id
}

/** 统一字段为数组（LLM 有时输出字符串，避免 v-for 逐字渲染） */
function toList(val: unknown): string[] {
  if (Array.isArray(val)) return val.filter((v): v is string => typeof v === 'string')
  if (typeof val === 'string') return [val]
  return []
}

// ---- L2 computed ----
const activeL2Panels = ref(['valuation', 'bullbear', 'scenarios'])

const l2Valuation = computed(() => {
  return props.data?.layers?.L2?.valuation_matrix || []
})

const l2BullBear = computed(() => {
  return props.data?.layers?.L2?.bull_bear_table || []
})

const l2Scenarios = computed(() => {
  return props.data?.layers?.L2?.scenarios || {}
})

const l2ScenarioList = computed(() => {
  const s = l2Scenarios.value
  if (Array.isArray(s)) return s
  // 可能是对象 keyed by "保守/基准/乐观"
  const keys = ['保守', '基准', '乐观']
  const list = []
  if (typeof s === 'object' && s !== null) {
    for (const k of keys) {
      if (s[k]) list.push({ ...s[k], _label: k })
      // also try pinyin keys
    }
    // fallback: 取所有 value
    if (!list.length) {
      for (const v of Object.values(s)) {
        if (typeof v === 'object' && v !== null) list.push(v)
      }
    }
  }
  return list
})

const l2Conflict = computed(() => {
  const layers = props.data?.layers
  // 从 L2 原始数据尝试提取 L1_conflict_summary
  const raw = layers?.L2?.raw_summary || ''
  const m = raw.match(/L1 冲突.*?看多=(\d+).*?看空=(\d+)/)
  if (m) {
    const bull = parseInt(m[1])
    const bear = parseInt(m[2])
    if (bull > 0 && bear > 0) return { type: 'warning', text: `分析师冲突: 看多${bull} vs 看空${bear}` }
    if (bull > 0) return { type: 'success', text: `分析师一致看多(${bull})` }
    if (bear > 0) return { type: 'danger', text: `分析师一致看空(${bear})` }
  }
  return null
})

// ---- L3 computed ----
const riskAssessment = computed(() => {
  return props.data?.layers?.L3?.risk_assessment || {}
})

const l3RiskKeys = computed(() => {
  return Object.keys(riskAssessment.value).filter(k => k.startsWith('R') || k.startsWith('r'))
})

const l3FinalText = computed(() => {
  const raw = props.data?.layers?.L3?.final_decision_raw || ''
  // 如果已经是结构化 CIO 数据（含 JSON），不显示原始文本
  if (cioParsed.value) return ''
  return raw.substring(0, 1000)
})

const renderedFinalDecision = computed(() => {
  return renderMarkdown(l3FinalText.value)
})

const safetyOverride = computed(() => {
  return props.data?.layers?.L3?.safety_override || null
})

// ---- CIO 结构化数据（从 L3 cio_memo 或从 final_decision_raw 中解析） ----
function tryParseCIO(raw: string): Record<string, any> | null {
  if (!raw) return null
  // 只尝试解析以 { 开头的 JSON
  const trimmed = raw.trim()
  if (!trimmed.startsWith('{')) return null
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed?.['投研备忘录']) return parsed
    return null
  } catch {
    return null
  }
}

const cioParsed = computed(() => {
  // 优先用后端注入的 L3.cio_memo
  const memo = props.data?.layers?.L3?.cio_memo
  if (memo && typeof memo === 'object' && Object.keys(memo).length > 0) {
    return { '投研备忘录': memo, '风险评估卡': props.data?.layers?.L3?.cio_risk_card }
  }
  // 回退：从 final_decision_raw 解析完整 JSON
  const raw = props.data?.layers?.L3?.final_decision_raw || ''
  return tryParseCIO(raw)
})

const cioMemo = computed(() => {
  return cioParsed.value?.['投研备忘录'] || null
})

const cioValuationRows = computed(() => {
  const v = cioMemo.value?.['估值审核']
  if (!v || typeof v !== 'object') return []
  return Object.entries(v).map(([dim, val]: [string, any]) => ({
    dimension: dim,
    judgment: val['判断'] || '',
    reason: val['理由'] || '',
    refId: val['引用ID'] || '',
  }))
})

const cioRiskCard = computed(() => {
  return cioParsed.value?.['风险评估卡']
    || props.data?.layers?.L3?.cio_risk_card
    || null
})

// ---- 辅助函数 ----
function directionLabel(action?: string): string {
  const map: Record<string, string> = { long: '做多', short: '做空', hold: '持有', flat: '平仓', bullish: '看多', bearish: '看空', neutral: '中性', skip: '跳过' }
  return map[action || 'hold'] || action || 'hold'
}

function directionTagType(action?: string): string {
  const map: Record<string, string> = { long: 'success', short: 'danger', hold: 'info', flat: 'warning', bullish: 'success', bearish: 'danger', neutral: 'info', skip: 'info' }
  return map[action || 'hold']
}

function statusTagType(status?: string): string {
  const map: Record<string, string> = { degraded: 'warning', skipped: 'info' }
  return map[status || ''] || 'info'
}

function statusLabel(status?: string): string {
  const map: Record<string, string> = { degraded: '降级', skipped: '跳过' }
  return map[status || ''] || status || ''
}

function confidenceColor(conf: number): string {
  if (conf >= 0.7) return '#67c23a'
  if (conf >= 0.4) return '#e6a23c'
  return '#f56c6c'
}

function metricLabel(key: string): string {
  const map: Record<string, string> = {
    composite_score: '综合评分', oi_divergence: '量价背离', volatility: '波动率',
    boll_low: '布林下轨', boll_up: '布林上轨',
    basis: '基差', basis_zscore: '基差Z值', inventory_wow: '库存周环比',
    term_structure: '期限结构', roll_yield: '展期收益',
    net_long_change_5d: '净多变化5日', long_short_ratio: '多空比', crowding: '拥挤度',
    sentiment_score: '情感评分', event_count: '事件数',
  }
  return map[key] || key
}

function formatMetric(val: unknown): string {
  if (val === null || val === undefined) return '-'
  if (typeof val === 'number') return val.toFixed(2)
  return String(val)
}

function riskLabel(key: string): string {
  const map: Record<string, string> = { R1: '估值', R2: '库存', R3: '基差', R4: '技术', R5: '宏观' }
  return map[key] || key
}

function riskLevel(key: string): string {
  const v = riskAssessment.value[key]
  if (!v) return 'low'
  if (typeof v === 'number') {
    if (v >= 4) return 'high'
    if (v >= 2) return 'mid'
    return 'low'
  }
  const s = String(v).toLowerCase()
  if (s.includes('高') || s.includes('极') || s.includes('danger')) return 'high'
  if (s.includes('中') || s.includes('warn')) return 'mid'
  return 'low'
}

function riskDescription(key: string): string {
  const maps: Record<string, Record<string, string>> = {
    R1: { '1': '估值极低/安全', '2': '估值偏低', '3': '估值中性', '4': '估值偏高', '5': '估值极高/危险' },
    R2: { '1': '库存极低', '2': '库存偏低', '3': '库存中性', '4': '库存偏高', '5': '库存极高' },
    R3: { '1': '基差极强', '2': '基差偏强', '3': '基差中性', '4': '基差偏弱', '5': '基差极弱' },
    R4: { '1': '技术极强', '2': '技术偏强', '3': '技术中性', '4': '技术偏弱', '5': '技术极弱' },
    R5: { '1': '宏观极利好', '2': '宏观偏利好', '3': '宏观中性', '4': '宏观偏空', '5': '宏观极空' },
  }
  const v = riskAssessment.value[key]
  return maps[key]?.[String(v)] || ''
}

function scenarioLabel(sc: Record<string, any>): string {
  if (sc._label) return `情景: ${sc._label}`
  // try 推演方向
  const dir = sc['推演方向'] || sc.direction || ''
  return `情景: ${dir}`
}

function scrollToL1(refId: string) {
  // 简单的滚动到 L1 区域 — 高亮引用 ID
  const el = document.querySelector(`[data-ref-id="${refId}"]`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
</script>

<style scoped>
.evidence-chain {
  font-size: 14px;
  line-height: 1.6;
}

.chain-summary {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 20px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 16px;
  font-weight: 600;
}

.layer-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 2px solid #e4e7ed;
}

.l1-card {
  padding: 8px 0;
}

.l1-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.confidence-bar {
  font-size: 12px;
  color: #606266;
}

.calibrated {
  color: #e6a23c;
  margin-left: 4px;
}

.l1-summary {
  color: #303133;
  margin-bottom: 6px;
}

.l1-signals {
  margin-bottom: 6px;
}

.l1-metrics {
  margin-bottom: 6px;
}

.l1-id {
  font-size: 11px;
  color: #c0c4cc;
}

.conclusion-id {
  color: #909399;
}

.ref-link {
  cursor: pointer;
  color: #409eff;
  margin-right: 4px;
}

.ref-link:hover {
  text-decoration: underline;
}

.bullbear-item {
  margin-bottom: 16px;
}

.bull-card, .bear-card {
  font-size: 13px;
}

.override-detail p {
  margin: 4px 0;
}

.risk-card {
  text-align: center;
}

.risk-card .risk-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.risk-card .risk-value {
  font-size: 24px;
  font-weight: 700;
}

.risk-card .risk-desc {
  font-size: 11px;
  color: #909399;
  margin-top: 4px;
}

.risk-low { border-left: 3px solid #67c23a; }
.risk-mid { border-left: 3px solid #e6a23c; }
.risk-high { border-left: 3px solid #f56c6c; }

/* CIO 结构化卡片 */
.cio-scenario p {
  margin: 4px 0;
  font-size: 13px;
  line-height: 1.6;
}

.cio-perspective-card {
  margin-bottom: 8px;
  font-size: 13px;
}

.scenario-section {
  margin-bottom: 8px;
  font-size: 13px;
}

.scenario-section ul {
  margin: 4px 0;
  padding-left: 16px;
}

.scenario-card { margin-bottom: 12px; }

.scenario-bull { background: #f0f9eb; }

.scenario-bear { background: #fef0f0; }

.scenario-neutral { background: #f4f4f5; }

.scenario-confidence {
  margin-top: 8px;
  font-size: 13px;
}

.final-decision-text {
  white-space: pre-wrap;
  max-height: 500px;
  overflow-y: auto;
  font-size: 13px;
  line-height: 1.7;
}
</style>
