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
        <el-col :span="6">
          <div class="summary-item">
            <span class="summary-label">风控等级</span>
            <span class="summary-value">
              <el-tag
                v-if="data.summary.risk_tier"
                :type="riskTierTagType(data.summary.risk_tier)"
                size="small"
              >
                {{ data.summary.risk_tier }}
              </el-tag>
              <span v-else>-</span>
            </span>
          </div>
        </el-col>
        <el-col :span="6">
          <div class="summary-item">
            <span class="summary-label">策略约束</span>
            <span class="summary-value" style="font-size:13px">
              <template v-if="data.summary.forbidden_strategies?.length">
                禁止: <el-tag v-for="s in data.summary.forbidden_strategies" :key="s" type="danger" size="small" style="margin-right:2px">{{ s }}</el-tag>
              </template>
              <template v-else-if="data.summary.allowed_strategies?.length">
                <el-tag v-for="s in data.summary.allowed_strategies" :key="s" type="success" size="small" style="margin-right:2px">{{ s }}</el-tag>
              </template>
              <span v-else class="summary-muted">无</span>
            </span>
          </div>
        </el-col>
      </el-row>
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
        <el-collapse-item v-if="l2ScenarioList.length" title="情景推演" name="scenarios">
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

        <!-- 矛盾地图 -->
        <el-collapse-item v-if="contradictionMap.length" title="矛盾地图" name="contradictions">
          <el-alert
            v-for="(item, ci) in contradictionMap"
            :key="ci"
            type="warning"
            :closable="false"
            show-icon
            style="margin-bottom: 8px"
          >
            <template #title>
              {{ item['矛盾'] }}
            </template>
            <div style="display:flex; gap: 16px; margin-top: 8px">
              <div style="flex:1; border-left:3px solid #67c23a; padding-left:8px">
                <strong>▲ 利多:</strong> {{ item['利多'] }}
              </div>
              <div style="flex:1; border-left:3px solid #f56c6c; padding-left:8px">
                <strong>▼ 利空:</strong> {{ item['利空'] }}
              </div>
            </div>
          </el-alert>
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
        v-if="safetyOverride?.executed || safetyOverride?.overridden"
        :title="safetyOverrideTitle"
        :type="safetyOverrideAlertType"
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
          </div>
        </template>
      </el-alert>

      <!-- 策略适应性矩阵 -->
      <el-card v-if="strategyMatrix.length" shadow="never" style="margin-bottom: 12px">
        <template #header><b>策略适应性矩阵（量化规则）</b></template>
        <el-table :data="strategyMatrix" stripe size="small" border>
          <el-table-column prop="strategy" label="策略" width="110" />
          <el-table-column prop="fitness" label="适应性" width="100">
            <template #default="{ row }">
              <el-tag :type="fitnessTagType(row.fitness)" size="small">
                {{ row.fitness }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="rationale" label="核心判据" min-width="240" />
          <el-table-column label="关键条件" min-width="180">
            <template #default="{ row }">
              <div
                v-for="(cond, ci) in (row.key_conditions || [])"
                :key="ci"
                :style="{ color: cond.includes('✗') ? '#f56c6c' : cond.includes('⚠') ? '#e6a23c' : '#67c23a', fontSize: '12px' }"
              >
                {{ cond }}
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
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
        <template v-if="cioRiskCard['风险裁定']">
          <el-row :gutter="12" style="margin-bottom: 12px">
            <el-col :span="6">
              <div class="verdict-item">
                <span class="verdict-label">总体风险等级</span>
                <el-tag :type="riskTierTagType(cioRiskCard['风险裁定']['总体风险等级'] || '')" size="large" effect="dark">
                  {{ cioRiskCard['风险裁定']['总体风险等级'] || '—' }}
                </el-tag>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="verdict-item">
                <span class="verdict-label">数据充分</span>
                <el-tag :type="cioRiskCard['风险裁定']['数据充分'] ? 'success' : 'danger'" size="large">
                  {{ cioRiskCard['风险裁定']['数据充分'] ? '✓ 充分' : '✗ 不足' }}
                </el-tag>
              </div>
            </el-col>
            <el-col :span="4">
              <div class="verdict-item">
                <span class="verdict-label">建议动作</span>
                <el-tag :type="cioRiskCard['风险裁定']['建议动作'] === '平仓' ? 'warning' : 'success'" size="large">
                  {{ cioRiskCard['风险裁定']['建议动作'] || '—' }}
                </el-tag>
              </div>
            </el-col>
            <el-col :span="5">
              <div class="verdict-item">
                <span class="verdict-label">仓位上限</span>
                <span class="verdict-value">{{ cioRiskCard['风险裁定']['仓位上限'] ?? '—' }}%</span>
              </div>
            </el-col>
            <el-col :span="5">
              <div class="verdict-item">
                <span class="verdict-label">杠杆上限</span>
                <span class="verdict-value">{{ cioRiskCard['风险裁定']['杠杆上限'] ?? '—' }}x</span>
              </div>
            </el-col>
          </el-row>
          <!-- 数据质量摘要 -->
          <el-row v-if="cioRiskCard['风险裁定']['数据质量']" :gutter="12" style="margin-bottom: 12px">
            <el-col :span="24">
              <el-card shadow="never" class="dq-summary-card">
                <template #header><b>数据质量</b></template>
                <el-row :gutter="8">
                  <el-col v-for="(mod, mk) in dqDetails" :key="String(mk)" :span="8" style="margin-bottom: 8px">
                    <div class="dq-item">
                      <span class="dq-name">{{ moduleName(String(mk)) }}</span>
                      <el-progress
                        :percentage="Math.round((mod.coverage || 0) * 100)"
                        :stroke-width="14"
                        :status="mod.available ? 'success' : 'exception'"
                        :text-inside="true"
                        style="width: 100px"
                      />
                      <span class="dq-meta">{{ mod.rows }}行 · {{ freshnessLabel(mod.freshness_days) }}</span>
                    </div>
                  </el-col>
                </el-row>
              </el-card>
            </el-col>
          </el-row>
          <!-- 允许/禁止策略 -->
          <el-row v-if="cioRiskCard['风险裁定']['允许策略']?.length || cioRiskCard['风险裁定']['禁止策略']?.length" :gutter="12" style="margin-bottom: 12px">
            <el-col v-if="cioRiskCard['风险裁定']['允许策略']?.length" :span="12">
              <strong>允许策略:</strong>
              <el-tag v-for="s in cioRiskCard['风险裁定']['允许策略']" :key="s" type="success" size="small" style="margin-right: 4px">{{ s }}</el-tag>
            </el-col>
            <el-col v-if="cioRiskCard['风险裁定']['禁止策略']?.length" :span="12">
              <strong>禁止策略:</strong>
              <el-tag v-for="s in cioRiskCard['风险裁定']['禁止策略']" :key="s" type="danger" size="small" style="margin-right: 4px">{{ s }}</el-tag>
            </el-col>
          </el-row>
          <div v-if="cioRiskCard['风险裁定']['策略约束说明']" class="verdict-constraint">
            <el-alert :title="cioRiskCard['风险裁定']['策略约束说明']" type="warning" :closable="false" show-icon />
          </div>
        </template>
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

      <!-- 策略适应性报告（替代最终决策） -->
      <el-card v-if="l3FinalText" shadow="never">
        <template #header>
          <span>
            <b>策略适应性报告</b>
            <el-tag
              v-if="data?.summary?.risk_tier"
              :type="riskTierTagType(data.summary.risk_tier)"
              size="small"
              style="margin-left: 8px"
            >
              {{ data.summary.risk_tier }}
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
import { DataAnalysis, SetUp } from '@element-plus/icons-vue'
import { renderMarkdown } from '@/utils/markdown'

const props = defineProps<{
  data: Record<string, any> | null
}>()

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
    return parts.slice(1).join('-')
  }
  return id
}

/** 统一字段为数组 */
function toList(val: unknown): string[] {
  if (Array.isArray(val)) return val.filter((v): v is string => typeof v === 'string')
  if (typeof val === 'string') return [val]
  return []
}

const activeL2Panels = ref(['valuation', 'bullbear', 'scenarios', 'contradictions'])

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
  if (Array.isArray(s)) return s.filter(isScenarioObject)
  // 可能是对象 keyed by "保守/基准/乐观"
  const keys = ['保守', '基准', '乐观']
  const list = []
  if (typeof s === 'object' && s !== null) {
    for (const k of keys) {
      if (s[k]) list.push({ ...s[k], _label: k })
    }
    // fallback: 取所有 value，过滤掉非情景对象（如数组、字符串）
    if (!list.length) {
      for (const v of Object.values(s)) {
        if (isScenarioObject(v)) list.push(v)
      }
    }
  }
  return list
})

/** 判断是否为有效的情景对象（有推演方向或情景名称等字段） */
function isScenarioObject(v: unknown): v is Record<string, any> {
  return typeof v === 'object' && v !== null && !Array.isArray(v) &&
    (typeof (v as any)['推演方向'] === 'string' || typeof (v as any)['情景名称'] === 'string')
}

const l2Conflict = computed<{ type: TagType; text: string } | null>(() => {
  const layers = props.data?.layers
  // 从 contradiction_map 判断是否存在矛盾
  const cm = layers?.L2?.contradiction_map
  if (Array.isArray(cm) && cm.length) {
    return { type: 'warning', text: `存在 ${cm.length} 组矛盾信号` }
  }
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

// ---- 策略矩阵 + 矛盾地图 computed ----
const strategyMatrix = computed(() => {
  return props.data?.layers?.L3?.strategy_matrix || []
})

const contradictionMap = computed(() => {
  return props.data?.layers?.L2?.contradiction_map || props.data?.layers?.L3?.contradiction_map || []
})

// ---- L3 computed ----
const riskAssessment = computed(() => {
  return props.data?.layers?.L3?.risk_assessment || {}
})

const l3RiskKeys = computed(() => {
  return Object.keys(riskAssessment.value).filter(k => k.startsWith('R') || k.startsWith('r'))
})

const l3FinalText = computed(() => {
  const raw = props.data?.layers?.L3?.research_brief_raw || props.data?.layers?.L3?.final_decision_raw || ''
  // 如果已经是结构化 CIO 数据（含 JSON），不显示原始文本
  if (cioParsed.value) return ''
  return raw.substring(0, 2000)
})

const renderedFinalDecision = computed(() => {
  return renderMarkdown(l3FinalText.value)
})

const safetyOverride = computed(() => {
  const so = props.data?.layers?.L3?.safety_override
  // 空对象（后端未写入数据/旧报告）返回 null，不触发 alert
  if (!so || typeof so !== 'object' || !Object.keys(so).length || !so.executed) return null
  return so
})

const hasPositionLimit = computed(() => {
  const value = safetyOverride.value?.max_position_pct
  return value !== undefined && value !== null
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
  if (audit?.overridden || (audit?.override_rules_triggered || []).length) return 'warning'
  return 'success'
})

function formatConfidence(value: unknown): string {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? `${(parsed * 100).toFixed(0)}%` : '—'
}

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

// ---- 数据质量辅助 ----
const dqDetails = computed(() => {
  const dq = cioRiskCard.value?.['风险裁定']?.['数据质量']?.details
  if (!dq || typeof dq !== 'object') return {}
  return dq
})

function moduleName(key: string): string {
  const names: Record<string, string> = {
    technical: '技术分析',
    basis: '基差分析',
    inventory: '库存分析',
    positioning: '持仓分析',
    term_structure: '期限结构',
    news_sentiment: '新闻情绪',
  }
  return names[key] || key
}

function freshnessLabel(days: number | null | undefined): string {
  if (days === null || days === undefined) return '—'
  if (days <= 1) return '今日'
  if (days <= 3) return `${days}天前`
  if (days <= 7) return `${days}天前`
  return `${days}天前 (较旧)`
}

// ---- 辅助函数 ----
type TagType = 'primary' | 'success' | 'warning' | 'info' | 'danger'

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

function riskTierTagType(tier: string): TagType {
  const map: Record<string, TagType> = { R1: 'success', R2: 'success', R3: 'warning', R4: 'danger', R5: 'danger' }
  return map[tier] || 'info'
}

function fitnessTagType(fitness: string): TagType {
  const map: Record<string, TagType> = { '推荐关注': 'success', '谨慎推荐': 'warning', '不推荐': 'danger', '数据不足': 'info' }
  return map[fitness] || 'info'
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
.verdict-constraint {
  margin-top: 8px;
}
.dq-summary-card {
  font-size: 13px;
}
.dq-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.dq-name {
  min-width: 60px;
  font-weight: 500;
  white-space: nowrap;
}
.dq-meta {
  font-size: 11px;
  color: #909399;
  white-space: nowrap;
}
</style>
