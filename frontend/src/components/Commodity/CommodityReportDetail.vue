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
        <!-- 证据链 -->
        <el-tab-pane label="证据链" name="evidence">
          <EvidenceChain :data="report.evidence_chain || null" />
        </el-tab-pane>

        <!-- 分析师报告 -->
        <el-tab-pane label="分析师报告" name="analysts">
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
        </el-tab-pane>

        <!-- 推理分析（结构化 JSON） -->
        <el-tab-pane label="推理分析" name="plan">
          <!-- CIO 新结构：投研备忘录 + 风险评估卡 -->
          <template v-if="cioMemo">
            <div class="plan-container">
              <!-- 估值审核 -->
              <el-card v-if="cioMemo['估值审核']" shadow="never" class="plan-section">
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
                      <code v-if="row.refId" class="ref-tag">{{ row.refId.replace(/^REF-/i, '') }}</code>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>

              <!-- 情景裁决 -->
              <el-card v-if="cioMemo['情景裁决']" shadow="never" class="plan-section">
                <template #header><b>情景裁决</b></template>
                <div class="cio-scenario">
                  <el-alert
                    v-if="cioMemo['情景裁决']['选定情景']"
                    :title="'选定: ' + cioMemo['情景裁决']['选定情景']"
                    type="success"
                    :closable="false"
                    show-icon
                  />
                  <div v-if="cioMemo['情景裁决']['理由']" class="cio-field">
                    <strong>理由:</strong> {{ cioMemo['情景裁决']['理由'] }}
                  </div>
                  <div v-if="cioMemo['情景裁决']['排除理由']" class="cio-field">
                    <strong>排除理由:</strong> {{ cioMemo['情景裁决']['排除理由'] }}
                  </div>
                </div>
              </el-card>

              <!-- 投研结论 -->
              <el-card v-if="cioConclusion" shadow="never" class="plan-section">
                <template #header><b>投研结论</b></template>
                <el-descriptions :column="2" border size="small">
                  <!-- 方向倾向（LLM 实际输出字段） -->
                  <el-descriptions-item v-if="cioConclusion['方向倾向']" label="方向倾向">
                    <el-tag :type="cioConclusionDirTagType(cioConclusion['方向倾向'])" size="small">
                      {{ cioConclusion['方向倾向'] }}
                    </el-tag>
                  </el-descriptions-item>
                  <!-- 置信度（LLM 实际输出字段） -->
                  <el-descriptions-item v-if="cioConclusion['置信度'] !== undefined" label="置信度">
                    {{ formatConfidence(cioConclusion['置信度']) }}
                  </el-descriptions-item>
                  <!-- 风险等级（prompt 期望字段） -->
                  <el-descriptions-item v-if="cioConclusion['风险等级']" label="风险等级">
                    <el-tag :type="riskTierTagType(cioConclusion['风险等级'] || '')" size="small">
                      {{ cioConclusion['风险等级'] }}
                    </el-tag>
                  </el-descriptions-item>
                  <!-- 核心观点（prompt 期望）/ 核心逻辑（LLM 实际输出） -->
                  <el-descriptions-item label="核心观点" :span="2">
                    {{ cioConclusion['核心观点'] || cioConclusion['核心逻辑'] || '—' }}
                  </el-descriptions-item>
                  <!-- 风险信号（prompt 期望）/ 反向信号（LLM 实际输出） -->
                  <el-descriptions-item v-if="cioConclusionRiskSignals.length" label="风险信号" :span="2">
                    <el-tag
                      v-for="(sig, si) in cioConclusionRiskSignals"
                      :key="si"
                      type="danger"
                      size="small"
                      style="margin-right: 4px; margin-bottom: 4px"
                    >
                      {{ sig }}
                    </el-tag>
                  </el-descriptions-item>
                  <!-- 逆向信号处理（LLM 实际输出） -->
                  <el-descriptions-item v-if="cioConclusion['逆向信号处理']" label="逆向信号处理" :span="2">
                    {{ cioConclusion['逆向信号处理'] }}
                  </el-descriptions-item>
                  <el-descriptions-item label="推荐关注策略">
                    <span v-if="cioConclusion['推荐关注策略']?.length">
                      <el-tag
                        v-for="(s, si) in cioConclusion['推荐关注策略']"
                        :key="si"
                        type="success"
                        size="small"
                        style="margin-right: 4px"
                      >
                        {{ s }}
                      </el-tag>
                    </span>
                    <span v-else>—</span>
                  </el-descriptions-item>
                  <el-descriptions-item label="需规避策略">
                    <span v-if="cioConclusion['需规避策略']?.length">
                      <el-tag
                        v-for="(s, si) in cioConclusion['需规避策略']"
                        :key="si"
                        type="danger"
                        size="small"
                        style="margin-right: 4px"
                      >
                        {{ s }}
                      </el-tag>
                    </span>
                    <span v-else>—</span>
                  </el-descriptions-item>
                  <!-- 硬约束说明（LLM 实际输出） -->
                  <el-descriptions-item v-if="cioConclusion['硬约束说明']" label="硬约束说明" :span="2">
                    <el-tag type="warning" size="small" effect="dark">{{ cioConclusion['硬约束说明'] }}</el-tag>
                  </el-descriptions-item>
                </el-descriptions>
              </el-card>

              <!-- 风险评估卡 -->
              <template v-if="cioRiskCard">
                <el-card shadow="never" class="plan-section">
                  <template #header><b>风险评估卡</b></template>

                  <el-row v-if="cioRiskCard['三方视角']" :gutter="12">
                    <el-col v-for="(v, vk) in cioRiskCard['三方视角']" :key="String(vk)" :span="8">
                      <el-card shadow="never" class="cio-perspective-card">
                        <template #header><b>{{ vk }}</b></template>
                        <div v-if="v['概率权重']" class="cio-field">
                          <strong>概率权重:</strong> {{ (v['概率权重'] * 100).toFixed(0) }}%
                        </div>
                        <div v-if="v['条件']" class="cio-field">
                          <strong>条件:</strong> {{ v['条件'] }}
                        </div>
                      </el-card>
                    </el-col>
                  </el-row>

                  <el-card v-if="cioRiskCard['风险裁定']" shadow="never" style="margin-top: 12px">
                    <template #header><b>风险裁定</b></template>
                    <el-row :gutter="12">
                      <el-col :span="12">
                        <div class="verdict-item">
                          <span class="verdict-label">总体风险等级</span>
                          <el-tag :type="riskTierTagType(cioRiskCard['风险裁定']['总体风险等级'] || '')" size="large" effect="dark">
                            {{ cioRiskCard['风险裁定']['总体风险等级'] || '—' }}
                          </el-tag>
                        </div>
                      </el-col>
                      <el-col :span="12">
                        <div class="verdict-item">
                          <span class="verdict-label">数据充分</span>
                          <el-tag :type="cioRiskCard['风险裁定']['数据充分'] ? 'success' : 'danger'" size="large">
                            {{ cioRiskCard['风险裁定']['数据充分'] ? '✓ 充分' : '✗ 不足' }}
                          </el-tag>
                        </div>
                      </el-col>
                    </el-row>
                    <!-- 数据质量摘要 -->
                    <el-row v-if="cioRiskCard['风险裁定']['数据质量']" :gutter="12" style="margin-top: 12px">
                      <el-col :span="24">
                        <el-card shadow="never" class="dq-summary-card">
                          <template #header><b>数据质量</b></template>
                          <el-row :gutter="8">
                            <el-col v-for="(mod, mk) in cioRiskCard['风险裁定']['数据质量']?.details" :key="String(mk)" :span="8" style="margin-bottom: 8px">
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

                  <div v-if="cioRiskCard['风险提示']?.length" style="margin-top: 12px">
                    <strong>风险提示:</strong>
                    <el-alert
                      v-for="(tip, ti) in cioRiskCard['风险提示']"
                      :key="ti"
                      :title="tip"
                      type="warning"
                      :closable="false"
                      show-icon
                      style="margin-top: 8px"
                    />
                  </div>
                </el-card>
              </el-card>
              </template>
            </div>
          </template>

          <!-- 旧结构兼容：多因子矩阵 / 看涨看跌对照 / 情景推演 -->
          <template v-else-if="parsedPlan">
            <div class="plan-container">
              <el-card v-if="parsedPlan['估值驱动矩阵']" shadow="never" class="plan-section">
                <template #header><b>多因子矩阵</b></template>
                <el-table :data="parsedPlan['估值驱动矩阵']" stripe size="small" border>
                  <el-table-column prop="维度" label="维度" width="90" />
                  <el-table-column prop="当前状态" label="当前状态" min-width="140" show-overflow-tooltip />
                  <el-table-column prop="估值判断" label="估值" width="80">
                    <template #default="{ row }">
                      <el-tag
                        :type="row['估值判断'] === '低估' ? 'success' : row['估值判断'] === '高估' ? 'danger' : 'info'"
                        size="small"
                      >
                        {{ row['估值判断'] }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="驱动方向" label="驱动" width="80">
                    <template #default="{ row }">
                      <el-tag
                        :type="row['驱动方向'] === 'bullish' ? 'success' : row['驱动方向'] === 'bearish' ? 'danger' : 'info'"
                        size="small"
                      >
                        {{ row['驱动方向'] === 'bullish' ? '↑' : row['驱动方向'] === 'bearish' ? '↓' : '→' }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="数据来源" label="引用" min-width="120">
                    <template #default="{ row }">
                      <code v-for="(src, si) in (row['数据来源'] || [])" :key="si" class="ref-tag">
                        {{ typeof src === 'string' ? src.replace(/^REF-/i, '') : src }}
                      </code>
                    </template>
                  </el-table-column>
                </el-table>
              </el-card>

              <el-card v-if="parsedPlan['多空对照表']" shadow="never" class="plan-section">
                <template #header><b>看涨看跌对照</b></template>
                <div v-for="(item, ii) in parsedPlan['多空对照表']" :key="ii" class="bullbear-block">
                  <h5 class="bb-title">{{ item['分歧点'] || item.title || '分歧 ' + (ii + 1) }}</h5>
                  <el-row :gutter="12">
                    <el-col :span="12">
                      <el-card shadow="never" class="bb-card bull-card">
                        <template #header><span style="color: #67c23a">▲ 看涨</span></template>
                        <p>{{ item['看涨逻辑'] || item.bull || '(空)' }}</p>
                        <div v-if="item['看涨引用']?.length" class="refs">
                          <code v-for="(r, ri) in item['看涨引用']" :key="ri">{{ r }}</code>
                        </div>
                      </el-card>
                    </el-col>
                    <el-col :span="12">
                      <el-card shadow="never" class="bb-card bear-card">
                        <template #header><span style="color: #f56c6c">▼ 看跌</span></template>
                        <p>{{ item['看跌逻辑'] || item.bear || '(空)' }}</p>
                        <div v-if="item['看跌引用']?.length" class="refs">
                          <code v-for="(r, ri) in item['看跌引用']" :key="ri">{{ r }}</code>
                        </div>
                      </el-card>
                    </el-col>
                  </el-row>
                </div>
              </el-card>

              <el-card v-if="parsedPlan['三种情景推演']" shadow="never" class="plan-section">
                <template #header><b>情景推演</b></template>
                <el-row :gutter="12">
                  <el-col v-for="(sc, si) in parsedPlan['三种情景推演']" :key="si" :span="8">
                    <el-card
                      :shadow="sc['推演方向'] === '做多' ? 'always' : 'never'"
                      :class="'scenario-card scenario-' + (sc['推演方向'] === '做多' ? 'bull' : sc['推演方向'] === '做空' ? 'bear' : 'neutral')"
                    >
                      <template #header>
                        <el-space>
                          <b>{{ sc['情景名称'] || '情景 ' + (si + 1) }}</b>
                          <el-tag
                            :type="sc['推演方向'] === '做多' ? 'success' : sc['推演方向'] === '做空' ? 'danger' : 'info'"
                            size="small"
                          >
                            {{ sc['推演方向'] }}
                          </el-tag>
                        </el-space>
                      </template>
                      <div v-if="toList(sc['触发条件']).length" class="sc-section">
                        <strong>触发条件:</strong>
                        <ul><li v-for="(c, ci) in toList(sc['触发条件'])" :key="ci">{{ c }}</li></ul>
                      </div>
                      <div v-if="toList(sc['关注焦点']).length" class="sc-section">
                        <strong>关注焦点:</strong>
                        <ul><li v-for="(item, fi) in toList(sc['关注焦点'])" :key="fi">{{ item }}</li></ul>
                      </div>
                      <div v-if="toList(sc['失效条件'] || sc['风险节点']).length" class="sc-section">
                        <strong>失效条件:</strong>
                        <ul><li v-for="(item, ri) in toList(sc['失效条件'] || sc['风险节点'])" :key="ri">{{ item }}</li></ul>
                      </div>
                      <div v-if="sc['置信度']" class="sc-section">
                        <strong>置信度:</strong>
                        <el-progress :percentage="Math.round((sc['置信度'] || 0) * 100)" :stroke-width="14" style="width: 80px; display: inline-block" />
                      </div>
                    </el-card>
                  </el-col>
                </el-row>
                <div v-if="parsedPlan['综合情景判断']" class="plan-summary">
                  <el-alert :title="parsedPlan['综合情景判断']" type="info" :closable="false" show-icon />
                </div>
              </el-card>

              <el-card v-if="parsedPlan['综合情景判断'] && !parsedPlan['三种情景推演']" shadow="never" class="plan-section">
                <template #header><b>综合情景判断</b></template>
                <p>{{ parsedPlan['综合情景判断'] }}</p>
              </el-card>
            </div>
          </template>

          <!-- 纯文本 fallback -->
          <div v-else-if="report.investment_plan" class="md-render" v-html="renderMarkdown(report.investment_plan)" />
          <el-empty v-else description="暂无推理分析" :image-size="60" />
        </el-tab-pane>

        <!-- 交易计划（由投研总监策略产出规则派生） -->
        <el-tab-pane label="交易计划" name="trade">
          <div v-if="report.final_trade_decision || report.trader_investment_plan" class="trade-container">
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
          <el-empty v-else description="暂无交易计划" :image-size="60" />
        </el-tab-pane>

        <!-- 风控评估 -->
        <el-tab-pane label="风控评估" name="risk">
          <div v-if="riskAssessment" class="risk-container">
            <!-- 综合风险等级 -->
            <el-row :gutter="12" style="margin-bottom: 16px">
              <el-col :span="8">
                <el-card shadow="never" class="risk-summary-card">
                  <div class="risk-comp-label">综合风险等级</div>
                  <div class="risk-comp-value" :class="'risk-l' + riskAssessment.composite_risk_level">
                    {{ riskAssessment.composite_risk_level || '—' }}
                  </div>
                </el-card>
              </el-col>
              <el-col v-if="riskAssessment.data_quality" :span="16">
                <el-card shadow="never">
                  <template #header><b>数据质量</b></template>
                  <el-row :gutter="8">
                    <el-col
                      v-for="(mod, mk) in riskAssessment.data_quality?.details"
                      :key="String(mk)"
                      :span="8"
                      style="margin-bottom: 8px"
                    >
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

            <!-- 各维度风控 -->
            <el-row v-if="riskDimensions.length" :gutter="12">
              <el-col
                v-for="dim in riskDimensions"
                :key="dim.key"
                :span="6"
                style="margin-bottom: 12px"
              >
                <el-card shadow="never" :class="'risk-dim-card risk-dim-' + dim.level">
                  <div class="dim-label">{{ dimLabel(dim.key) }}</div>
                  <div class="dim-tier">{{ dim.tier || (dim.available === false ? '无数据' : '未知') }}</div>
                  <div v-if="dim.interpretation" class="dim-desc">{{ dim.interpretation }}</div>
                </el-card>
              </el-col>
            </el-row>

            <!-- 风险标志 -->
            <el-card v-if="riskFlags.length" shadow="never" class="risk-flags-card">
              <template #header><b>风险标志</b></template>
              <el-alert
                v-for="(flag, fi) in riskFlags"
                :key="fi"
                :title="flag.flag || flag.name"
                :type="flag.severity === 'high' ? 'error' : flag.severity === 'medium' ? 'warning' : 'info'"
                show-icon
                :closable="false"
                style="margin-bottom: 8px"
              />
            </el-card>
          </div>
          <el-empty v-else description="暂无风控评估" :image-size="60" />
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
  // 优先从 investment_plan 读取（L2 旧格式兼容）
  if (parsedPlan.value?.['风险评估卡']) return parsedPlan.value['风险评估卡']
  // 回退到 evidence_chain.L3.cio_risk_card（新格式）
  const l3 = report.value?.evidence_chain?.layers?.L3
  if (l3?.cio_risk_card && typeof l3.cio_risk_card === 'object' && Object.keys(l3.cio_risk_card).length) {
    return l3.cio_risk_card as Record<string, any>
  }
  return null
})

const cioConclusionDirType = computed(() => {
  const dir = cioMemo.value?.['投研结论']?.['方向倾向'] || ''
  if (dir.includes('做多')) return 'success'
  if (dir.includes('做空')) return 'danger'
  return 'info'
})

/**
 * 归一化投研结论，兼容 prompt 期望字段名和 LLM 实际输出字段名
 */
const cioConclusion = computed(() => {
  return cioMemo.value?.['投研结论'] || null
})

/** 风险信号：兼容风险信号（prompt 期望）和反向信号（LLM 实际输出） */
const cioConclusionRiskSignals = computed(() => {
  const raw = cioConclusion.value
  if (!raw) return []
  return raw['风险信号'] || raw['反向信号'] || []
})

/** 映射方向倾向到 el-tag type */
function cioConclusionDirTagType(dir: string): string {
  if (dir.includes('做多') || dir.includes('long') || dir.includes('看多')) return 'success'
  if (dir.includes('做空') || dir.includes('short') || dir.includes('看空')) return 'danger'
  if (dir.includes('平仓') || dir.includes('flat')) return 'warning'
  return 'info'
}

// ---- 风控评估 ----
const riskAssessment = computed(() => {
  // 尝试从 evidence_chain 或顶层获取
  return report.value?.risk_assessment
    || report.value?.evidence_chain?.layers?.L3?.risk_assessment
    || null
})

const riskDimensions = computed(() => {
  const dims = riskAssessment.value?.dimensions
  if (!dims || typeof dims !== 'object') return []
  return Object.entries(dims)
    .filter(([, v]) => typeof v === 'object' && v !== null)
    .map(([key, v]: [string, any]) => ({
      key,
      level: v.level || 0,
      tier: v.tier || 'unknown',
      interpretation: v.interpretation || '',
      available: v.available,
      label: v.label,
      sentimentValue: v.value,
    }))
})

const riskFlags = computed(() => {
  return riskAssessment.value?.flags || []
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

/** 统一字段为数组（LLM 有时输出字符串，避免 v-for 逐字渲染） */
function toList(val: unknown): string[] {
  if (Array.isArray(val)) return val.filter((v): v is string => typeof v === 'string')
  if (typeof val === 'string') return [val]
  return []
}

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

function moduleName(key: string): string {
  const map: Record<string, string> = {
    technical: '技术', basis: '基差', inventory: '库存',
    positioning: '持仓', term_structure: '期限结构', news_sentiment: '新闻',
  }
  return map[key] || key
}

function freshnessLabel(days: number | null | undefined): string {
  if (days === null || days === undefined) return '—'
  if (days <= 1) return '今日'
  if (days <= 3) return `${days}天前`
  if (days <= 7) return `${days}天前`
  return `${days}天前 (较旧)`
}

function dimLabel(key: string): string {
  const map: Record<string, string> = {
    volatility: '波动率', basis: '基差', crowding: '拥挤度',
    inventory: '库存', term_structure: '期限结构', oi_divergence: '量价背离',
    news_sentiment: '新闻',
  }
  return map[key] || key
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
.safety-alert {
  margin-bottom: 12px;
}

.override-detail p {
  margin: 4px 0;
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
