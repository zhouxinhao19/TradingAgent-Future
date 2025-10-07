<template>
  <el-dialog
    :model-value="visible"
    :title="isEdit ? '编辑大模型配置' : '添加大模型配置'"
    width="600px"
    @update:model-value="handleVisibleChange"
    @close="handleClose"
  >
    <el-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      label-width="120px"
    >
      <!-- 基础配置 -->
      <el-form-item label="供应商" prop="provider">
        <el-select
          v-model="formData.provider"
          placeholder="选择供应商"
          @change="handleProviderChange"
          :loading="providersLoading"
        >
          <el-option
            v-for="provider in availableProviders"
            :key="provider.name"
            :label="provider.display_name"
            :value="provider.name"
          />
        </el-select>
        <div class="form-tip">
          如果没有找到需要的供应商，请先在"厂家管理"中添加
        </div>
      </el-form-item>

      <el-form-item label="模型名称" prop="model_name">
        <el-select
          v-if="modelOptions.length > 0"
          v-model="formData.model_name"
          placeholder="选择或输入模型名称"
          filterable
          allow-create
        >
          <el-option
            v-for="model in modelOptions"
            :key="model.value"
            :label="model.label"
            :value="model.value"
          />
        </el-select>
        <el-input
          v-else
          v-model="formData.model_name"
          placeholder="输入模型名称"
        />
        <div class="form-tip">
          💡 可以从列表中选择常用模型，也可以直接输入自定义模型名称
        </div>
      </el-form-item>

      <el-form-item label="API基础URL" prop="api_base">
        <el-input
          v-model="formData.api_base"
          placeholder="可选，自定义API端点（留空使用厂家默认地址）"
        />
        <div class="form-tip">
          💡 API密钥已在厂家配置中设置，此处只需配置模型参数
        </div>
      </el-form-item>

      <!-- 模型参数 -->
      <el-divider content-position="left">模型参数</el-divider>

      <el-form-item label="最大Token数" prop="max_tokens">
        <el-input-number
          v-model="formData.max_tokens"
          :min="100"
          :max="32000"
          :step="100"
        />
      </el-form-item>

      <el-form-item label="温度参数" prop="temperature">
        <el-input-number
          v-model="formData.temperature"
          :min="0"
          :max="2"
          :step="0.1"
          :precision="1"
        />
      </el-form-item>

      <el-form-item label="超时时间" prop="timeout">
        <el-input-number
          v-model="formData.timeout"
          :min="10"
          :max="300"
          :step="10"
        />
        <span class="ml-2 text-gray-500">秒</span>
      </el-form-item>

      <el-form-item label="重试次数" prop="retry_times">
        <el-input-number
          v-model="formData.retry_times"
          :min="0"
          :max="10"
        />
      </el-form-item>

      <!-- 定价配置 -->
      <el-divider content-position="left">定价配置</el-divider>

      <el-form-item label="输入价格" prop="input_price_per_1k">
        <el-input-number
          v-model="formData.input_price_per_1k"
          :min="0"
          :step="0.001"
          :precision="4"
          placeholder="每1000个token的价格"
        />
        <span class="ml-2 text-gray-500">{{ formData.currency || 'CNY' }}/1K tokens</span>
      </el-form-item>

      <el-form-item label="输出价格" prop="output_price_per_1k">
        <el-input-number
          v-model="formData.output_price_per_1k"
          :min="0"
          :step="0.001"
          :precision="4"
          placeholder="每1000个token的价格"
        />
        <span class="ml-2 text-gray-500">{{ formData.currency || 'CNY' }}/1K tokens</span>
      </el-form-item>

      <el-form-item label="货币单位" prop="currency">
        <el-select v-model="formData.currency" placeholder="选择货币单位">
          <el-option label="人民币 (CNY)" value="CNY" />
          <el-option label="美元 (USD)" value="USD" />
          <el-option label="欧元 (EUR)" value="EUR" />
        </el-select>
      </el-form-item>

      <!-- 高级设置 -->
      <el-divider content-position="left">高级设置</el-divider>

      <el-form-item label="启用模型">
        <el-switch v-model="formData.enabled" />
      </el-form-item>

      <el-form-item label="启用记忆功能">
        <el-switch v-model="formData.enable_memory" />
      </el-form-item>

      <el-form-item label="启用调试模式">
        <el-switch v-model="formData.enable_debug" />
      </el-form-item>

      <el-form-item label="优先级" prop="priority">
        <el-input-number
          v-model="formData.priority"
          :min="0"
          :max="100"
        />
        <span class="ml-2 text-gray-500">数值越大优先级越高</span>
      </el-form-item>

      <el-form-item label="模型类别" prop="model_category">
        <el-input
          v-model="formData.model_category"
          placeholder="可选，用于OpenRouter等分类"
        />
      </el-form-item>

      <el-form-item label="描述" prop="description">
        <el-input
          v-model="formData.description"
          type="textarea"
          :rows="3"
          placeholder="可选，配置描述"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleClose">取消</el-button>
        <el-button type="primary" @click="handleSubmit" :loading="loading">
          {{ isEdit ? '更新' : '添加' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { configApi, type LLMProvider, type LLMConfig, validateLLMConfig } from '@/api/config'

// Props
interface Props {
  visible: boolean
  config?: LLMConfig | null
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
const providersLoading = ref(false)
const availableProviders = ref<LLMProvider[]>([])

// Computed
const isEdit = computed(() => !!props.config)

// 表单数据
const defaultFormData = {
  provider: '',
  model_name: '',
  api_base: '',
  max_tokens: 4000,
  temperature: 0.7,
  timeout: 60,
  retry_times: 3,
  enabled: true,
  enable_memory: false,
  enable_debug: false,
  priority: 0,
  model_category: '',
  description: '',
  input_price_per_1k: 0,
  output_price_per_1k: 0,
  currency: 'CNY'
}

const formData = ref({ ...defaultFormData })

// 表单验证规则
const rules: FormRules = {
  provider: [{ required: true, message: '请选择供应商', trigger: 'change' }],
  model_name: [{ required: true, message: '请输入模型名称', trigger: 'blur' }],
  max_tokens: [{ required: true, message: '请输入最大Token数', trigger: 'blur' }],
  temperature: [{ required: true, message: '请输入温度参数', trigger: 'blur' }],
  timeout: [{ required: true, message: '请输入超时时间', trigger: 'blur' }],
  retry_times: [{ required: true, message: '请输入重试次数', trigger: 'blur' }],
  priority: [{ required: true, message: '请输入优先级', trigger: 'blur' }]
}

// 模型选项
const modelOptions = ref<Array<{ label: string; value: string }>>([])

// 从后端获取的模型目录
const modelCatalog = ref<Record<string, Array<{ name: string; display_name: string }>>>({})

// 加载模型目录
const loadModelCatalog = async () => {
  try {
    const catalog = await configApi.getAvailableModels()
    // 转换为 provider -> models 的映射
    const catalogMap: Record<string, Array<{ name: string; display_name: string }>> = {}
    catalog.forEach(item => {
      catalogMap[item.provider] = item.models
    })
    modelCatalog.value = catalogMap
    console.log('✅ 模型目录加载成功:', Object.keys(catalogMap))
  } catch (error) {
    console.error('❌ 加载模型目录失败:', error)
    ElMessage.warning('加载模型列表失败，将使用默认列表')
    // 失败时使用空目录，允许用户手动输入
    modelCatalog.value = {}
  }
}

// 根据供应商获取模型选项
const getModelOptions = (provider: string) => {
  // 优先从后端获取的目录中查找
  const models = modelCatalog.value[provider]
  if (models && models.length > 0) {
    return models.map(m => ({
      label: m.display_name,
      value: m.name
    }))
  }

  // 如果后端没有数据，返回空数组（允许用户手动输入）
  return []
}

// 处理供应商变更
const handleProviderChange = (provider: string) => {
  modelOptions.value = getModelOptions(provider)
  formData.value.model_name = ''
}

// 监听配置变化
watch(
  () => props.config,
  (config) => {
    if (config) {
      // 合并默认值和传入的配置，确保所有字段都有值
      formData.value = { ...defaultFormData, ...config }
      modelOptions.value = getModelOptions(config.provider)
    } else {
      formData.value = { ...defaultFormData }
      modelOptions.value = getModelOptions('dashscope')
    }
  },
  { immediate: true }
)

// 监听visible变化
watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      if (props.config) {
        // 编辑模式：合并默认值和传入的配置
        formData.value = { ...defaultFormData, ...props.config }
        modelOptions.value = getModelOptions(props.config.provider)
      } else {
        // 新增模式：使用默认值
        formData.value = { ...defaultFormData }
        modelOptions.value = getModelOptions('dashscope')
      }
    }
  }
)

// 处理可见性变化
const handleVisibleChange = (value: boolean) => {
  emit('update:visible', value)
}

// 处理关闭
const handleClose = () => {
  emit('update:visible', false)
  formRef.value?.resetFields()
}

// 处理提交
const handleSubmit = async () => {
  if (!formRef.value) return

  try {
    await formRef.value.validate()

    // 验证配置数据
    const errors = validateLLMConfig(formData.value)
    if (errors.length > 0) {
      ElMessage.error(`配置验证失败: ${errors.join(', ')}`)
      return
    }

    loading.value = true

    // 准备提交数据，移除api_key字段（由后端从厂家配置获取）
    const submitData = { ...formData.value }
    // 使用类型安全的方式移除api_key字段（如果存在的话）
    if ('api_key' in submitData) {
      delete (submitData as any).api_key  // 不发送api_key，让后端从厂家配置获取
    }

    console.log('🚀 提交大模型配置:', submitData)

    // 调用API
    await configApi.updateLLMConfig(submitData)

    ElMessage.success(isEdit.value ? '模型配置更新成功' : '模型配置添加成功')
    emit('success')
    handleClose()
  } catch (error) {
    console.error('❌ 提交大模型配置失败:', error)
    ElMessage.error(isEdit.value ? '模型配置更新失败' : '模型配置添加失败')
  } finally {
    loading.value = false
  }
}

// 加载可用的厂家列表
const loadProviders = async () => {
  providersLoading.value = true
  try {
    const providers = await configApi.getLLMProviders()
    // 只显示启用的厂家
    availableProviders.value = providers.filter(p => p.is_active)
    console.log('✅ 加载厂家列表成功:', availableProviders.value.length)

    // 如果是新增模式且没有选择供应商，默认选择第一个
    if (!isEdit.value && !formData.value.provider && availableProviders.value.length > 0) {
      formData.value.provider = availableProviders.value[0].name
      handleProviderChange(formData.value.provider)
    }
  } catch (error) {
    console.error('❌ 加载厂家列表失败:', error)
    ElMessage.error('加载厂家列表失败')
  } finally {
    providersLoading.value = false
  }
}

// 组件挂载时加载厂家数据和模型目录
onMounted(() => {
  loadProviders()
  loadModelCatalog()
})
</script>

<style lang="scss" scoped>
.dialog-footer {
  text-align: right;
}

.ml-2 {
  margin-left: 8px;
}

.text-gray-500 {
  color: #6b7280;
  font-size: 12px;
}

.form-tip {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  margin-top: 4px;
}
</style>
