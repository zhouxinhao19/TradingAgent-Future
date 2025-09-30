<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? '编辑数据源' : '添加数据源'"
    width="600px"
    @update:model-value="$emit('update:visible', $event)"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="120px"
      label-position="left"
    >
      <!-- 基本信息 -->
      <el-form-item label="数据源名称" prop="name">
        <el-input
          v-model="formData.name"
          placeholder="请输入数据源名称"
          :disabled="isEdit"
        />
      </el-form-item>

      <el-form-item label="显示名称" prop="display_name">
        <el-input
          v-model="formData.display_name"
          placeholder="请输入显示名称"
        />
      </el-form-item>

      <el-form-item label="数据源类型" prop="type">
        <el-select
          v-model="formData.type"
          placeholder="请选择数据源类型"
          style="width: 100%"
        >
          <el-option
            v-for="option in dataSourceTypes"
            :key="option.value"
            :label="option.label"
            :value="option.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="数据提供商" prop="provider">
        <el-input
          v-model="formData.provider"
          placeholder="请输入数据提供商"
        />
      </el-form-item>

      <!-- 连接配置 -->
      <el-divider content-position="left">连接配置</el-divider>

      <el-form-item label="API端点" prop="endpoint">
        <el-input
          v-model="formData.endpoint"
          placeholder="请输入API端点URL"
        />
      </el-form-item>

      <el-alert
        title="🔒 安全提示"
        type="info"
        description="敏感密钥通过环境变量/运维配置注入；此处不保存或显示真实密钥。"
        show-icon
        :closable="false"
      />

      <!-- 性能配置 -->
      <el-divider content-position="left">性能配置</el-divider>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="超时时间" prop="timeout">
            <el-input-number
              v-model="formData.timeout"
              :min="1"
              :max="300"
              controls-position="right"
              style="width: 100%"
            />
            <span class="form-help">秒</span>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="速率限制" prop="rate_limit">
            <el-input-number
              v-model="formData.rate_limit"
              :min="1"
              :max="10000"
              controls-position="right"
              style="width: 100%"
            />
            <span class="form-help">请求/分钟</span>
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="优先级" prop="priority">
        <el-input-number
          v-model="formData.priority"
          :min="0"
          :max="100"
          controls-position="right"
          style="width: 200px"
        />
        <span class="form-help">数值越大优先级越高</span>
      </el-form-item>

      <!-- 市场分类 -->
      <el-divider content-position="left">市场分类</el-divider>

      <el-form-item label="所属市场" prop="market_categories">
        <el-checkbox-group v-model="formData.market_categories">
          <el-checkbox
            v-for="category in marketCategories"
            :key="category.id"
            :label="category.id"
            :disabled="!category.enabled"
          >
            {{ category.display_name }}
          </el-checkbox>
        </el-checkbox-group>
      </el-form-item>

      <!-- 高级设置 -->
      <el-divider content-position="left">高级设置</el-divider>

      <el-form-item label="启用状态">
        <el-switch v-model="formData.enabled" />
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="3"
          placeholder="请输入数据源描述"
        />
      </el-form-item>

      <!-- 自定义参数 -->
      <el-form-item label="自定义参数">
        <div class="config-params">
          <div
            v-for="(value, key, index) in formData.config_params"
            :key="index"
            class="param-item"
          >
            <el-input
              v-model="paramKeys[index]"
              placeholder="参数名"
              style="width: 40%"
              @blur="updateParamKey(index, paramKeys[index])"
            />
            <el-input
              v-model="formData.config_params[key]"
              placeholder="参数值"
              style="width: 40%; margin-left: 8px"
            />
            <el-button
              type="danger"
              size="small"
              icon="Delete"
              style="margin-left: 8px"
              @click="removeParam(key)"
            />
          </div>
          <el-button
            type="primary"
            size="small"
            icon="Plus"
            @click="addParam"
          >
            添加参数
          </el-button>
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          {{ isEdit ? '更新' : '创建' }}
        </el-button>
        <el-button
          v-if="formData.name"
          type="success"
          :loading="testing"
          @click="handleTest"
        >
          测试连接
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { 
  configApi, 
  type DataSourceConfig, 
  type MarketCategory,
  DEFAULT_DATA_SOURCE_CONFIG 
} from '@/api/config'

// Props
interface Props {
  visible: boolean
  config?: DataSourceConfig | null
}

const props = withDefaults(defineProps<Props>(), {
  config: null
})

// Emits
const emit = defineEmits<{
  'update:visible': [value: boolean]
  'success': []
}>()

// Refs
const formRef = ref<FormInstance>()
const loading = ref(false)
const testing = ref(false)
const marketCategories = ref<MarketCategory[]>([])

// Computed
const isEdit = computed(() => !!props.config)

// 表单数据
const defaultFormData = {
  name: '',
  display_name: '',
  type: '',
  provider: '',
  api_key: '',
  api_secret: '',
  endpoint: '',
  timeout: 30,
  rate_limit: 100,
  enabled: true,
  priority: 0,
  config_params: {} as Record<string, any>,
  description: '',
  market_categories: [] as string[]
}

const formData = ref({ ...defaultFormData })
const paramKeys = ref<string[]>([])

// 数据源类型选项
const dataSourceTypes = [
  { label: 'AKShare', value: 'akshare' },
  { label: 'Tushare', value: 'tushare' },
  { label: 'Yahoo Finance', value: 'yahoo' },
  { label: 'Alpha Vantage', value: 'alphavantage' },
  { label: 'Quandl', value: 'quandl' },
  { label: 'IEX Cloud', value: 'iex' },
  { label: 'Finnhub', value: 'finnhub' },
  { label: '自定义', value: 'custom' }
]

// 表单验证规则
const rules: FormRules = {
  name: [{ required: true, message: '请输入数据源名称', trigger: 'blur' }],
  display_name: [{ required: true, message: '请输入显示名称', trigger: 'blur' }],
  type: [{ required: true, message: '请选择数据源类型', trigger: 'change' }],
  timeout: [{ required: true, message: '请输入超时时间', trigger: 'blur' }],
  rate_limit: [{ required: true, message: '请输入速率限制', trigger: 'blur' }],
  priority: [{ required: true, message: '请输入优先级', trigger: 'blur' }]
}

// 自定义参数管理
const addParam = () => {
  const newKey = `param_${Object.keys(formData.value.config_params).length + 1}`
  formData.value.config_params[newKey] = ''
  paramKeys.value.push(newKey)
}

const removeParam = (key: string) => {
  delete formData.value.config_params[key]
  const index = paramKeys.value.indexOf(key)
  if (index > -1) {
    paramKeys.value.splice(index, 1)
  }
}

const updateParamKey = (index: number, newKey: string) => {
  const oldKey = paramKeys.value[index]
  if (oldKey !== newKey && newKey.trim()) {
    const value = formData.value.config_params[oldKey]
    delete formData.value.config_params[oldKey]
    formData.value.config_params[newKey] = value
    paramKeys.value[index] = newKey
  }
}

// 加载市场分类
const loadMarketCategories = async () => {
  try {
    marketCategories.value = await configApi.getMarketCategories()
  } catch (error) {
    console.error('加载市场分类失败:', error)
    ElMessage.error('加载市场分类失败')
  }
}

// 监听配置变化
watch(
  () => props.config,
  (config) => {
    if (config) {
      // 编辑模式：合并默认值和传入的配置
      formData.value = {
        ...defaultFormData,
        ...config,
        market_categories: config.market_categories || []
      }
      // 初始化参数键列表
      paramKeys.value = Object.keys(config.config_params || {})
    } else {
      // 新增模式：使用默认值
      formData.value = { ...defaultFormData }
      paramKeys.value = []
    }
  },
  { immediate: true }
)

// 监听visible变化
watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      loadMarketCategories()
      if (props.config) {
        // 编辑模式
        formData.value = {
          ...defaultFormData,
          ...props.config,
          market_categories: props.config.market_categories || []
        }
        paramKeys.value = Object.keys(props.config.config_params || {})
      } else {
        // 新增模式
        formData.value = { ...defaultFormData }
        paramKeys.value = []
      }
    }
  }
)

// 处理关闭
const handleClose = () => {
  emit('update:visible', false)
}

// 处理提交
const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    loading.value = true

    // 方案A：前端不提交敏感字段
    const payload: any = { ...formData.value }
    delete payload.api_key
    delete payload.api_secret

    if (isEdit.value) {
      // 更新数据源
      await configApi.updateDataSourceConfig(formData.value.name, payload)
      ElMessage.success('数据源更新成功')
    } else {
      // 创建数据源
      await configApi.addDataSourceConfig(payload)
      ElMessage.success('数据源创建成功')
    }

    emit('success')
    handleClose()
  } catch (error) {
    console.error('保存数据源失败:', error)
    ElMessage.error('保存数据源失败')
  } finally {
    loading.value = false
  }
}

// 处理测试连接
const handleTest = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()
    testing.value = true

    const testPayload: any = { ...formData.value }
    delete testPayload.api_key
    delete testPayload.api_secret
    const result = await configApi.testConfig({
      config_type: 'datasource',
      config_data: testPayload
    })

    if (result.success) {
      ElMessage.success(`连接测试成功: ${result.message}`)
    } else {
      ElMessage.error(`连接测试失败: ${result.message}`)
    }
  } catch (error) {
    console.error('测试连接失败:', error)
    ElMessage.error('测试连接失败')
  } finally {
    testing.value = false
  }
}

// 生命周期
onMounted(() => {
  loadMarketCategories()
})
</script>

<style lang="scss" scoped>
.form-help {
  color: #909399;
  font-size: 12px;
  margin-left: 8px;
}

.config-params {
  .param-item {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
  }
}

.dialog-footer {
  text-align: right;
}
</style>
