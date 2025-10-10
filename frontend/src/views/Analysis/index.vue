<template>
  <div class="analysis-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><TrendCharts /></el-icon>
        股票分析
      </h1>
      <p class="page-description">
        基于AI的智能股票分析系统
      </p>
    </div>

    <el-row :gutter="24">
      <!-- 左侧：分析表单 -->
      <el-col :span="8">
        <el-card class="analysis-form" shadow="never">
          <template #header>
            <h3>📋 分析配置</h3>
          </template>
          
          <el-form
            ref="formRef"
            :model="formData"
            :rules="rules"
            label-width="100px"
            @submit.prevent="handleSubmit"
          >
            <!-- 市场选择 -->
            <el-form-item label="选择市场" prop="market_type">
              <el-select v-model="formData.market_type" @change="handleMarketChange">
                <el-option label="🇺🇸 美股" value="美股" />
                <el-option label="🇨🇳 A股" value="A股" />
                <el-option label="🇭🇰 港股" value="港股" />
              </el-select>
            </el-form-item>

            <!-- 股票代码 -->
            <el-form-item label="股票代码" prop="stock_symbol">
              <el-input
                v-model="formData.stock_symbol"
                :placeholder="getStockPlaceholder()"
                @input="handleStockInput"
                @keyup.enter="handleSubmit"
              >
                <template #prefix>
                  <el-icon><TrendCharts /></el-icon>
                </template>
              </el-input>
              <div class="stock-examples">
                <span class="example-label">示例：</span>
                <el-tag
                  v-for="example in getStockExamples()"
                  :key="example"
                  size="small"
                  class="example-tag"
                  @click="selectExample(example)"
                >
                  {{ example }}
                </el-tag>
              </div>
            </el-form-item>

            <!-- 分析日期 -->
            <el-form-item label="分析日期" prop="analysis_date">
              <el-date-picker
                v-model="formData.analysis_date"
                type="date"
                placeholder="选择分析日期"
                style="width: 100%"
                :disabled-date="disabledDate"
              />
            </el-form-item>

            <!-- 分析类型 -->
            <el-form-item label="分析类型" prop="analysis_type">
              <el-select v-model="formData.analysis_type">
                <el-option label="📊 基础分析" value="basic" />
                <el-option label="🔍 深度分析" value="deep" />
                <el-option label="📈 技术分析" value="technical" />
                <el-option label="📰 新闻分析" value="news" />
                <el-option label="🎯 综合分析" value="comprehensive" />
              </el-select>
            </el-form-item>

            <!-- 高级选项 -->
            <el-form-item>
              <el-collapse v-model="activeCollapse">
                <el-collapse-item title="🔧 高级选项" name="advanced">
                  <el-form-item label="数据源">
                    <el-checkbox-group v-model="formData.data_sources">
                      <el-checkbox label="finnhub">FinnHub</el-checkbox>
                      <el-checkbox label="tushare">Tushare</el-checkbox>
                      <el-checkbox label="akshare">AKShare</el-checkbox>
                    </el-checkbox-group>
                  </el-form-item>
                  
                  <el-form-item label="分析深度">
                    <el-slider
                      v-model="formData.analysis_depth"
                      :min="1"
                      :max="5"
                      :marks="depthMarks"
                      show-stops
                    />
                  </el-form-item>
                  
                  <el-form-item label="包含新闻">
                    <el-switch v-model="formData.include_news" />
                  </el-form-item>
                  
                  <el-form-item label="包含财报">
                    <el-switch v-model="formData.include_financials" />
                  </el-form-item>
                </el-collapse-item>
              </el-collapse>
            </el-form-item>

            <!-- 提交按钮 -->
            <el-form-item>
              <el-button
                type="primary"
                @click="handleSubmit"
                :loading="isAnalyzing"
                :disabled="!canSubmit"
                style="width: 100%"
                size="large"
              >
                <el-icon v-if="!isAnalyzing"><Search /></el-icon>
                {{ isAnalyzing ? '分析中...' : '开始分析' }}
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧：分析结果 -->
      <el-col :span="16">
        <!-- 进度显示 -->
        <el-card v-if="isAnalyzing" class="progress-card" shadow="never">
          <template #header>
            <h3>🔄 分析进度</h3>
          </template>
          
          <div class="progress-content">
            <el-progress
              :percentage="progress.percentage"
              :status="progress.status"
              :stroke-width="8"
            />
            <div class="progress-info">
              <p class="current-step">{{ progress.currentStep }}</p>
              <p class="step-detail">{{ progress.stepDetail }}</p>
            </div>
            
            <!-- 步骤列表 -->
            <el-timeline class="progress-timeline">
              <el-timeline-item
                v-for="(step, index) in progress.steps"
                :key="index"
                :type="getStepType(step.status)"
                :icon="getStepIcon(step.status)"
              >
                <div class="step-content">
                  <h4>{{ step.title }}</h4>
                  <p>{{ step.description }}</p>
                  <span v-if="step.duration" class="step-duration">
                    耗时: {{ step.duration }}ms
                  </span>
                </div>
              </el-timeline-item>
            </el-timeline>
          </div>
        </el-card>

        <!-- 分析结果 -->
        <el-card v-if="analysisResult" class="result-card" shadow="never">
          <template #header>
            <div class="result-header">
              <h3>📊 分析结果</h3>
              <div class="result-actions">
                <el-button size="small" @click="exportResult">
                  <el-icon><Download /></el-icon>
                  导出
                </el-button>
                <el-button size="small" @click="shareResult">
                  <el-icon><Share /></el-icon>
                  分享
                </el-button>
              </div>
            </div>
          </template>
          
          <div class="result-content">
            <!-- 基本信息 -->
            <div class="stock-info">
              <h4>{{ analysisResult.stock_name }} ({{ analysisResult.stock_symbol }})</h4>
              <div class="stock-metrics">
                <el-tag type="success" size="large">
                  当前价格: ¥{{ analysisResult.current_price }}
                </el-tag>
                <el-tag :type="analysisResult.change >= 0 ? 'success' : 'danger'" size="large">
                  {{ analysisResult.change >= 0 ? '+' : '' }}{{ analysisResult.change }}%
                </el-tag>
              </div>
            </div>

            <!-- 分析摘要 -->
            <div class="analysis-summary">
              <h4>📝 分析摘要</h4>
              <p>{{ analysisResult.summary }}</p>
            </div>

            <!-- 详细分析 -->
            <el-tabs v-model="activeTab" class="result-tabs">
              <el-tab-pane label="📊 技术分析" name="technical">
                <div v-html="analysisResult.technical_analysis"></div>
              </el-tab-pane>
              <el-tab-pane label="📰 基本面分析" name="fundamental">
                <div v-html="analysisResult.fundamental_analysis"></div>
              </el-tab-pane>
              <el-tab-pane label="📈 市场情绪" name="sentiment">
                <div v-html="analysisResult.sentiment_analysis"></div>
              </el-tab-pane>
              <el-tab-pane label="🎯 投资建议" name="recommendation">
                <div v-html="analysisResult.recommendation"></div>
              </el-tab-pane>
            </el-tabs>
          </div>
        </el-card>

        <!-- 空状态 -->
        <el-empty
          v-if="!isAnalyzing && !analysisResult"
          description="请在左侧配置分析参数并开始分析"
          :image-size="200"
        />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  TrendCharts,
  Search,
  Download,
  Share,
  Loading,
  Check,
  Close
} from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'

// 响应式数据
const formRef = ref<FormInstance>()
const activeCollapse = ref<string[]>([])
const activeTab = ref('technical')

// 表单数据
const formData = ref({
  market_type: 'A股',
  stock_symbol: '',
  analysis_date: new Date(),
  analysis_type: 'comprehensive',
  data_sources: ['finnhub', 'tushare'],
  analysis_depth: 3,
  include_news: true,
  include_financials: true
})

// 分析状态
const isAnalyzing = ref(false)
const analysisResult = ref(null)

// 进度数据
const progress = ref({
  percentage: 0,
  status: 'active' as 'active' | 'success' | 'exception',
  currentStep: '',
  stepDetail: '',
  steps: [] as Array<{
    title: string
    description: string
    status: 'pending' | 'active' | 'success' | 'error'
    duration?: number
  }>
})

// 表单验证规则
const rules: FormRules = {
  market_type: [{ required: true, message: '请选择市场', trigger: 'change' }],
  stock_symbol: [{ required: true, message: '请输入股票代码', trigger: 'blur' }],
  analysis_date: [{ required: true, message: '请选择分析日期', trigger: 'change' }],
  analysis_type: [{ required: true, message: '请选择分析类型', trigger: 'change' }]
}

// 深度标记（与Web界面保持一致）
const depthMarks = {
  1: '快速',
  2: '基础',
  3: '标准',
  4: '深度',
  5: '全面'
}

// 计算属性
const canSubmit = computed(() => {
  return formData.value.stock_symbol.trim() !== '' && !isAnalyzing.value
})

// 方法
const getStockPlaceholder = () => {
  const placeholders = {
    '美股': '输入美股代码，如 AAPL, TSLA, MSFT',
    'A股': '输入A股代码，如 000001, 600519',
    '港股': '输入港股代码，如 0700.HK, 9988.HK'
  }
  return placeholders[formData.value.market_type] || ''
}

const getStockExamples = () => {
  const examples = {
    '美股': ['AAPL', 'TSLA', 'MSFT', 'GOOGL', 'AMZN'],
    'A股': ['000001', '600519', '000002', '600036', '000858'],
    '港股': ['0700.HK', '9988.HK', '3690.HK', '0941.HK', '1810.HK']
  }
  return examples[formData.value.market_type] || []
}

const selectExample = (example: string) => {
  formData.value.stock_symbol = example
}

const handleMarketChange = () => {
  formData.value.stock_symbol = ''
}

const handleStockInput = (value: string) => {
  if (formData.value.market_type === '美股') {
    formData.value.stock_symbol = value.toUpperCase()
  }
}

const disabledDate = (time: Date) => {
  return time.getTime() > Date.now()
}

const getStepType = (status: string) => {
  const types = {
    'pending': 'info',
    'active': 'primary',
    'success': 'success',
    'error': 'danger'
  }
  return types[status] || 'info'
}

const getStepIcon = (status: string) => {
  const icons = {
    'pending': Loading,
    'active': Loading,
    'success': Check,
    'error': Close
  }
  return icons[status] || Loading
}

const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    
    isAnalyzing.value = true
    analysisResult.value = null
    
    // 初始化进度
    progress.value = {
      percentage: 0,
      status: 'active',
      currentStep: '准备分析...',
      stepDetail: '正在初始化分析参数',
      steps: [
        { title: '数据获取', description: '获取股票基础数据', status: 'pending' },
        { title: '技术分析', description: '进行技术指标分析', status: 'pending' },
        { title: '基本面分析', description: '分析财务数据', status: 'pending' },
        { title: '新闻分析', description: '分析相关新闻', status: 'pending' },
        { title: '生成报告', description: '生成分析报告', status: 'pending' }
      ]
    }

    // 模拟分析过程
    await simulateAnalysis()
    
  } catch (error) {
    ElMessage.error('表单验证失败')
  }
}

const simulateAnalysis = async () => {
  const steps = progress.value.steps
  
  for (let i = 0; i < steps.length; i++) {
    steps[i].status = 'active'
    progress.value.currentStep = steps[i].title
    progress.value.stepDetail = steps[i].description
    progress.value.percentage = ((i + 1) / steps.length) * 100
    
    // 模拟处理时间
    await new Promise(resolve => setTimeout(resolve, 1000 + Math.random() * 2000))
    
    steps[i].status = 'success'
    steps[i].duration = Math.floor(1000 + Math.random() * 2000)
  }
  
  progress.value.status = 'success'
  progress.value.currentStep = '分析完成'
  progress.value.stepDetail = '正在生成分析报告...'
  
  // 模拟分析结果
  setTimeout(() => {
    analysisResult.value = {
      stock_name: '平安银行',
      stock_symbol: formData.value.stock_symbol,
      current_price: '12.45',
      change: 2.34,
      summary: '基于当前市场环境和技术指标分析，该股票呈现积极的投资机会...',
      technical_analysis: '<p>技术分析显示该股票处于上升趋势...</p>',
      fundamental_analysis: '<p>基本面分析表明公司财务状况良好...</p>',
      sentiment_analysis: '<p>市场情绪整体偏向乐观...</p>',
      recommendation: '<p>建议：买入，目标价位 15.00 元</p>'
    }
    isAnalyzing.value = false
  }, 1000)
}

const exportResult = () => {
  ElMessage.info('导出功能开发中...')
}

const shareResult = () => {
  ElMessage.info('分享功能开发中...')
}

// 生命周期
onMounted(() => {
  // 初始化
})
</script>

<style lang="scss" scoped>
.analysis-page {
  .page-header {
    margin-bottom: 24px;

    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 24px;
      font-weight: 600;
      color: var(--el-text-color-primary);
      margin: 0 0 8px 0;
    }

    .page-description {
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }

  .analysis-form {
    .stock-examples {
      margin-top: 8px;
      
      .example-label {
        font-size: 12px;
        color: var(--el-text-color-placeholder);
        margin-right: 8px;
      }
      
      .example-tag {
        margin-right: 4px;
        margin-bottom: 4px;
        cursor: pointer;
        
        &:hover {
          opacity: 0.8;
        }
      }
    }
  }

  .progress-card {
    margin-bottom: 24px;
    
    .progress-content {
      .progress-info {
        margin: 16px 0;
        text-align: center;
        
        .current-step {
          font-size: 16px;
          font-weight: 600;
          margin: 0 0 4px 0;
        }
        
        .step-detail {
          font-size: 14px;
          color: var(--el-text-color-regular);
          margin: 0;
        }
      }
      
      .progress-timeline {
        margin-top: 24px;
        
        .step-content {
          h4 {
            margin: 0 0 4px 0;
            font-size: 14px;
          }
          
          p {
            margin: 0 0 4px 0;
            font-size: 12px;
            color: var(--el-text-color-regular);
          }
          
          .step-duration {
            font-size: 11px;
            color: var(--el-text-color-placeholder);
          }
        }
      }
    }
  }

  .result-card {
    .result-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      
      h3 {
        margin: 0;
      }
      
      .result-actions {
        display: flex;
        gap: 8px;
      }
    }
    
    .result-content {
      .stock-info {
        margin-bottom: 24px;
        
        h4 {
          margin: 0 0 12px 0;
          font-size: 18px;
        }
        
        .stock-metrics {
          display: flex;
          gap: 12px;
        }
      }
      
      .analysis-summary {
        margin-bottom: 24px;
        
        h4 {
          margin: 0 0 12px 0;
        }
        
        p {
          margin: 0;
          line-height: 1.6;
        }
      }
      
      .result-tabs {
        :deep(.el-tab-pane) {
          padding: 16px 0;
        }
      }
    }
  }
}
</style>
