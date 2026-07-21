<template>
  <div class="commodity-report-detail">
    <!-- 加载态 -->
    <div v-if="loading" class="state-box">
      <el-skeleton :rows="6" animated />
    </div>

    <!-- 空数据 -->
    <div v-else-if="!report" class="state-box">
      <el-empty description="暂无报告数据" />
    </div>

    <!-- 正常渲染 -->
    <template v-else>
      <!-- 顶部摘要卡 -->
      <el-card shadow="never" class="summary-card">
        <el-row :gutter="16" align="middle">
          <el-col :span="4">
            <div class="symbol-badge">
              <span class="symbol-name">{{ varietyDisplay }}</span>
              <span v-if="report.variety_name" class="variety-tag">{{ report.variety_name }}</span>
            </div>
          </el-col>
          <el-col :span="14">
            <el-space>
              <span class="meta-chip">
                <el-icon><Calendar /></el-icon>
                {{ report.trade_date || '—' }}
              </span>
              <span class="meta-chip">
                <el-icon><Clock /></el-icon>
                {{ report.total_time_s ? `${report.total_time_s.toFixed(0)} 秒` : '—' }}
              </span>
              <span v-if="report.exchange" class="meta-chip">
                <el-icon><OfficeBuilding /></el-icon>
                {{ exchangeName(report.exchange) }}
              </span>
            </el-space>
          </el-col>
          <el-col :span="6" style="text-align: right">
            <el-space>
              <el-tag v-if="riskTierDisplay" :type="riskTierTagType(riskTierDisplay)" size="large" effect="dark">
                {{ riskTierDisplay }}
              </el-tag>
              <div v-if="strategyTags.length" style="display: flex; gap: 4px; flex-wrap: wrap; justify-content: flex-end;">
                <el-tag
                  v-for="s in strategyTags"
                  :key="s.name"
                  :type="s.type"
                  size="small"
                  effect="plain"
                >
                  {{ s.name }}
                </el-tag>
              </div>
            </el-space>
          </el-col>
        </el-row>
      </el-card>

      <!-- 合约到期警告 -->
      <el-alert
        v-if="contractExpiryWarning"
        :title="contractExpiryWarning"
        type="warning"
        show-icon
        :closable="false"
        class="expiry-alert"
      />

      <!-- SafetyOverride 高亮（从 report 或 evidence_chain 中提取） -->
      <el-alert
        v-if="safetyOverride"
        :title="safetyOverrideTitle"
        :type="safetyOverrideAlertType"
        show-icon
        :closable="false"
        class="safety-alert"
      >
        <template #default>
          <div class="override-detail">
            <p v-if="safetyOverride.override_reason">
              <strong>原因:</strong> {{ safetyOverride.override_reason }}
            </p>
            <p v-if="safetyOverride.override_rules_triggered?.length">
              <strong>触发的规则:</strong>
              <el-tag
                v-for="(rule, ri) in safetyOverride.override_rules_triggered"
                :key="ri"
                type="danger"
                size="small"
                style="margin-right: 4px"
              >
                {{ rule }}
              </el-tag>
            </p>
            <p v-if="safetyOverride.risk_tier">
              <strong>风险等级:</strong>
              <el-tag :type="riskTierTagType(safetyOverride.risk_tier)" size="small">
                {{ safetyOverride.risk_tier }}
              </el-tag>
            </p>
            <p v-if="safetyOverride.allowed_strategies?.length">
              <strong>允许策略:</strong>
              <el-tag
                v-for="(s, si) in safetyOverride.allowed_strategies"
                :key="si"
                type="success"
                size="small"
                style="margin-right: 4px"
              >
                {{ s }}
              </el-tag>
            </p>
            <p v-if="safetyOverride.forbidden_strategies?.length">
              <strong>禁止策略:</strong>
              <el-tag
                v-for="(s, si) in safetyOverride.forbidden_strategies"
                :key="si"
                type="danger"
                size="small"
                style="margin-right: 4px"
              >
                {{ s }}
              </el-tag>
            </p>
            <p v-if="safetyOverride.strategy_constraints">
              <strong>策略约束说明:</strong> {{ safetyOverride.strategy_constraints }}
            </p>
            <p v-if="hasPositionLimit">
              <strong>仓位上限:</strong> {{ safetyOverride.max_position_pct }}%
              <span v-if="Number(safetyOverride.max_position_pct) === 0">（禁止开仓）</span>
            </p>
            <p v-if="safetyOverride.r5_dimensions?.length">
              <strong>R5 维度:</strong> {{ safetyOverride.r5_dimensions.join('、') }}
            </p>
            <p v-if="hasOriginalOverride" class="override-comparison">
              <strong>原始决策 → 规则覆盖:</strong>
              <span class="override-arrow">
                {{ directionLabel(safetyOverride.original_llm_direction) }}
                / {{ formatConfidence(safetyOverride.original_llm_confidence) }}
                →
                <strong>{{ directionLabel(safetyOverride.overridden_action) }}</strong>
                / {{ formatConfidence(safetyOverride.overridden_confidence) }}
              </span>
            </p>
            <p v-if="safetyOverride.custom_data_conflict || safetyOverride.custom_data_overreliance?.ratio > 0.5" class="override-custom-data">
              <strong>自定义数据审计:</strong>
              <el-tag
                v-if="safetyOverride.custom_data_conflict"
                type="danger"
                size="small"
                style="margin-right: 4px"
              >
                私有数据方向冲突 (私有={{ safetyOverride.custom_data_direction || '中性' }})
              </el-tag>
              <el-tag
                v-if="safetyOverride.custom_data_overreliance?.ratio > 0.5"
                type="warning"
                size="small"
                style="margin-right: 4px"
              >
                CIO 过度依赖用户数据 ({{ Math.round((safetyOverride.custom_data_overreliance?.ratio || 0) * 100) }}%)
              </el-tag>
              <span v-if="safetyOverride.custom_data_as_of" class="custom-data-asof">
                数据截至: {{ safetyOverride.custom_data_as_of }}
              </span>
            </p>
          </div>
        </template>
      </el-alert>

      <!-- 错误消息 -->
      <el-alert
        v-if="report.checks && hasFailChecks"
        :title="'部分检查未通过 — 仅参考'"
        type="warning"
        show-icon
        :closable="false"
        class="checks-alert"
      >
        <template #default>
          <div>
            <el-tag
              v-for="(status, label) in report.checks"
              :key="String(label)"
              :type="status === 'PASS' ? 'success' : 'danger'"
              size="small"
              style="margin-right: 4px; margin-bottom: 4px"
            >
              {{ label }}: {{ status }}
            </el-tag>
          </div>
        </template>
      </el-alert>

      <!-- 主内容: 标签页切换 -->
      <el-tabs v-model="activeTab" type="border-card" class="report-tabs">
        <!-- 证据链: L1→L2→L3 + 风险 + 事实卡片, 完整结构化推理 -->
        <el-tab-pane label="证据链" name="evidence">
          <EvidenceChain :data="report.evidence_chain || null" />
        </el-tab-pane>

        <!-- 分析报告: 分析师 markdown + 策略报告 markdown, 完整文字叙述 -->
        <el-tab-pane label="分析报告" name="reports">
          <!-- 分析师报告 (markdown 全文) -->
          <el-collapse v-model="expandedSections">
            <el-collapse-item
              v-for="section in analystSections"
              :key="section.key"
              :title="section.title"
              :name="section.key"
            >
              <template #title>
                <el-space>
                  <el-tag :type="directionTagType(section.direction)" size="small">
                    {{ directionLabel(section.direction) }}
                  </el-tag>
                  <span>{{ section.title }}</span>
                  <span v-if="section.charCount" class="char-count">{{ section.charCount }} 字</span>
                </el-space>
              </template>
              <div
                v-if="section.content"
                class="md-render"
                v-html="section.rendered"
              />
              <div v-else class="empty-section">
                <el-empty :description="`${section.title} 暂无内容`" :image-size="60" />
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 交易计划（由投研总监策略产出规则派生） -->
          <div v-if="report.final_trade_decision || report.trader_investment_plan" class="trade-container" style="margin-top: 16px">
            <el-card
              v-if="report.final_trade_decision"
              shadow="never"
              class="plan-section trade-decision-card"
            >
              <template #header><b>最终交易决策</b></template>
              <div class="md-render" v-html="renderMarkdown(report.final_trade_decision)" />
            </el-card>
            <el-card v-if="report.trader_investment_plan" shadow="never" class="plan-section">
              <template #header><b>交易计划</b></template>
              <div class="md-render" v-html="renderMarkdown(report.trader_investment_plan)" />
            </el-card>
          </div>

          <!-- 推理分析 fallback: 当 CIO 没有结构化数据时, 渲染 investment_plan markdown -->
          <template v-if="!cioMemo && !parsedPlan && report.investment_plan">
            <el-card shadow="never" class="plan-section" style="margin-top: 16px">
              <template #header><b>推理分析</b></template>
              <div class="md-render" v-html="renderMarkdown(report.investment_plan)" />
            </el-card>
          </template>

          <el-empty
            v-if="!analystSections.some(s => s.content) && !report.final_trade_decision && !report.trader_investment_plan && !report.investment_plan"
            description="暂无分析报告"
            :image-size="60"
            style="margin-top: 24px"
          />
        </el-tab-pane>

        <!-- 原始数据 -->
        <el-tab-pane label="原始数据" name="raw">
          <div class="raw-container">
            <el-alert title="以下为 API 返回的完整 JSON 数据，供调试使用" type="info" :closable="false" show-icon style="margin-bottom: 12px" />
            <pre class="raw-json">{{ formattedRaw }}</pre>
          </div>
        </el-tab-pane>
      </el-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Calendar, Clock, OfficeBuilding } from '@element-plus/icons-vue'
import EvidenceChain from '@/components/Commodity/EvidenceChain.vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  data: Record<string, any> | null
  loading?: boolean
}>()

// ---- 标签页 ----
const activeTab = ref('evidence')
const expandedSections = ref<string[]>([])

watch(() => props.data, () => {
  // 默认展开所有分析师报告
  if (props.data) {
    expandedSections.value = analystSections.value.map(s => s.key)
  }
}, { immediate: true })

// ---- 计算属性 ----
const report = computed(() => props.data || null)

/** 从 report.decision 或 evidence_chain 提取风险等级 */
const riskTierDisplay = computed(() => {
  // 优先 evidence_chain summary
  const ec_summary = report.value?.evidence_chain?.summary
  if (ec_summary?.risk_tier) return ec_summary.risk_tier
  // fallback: report.decision
  return report.value?.decision?.risk_tier || null
})

/** 从 evidence_chain summary 提取策略标签 */
const strategyTags = computed(() => {
  const ec_summary = report.value?.evidence_chain?.summary
  const tags: Array<{ name: string; type: string }> = []
  if (ec_summary?.allowed_strategies?.length) {
    for (const s of ec_summary.allowed_strategies) {
      tags.push({ name: s, type: 'success' })
    }
  }
  if (ec_summary?.forbidden_strategies?.length) {
    for (const s of ec_summary.forbidden_strategies) {
      tags.push({ name: `禁:${s}`, type: 'danger' })
    }
  }
  return tags
})

/** 品种显示: 品种代码 + 中文名，不要主力合约名 */
const varietyDisplay = computed(() => {
  const r = report.value
  if (!r) return '—'
  // 从 full_symbol 提取品种代码 (如 CU0.SHF → CU)
  const sym = r.full_symbol || ''
  const variety = sym.split('.')[0]?.replace(/0$/, '') || sym
  const name = r.variety_name || ''
  return name ? `${variety}（${name}）` : variety
})

const hasFailChecks = computed(() => {
  if (!report.value?.checks) return false
  return Object.values(report.value.checks as Record<string, string>).some(v => v !== 'PASS')
})

// ---- 分析师报告 ----
interface AnalystSection {
  key: string
  title: string
  content: string
  direction: string
  charCount: number
  rendered: string
}

const analystSections = computed<AnalystSection[]>(() => {
  const r = report.value
  if (!r) return []
  // 从报告文本中提取方向关键词
  const extractDirection = (text: string): string => {
    if (!text) return 'info'
    // 从句首综合判断中提取
    const dirMatch = text.match(/\*\*方向\*\*[：:]\s*(\S+)/)
    if (dirMatch) {
      const dir = dirMatch[1]
      if (dir.includes('看多') || dir.includes('做多') || dir.includes('long')) return 'success'
      if (dir.includes('看空') || dir.includes('做空') || dir.includes('short')) return 'danger'
      if (dir.includes('中性') || dir.includes('持有') || dir.includes('hold') || dir.includes('neutral')) return 'info'
    }
    return 'info'
  }
  const sections: Array<{ key: string; title: string; field: string }> = [
    { key: 'market_report', title: '技术分析', field: 'market_report' },
    { key: 'fundamentals_report', title: '基本面分析（估值+驱动）', field: 'fundamentals_report' },
    { key: 'position_report', title: '持仓分析', field: 'position_report' },
    { key: 'news_report', title: '新闻分析', field: 'news_report' },
    { key: 'research_brief', title: '总结', field: 'research_brief' },
  ]

  return sections.map(s => {
    let content = ''
    if (s.field.includes('.')) {
      const [parent, child] = s.field.split('.')
      content = (r as any)[parent]?.[child] || ''
    } else if (s.field === 'research_brief') {
      content = (r as any)['research_brief'] || (r as any)['final_decision'] || ''
    } else {
      content = (r as any)[s.field] || ''
    }
    const direction = s.key === 'research_brief'
      ? (r?.evidence_chain?.summary?.final_action
        ? directionTagType(r.evidence_chain.summary.final_action)
        : 'info')
      : extractDirection(content)
    return {
      key: s.key,
      title: s.title,
      content,
      direction,
      charCount: content.length,
      rendered: renderMarkdown(content),
    }
  }).filter(s => s.content || true) // 保留全部，空内容会显示占位
})

// ---- 投资计划 ----
/** 从可能含多余文字的字符串中尽力提取 JSON */
function extractJsonSafe(raw: string): Record<string, any> | null {
  // 直接解析
  try { return JSON.parse(raw) } catch { /* 继续 */ }

  // 找 {…} 片段
  const braceStart = raw.indexOf('{')
  if (braceStart >= 0) {
    const braceEnd = raw.lastIndexOf('}')
    if (braceEnd > braceStart) {
      try { return JSON.parse(raw.slice(braceStart, braceEnd + 1)) } catch { /* 继续 */ }
    }
  }

  // 找 […] 片段
  const bracketStart = raw.indexOf('[')
  if (bracketStart >= 0) {
    const bracketEnd = raw.lastIndexOf(']')
    if (bracketEnd > bracketStart) {
      try { return JSON.parse(raw.slice(bracketStart, bracketEnd + 1)) } catch { /* 继续 */ }
    }
  }

  return null
}

const parsedPlan = computed(() => {
  const raw = report.value?.investment_plan
  if (!raw) return null
  if (typeof raw === 'object') return raw  // 已是对象
  return extractJsonSafe(raw)
})

// ---- CIO 新结构 (投研备忘录 + 风险评估卡) ----
const cioMemo = computed(() => {
  // 优先从 investment_plan 读取（L2 旧格式兼容）
  if (parsedPlan.value?.['投研备忘录']) return parsedPlan.value['投研备忘录']
  // 回退到 evidence_chain.L3.cio_memo（新格式）
  const l3 = report.value?.evidence_chain?.layers?.L3
  if (l3?.cio_memo && typeof l3.cio_memo === 'object' && Object.keys(l3.cio_memo).length) {
    return l3.cio_memo as Record<string, any>
  }
  return null
})

// ---- SafetyOverride ----
const safetyOverride = computed(() => {
  const so = report.value?.evidence_chain?.layers?.L3?.safety_override
    || report.value?.evidence_chain?.layers?.L3?.risk_card?.safety_override
    || report.value?.evidence_chain?.layers?.L3?.risk_assessment?.safety_override
  // 空对象（后端未写入数据/旧报告）返回 null，不触发 alert
  if (!so || typeof so !== 'object' || !Object.keys(so).length || !so.executed) return null
  return so
})

const hasPositionLimit = computed(() => {
  const value = safetyOverride.value?.max_position_pct
  return value !== undefined && value !== null
})

const hasOriginalOverride = computed(() => {
  const so = safetyOverride.value
  if (!so) return false
  return Boolean(
    so.original_llm_direction !== undefined
    && so.overridden_action !== undefined
    && so.original_llm_direction !== so.overridden_action
  )
})

// ---- 合约到期警告 ----
const contractExpiryWarning = computed(() => {
  const warn = report.value?.contract_expiry_warning
  return warn?.warning || ''
})

const safetyOverrideTitle = computed(() => {
  const audit = safetyOverride.value
  if (!audit) return ''
  if (audit.overridden) return '⚠️ SafetyOverride 风控硬约束已覆盖原始决策'
  if ((audit.override_rules_triggered || []).length) return '⚠️ SafetyOverride 风控规则已触发，原决策符合约束'
  return '✅ SafetyOverride 已执行，未改变原始决策'
})

const safetyOverrideAlertType = computed(() => {
  const audit = safetyOverride.value
  if (!audit?.executed) return 'warning'
  if (audit.overridden || (audit.override_rules_triggered || []).length) return 'warning'
  return 'success'
})

// ---- 原始数据 ----
const formattedRaw = computed(() => {
  try {
    return JSON.stringify(report.value, null, 2)
  } catch {
    return String(report.value)
  }
})

// ---- 辅助函数 ----

function directionLabel(action?: string): string {
  const map: Record<string, string> = {
    long: '做多', short: '做空', hold: '持有', flat: '平仓',
    bullish: '看多', bearish: '看空', neutral: '中性', skip: '跳过',
  }
  return map[action || ''] || action || '—'
}

type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

function directionTagType(action?: string): TagType {
  const map: Record<string, TagType> = {
    long: 'success', short: 'danger', hold: 'info', flat: 'warning',
    bullish: 'success', bearish: 'danger', neutral: 'info', skip: 'info',
  }
  return map[action || ''] || 'info'
}

function formatConfidence(value: unknown): string {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? `${(parsed * 100).toFixed(0)}%` : '—'
}

function exchangeName(code: string): string {
  const map: Record<string, string> = {
    SHF: '上期所', DCE: '大商所', ZCE: '郑商所',
    INE: '能源中心', GFEX: '广期所', CFX: '中金所',
    SHFE: '上期所', CZCE: '郑商所', CFFEX: '中金所',
  }
  return map[code] || code
}

function riskTierTagType(tier: string): TagType {
  const map: Record<string, TagType> = { R1: 'success', R2: 'success', R3: 'warning', R4: 'danger', R5: 'danger' }
  return map[tier] || 'info'
}

</script>

<style scoped lang="scss">
.commodity-report-detail {
  font-size: 14px;
  line-height: 1.6;
}

.state-box {
  padding: 40px 20px;
}

/* 顶部摘要 */
.summary-card {
  margin-bottom: 12px;
  border: 1px solid var(--el-border-color-light, #e4e7ed);
}

.symbol-badge {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.symbol-name {
  font-size: 20px;
  font-weight: 700;
}

.variety-tag {
  font-size: 12px;
  color: #909399;
}

.meta-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #606266;
}

.decision-badge {
  display: flex;
  align-items: center;
}

.action-tag {
  font-size: 14px;
  font-weight: 600;
}

.confidence-text {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

/* SafetyOverride */
.safety-alert,
.expiry-alert {
  margin-bottom: 12px;
}

.override-detail p {
  margin: 4px 0;
}

.override-comparison {
  background: #fdf6ec;
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 3px solid #e6a23c;
}

.override-arrow {
  font-family: 'SF Mono', Consolas, monospace;
  margin-left: 4px;
}

.override-custom-data {
  font-size: 13px;
}

.custom-data-asof {
  color: #909399;
  font-size: 11px;
  margin-left: 4px;
}

/* Checks */
.checks-alert {
  margin-bottom: 12px;
}

/* 标签页 */
.report-tabs {
  :deep(.el-tabs__nav-wrap) {
    padding-left: 16px;
  }
}

/* Markdown 内容 */
.md-render {
  white-space: normal;
  font-size: 14px;
  line-height: 1.8;
  padding: 8px 0;

  :deep(h4.md-h4) {
    margin: 16px 0 8px;
    padding: 6px 10px;
    background: var(--el-color-primary-light-9, #ecf5ff);
    border-radius: 4px;
    font-size: 15px;
    border-left: 3px solid var(--el-color-primary, #409eff);
  }

  :deep(h5.md-h5) {
    margin: 12px 0 6px;
    font-size: 14px;
    color: #606266;
  }

  :deep(code) {
    background: #f4f4f5;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 12px;
    color: #d63200;
  }

  :deep(pre) {
    background: #f5f7fa;
    padding: 12px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.5;
  }

  :deep(table.md-table) {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 13px;
  }

  :deep(table.md-table th) {
    background: #f5f7fa;
    padding: 6px 10px;
    border: 1px solid #e4e7ed;
    font-weight: 600;
  }

  :deep(table.md-table td) {
    padding: 6px 10px;
    border: 1px solid #e4e7ed;
  }

  :deep(strong) {
    font-weight: 600;
  }
}

.empty-section {
  padding: 20px;
}

.char-count {
  font-size: 11px;
  color: #c0c4cc;
}

/* 投资计划 */
.plan-container {
  max-width: 100%;
}

.plan-section {
  margin-bottom: 16px;
}

/* 交易计划 tab */
.trade-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.trade-decision-card {
  border-left: 4px solid var(--el-color-primary, #409eff);
  background: var(--el-fill-color-lighter, #f5f7fa);
}

.trade-decision-card .el-card__header {
  background: var(--el-color-primary-light-9, #ecf5ff);
  border-bottom: 1px solid var(--el-color-primary-light-7, #d9ecff);
}

.trade-decision-card b {
  color: var(--el-color-primary, #409eff);
  font-size: 15px;
}

.cio-scenario {
  .cio-field {
    margin-top: 8px;
    font-size: 13px;
    line-height: 1.6;
  }
}

.cio-perspective-card {
  margin-bottom: 12px;
  font-size: 13px;
}

.bullbear-block {
  margin-bottom: 16px;
}

.bb-title {
  margin: 0 0 8px;
  padding: 6px 10px;
  background: #fdf6ec;
  border-radius: 4px;
  font-size: 14px;
  border-left: 3px solid #e6a23c;
}

.bb-card {
  font-size: 13px;

  p {
    margin: 0 0 8px;
  }
}

.bull-card {
  border-left: 3px solid #67c23a;
}

.bear-card {
  border-left: 3px solid #f56c6c;
}

.refs {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;

  code {
    font-size: 11px;
    color: #909399;
  }
}

.scenario-card {
  margin-bottom: 12px;
  font-size: 13px;
}

.scenario-bull {
  background: #f0f9eb;
}

.scenario-bear {
  background: #fef0f0;
}

.scenario-neutral {
  background: #f4f4f5;
}

.sc-section {
  margin-bottom: 8px;

  ul {
    margin: 4px 0;
    padding-left: 16px;
  }
}

.plan-summary {
  margin-top: 12px;
}

/* 风控 */
.risk-container {
  max-width: 100%;
}

.risk-summary-card {
  text-align: center;
  padding: 16px 0;
}

.risk-comp-label {
  font-size: 13px;
  color: #909399;
  margin-bottom: 8px;
}

.risk-comp-value {
  font-size: 48px;
  font-weight: 800;
}

.risk-l1 { color: #67c23a; }
.risk-l2 { color: #67c23a; }
.risk-l3 { color: #e6a23c; }
.risk-l4 { color: #f56c6c; }
.risk-l5 { color: #f56c6c; }

.dq-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
}

.dq-name {
  font-size: 12px;
  color: #606266;
  min-width: 40px;
}

.dq-rows {
  font-size: 11px;
  color: #c0c4cc;
}

.dq-meta {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}

/* 风险裁定 */
.verdict-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.verdict-label {
  font-size: 12px;
  color: #909399;
}
.verdict-value {
  font-size: 16px;
  font-weight: 600;
  line-height: 32px;
}
.dq-summary-card {
  font-size: 13px;
}

.risk-dim-card {
  text-align: center;
  padding: 8px;
  height: 100%;
}

.risk-dim-0, .risk-dim-1 { border-top: 3px solid #67c23a; }
.risk-dim-2, .risk-dim-3 { border-top: 3px solid #e6a23c; }
.risk-dim-4, .risk-dim-5 { border-top: 3px solid #f56c6c; }

.dim-label {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.dim-tier {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 4px;
}

.dim-desc {
  font-size: 11px;
  color: #909399;
}

.risk-flags-card {
  margin-top: 12px;
}

.ref-tag {
  font-size: 11px;
  color: #409eff;
  margin-right: 4px;
  background: #ecf5ff;
  padding: 1px 4px;
  border-radius: 2px;
}

/* 原始数据 */
.raw-container {
  max-height: 70vh;
  overflow-y: auto;
}

.raw-json {
  font-size: 12px;
  line-height: 1.5;
  background: #f5f7fa;
  padding: 16px;
  border-radius: 4px;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
