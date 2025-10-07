<template>
  <div class="model-catalog-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>模型目录管理</span>
          <el-button type="primary" @click="handleAdd">
            <el-icon><Plus /></el-icon>
            添加厂家模型目录
          </el-button>
        </div>
      </template>

      <el-alert
        title="说明"
        type="info"
        :closable="false"
        style="margin-bottom: 20px"
      >
        模型目录用于在添加大模型配置时提供可选的模型列表。您可以在这里管理各个厂家支持的模型。
      </el-alert>

      <el-table
        :data="catalogs"
        v-loading="loading"
        border
        style="width: 100%"
      >
        <el-table-column prop="provider" label="厂家标识" width="150" />
        <el-table-column prop="provider_name" label="厂家名称" width="150" />
        <el-table-column label="模型数量" width="120">
          <template #default="{ row }">
            <el-tag>{{ row.models.length }} 个模型</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="模型列表">
          <template #default="{ row }">
            <el-tag
              v-for="model in row.models.slice(0, 3)"
              :key="model.name"
              size="small"
              style="margin-right: 5px"
            >
              {{ model.display_name }}
            </el-tag>
            <span v-if="row.models.length > 3">
              ... 还有 {{ row.models.length - 3 }} 个
            </span>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              size="small"
              @click="handleEdit(row)"
            >
              编辑
            </el-button>
            <el-button
              type="danger"
              size="small"
              @click="handleDelete(row)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 编辑对话框 -->
    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑模型目录' : '添加模型目录'"
      width="1200px"
    >
      <el-form
        ref="formRef"
        :model="formData"
        :rules="rules"
        label-width="120px"
      >
        <el-form-item label="厂家标识" prop="provider">
          <el-input
            v-model="formData.provider"
            placeholder="如: dashscope"
            :disabled="isEdit"
          />
        </el-form-item>
        <el-form-item label="厂家名称" prop="provider_name">
          <el-input
            v-model="formData.provider_name"
            placeholder="如: 通义千问"
          />
        </el-form-item>
        <el-form-item label="模型列表">
          <el-button
            type="primary"
            size="small"
            @click="handleAddModel"
            style="margin-bottom: 10px"
          >
            <el-icon><Plus /></el-icon>
            添加模型
          </el-button>
          <el-table :data="formData.models" border max-height="400">
            <el-table-column label="模型名称" width="200">
              <template #default="{ row, $index }">
                <el-input
                  v-model="row.name"
                  placeholder="如: qwen-turbo"
                  size="small"
                />
              </template>
            </el-table-column>
            <el-table-column label="显示名称" width="280">
              <template #default="{ row, $index }">
                <el-input
                  v-model="row.display_name"
                  placeholder="如: Qwen Turbo - 快速经济"
                  size="small"
                />
              </template>
            </el-table-column>
            <el-table-column label="输入价格/1K" width="180">
              <template #default="{ row, $index }">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model.number="row.input_price_per_1k"
                    placeholder="0.001"
                    size="small"
                    type="number"
                    step="0.0001"
                    style="width: 100px;"
                  />
                  <span style="color: #909399; font-size: 12px;">{{ row.currency || 'CNY' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="输出价格/1K" width="180">
              <template #default="{ row, $index }">
                <div style="display: flex; align-items: center; gap: 8px;">
                  <el-input
                    v-model.number="row.output_price_per_1k"
                    placeholder="0.002"
                    size="small"
                    type="number"
                    step="0.0001"
                    style="width: 100px;"
                  />
                  <span style="color: #909399; font-size: 12px;">{{ row.currency || 'CNY' }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="上下文长度" width="150">
              <template #default="{ row, $index }">
                <el-input
                  v-model.number="row.context_length"
                  placeholder="1000000"
                  size="small"
                  type="number"
                />
              </template>
            </el-table-column>
            <el-table-column label="货币单位" width="120">
              <template #default="{ row, $index }">
                <el-select
                  v-model="row.currency"
                  size="small"
                  placeholder="选择货币"
                >
                  <el-option label="CNY" value="CNY" />
                  <el-option label="USD" value="USD" />
                  <el-option label="EUR" value="EUR" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="100" fixed="right">
              <template #default="{ $index }">
                <el-button
                  type="danger"
                  size="small"
                  @click="handleRemoveModel($index)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">
          保存
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { configApi } from '@/api/config'

// 数据
const loading = ref(false)
const catalogs = ref<any[]>([])
const dialogVisible = ref(false)
const isEdit = ref(false)
const saving = ref(false)
const formRef = ref<FormInstance>()

interface ModelInfo {
  name: string
  display_name: string
  input_price_per_1k?: number | null
  output_price_per_1k?: number | null
  context_length?: number | null
  max_tokens?: number | null
  currency?: string
  description?: string
  is_deprecated?: boolean
  release_date?: string
  capabilities?: string[]
}

const formData = ref({
  provider: '',
  provider_name: '',
  models: [] as ModelInfo[]
})

const rules: FormRules = {
  provider: [{ required: true, message: '请输入厂家标识', trigger: 'blur' }],
  provider_name: [{ required: true, message: '请输入厂家名称', trigger: 'blur' }]
}

// 方法
const loadCatalogs = async () => {
  loading.value = true
  try {
    const response = await configApi.getModelCatalog()
    catalogs.value = response
  } catch (error) {
    console.error('加载模型目录失败:', error)
    ElMessage.error('加载模型目录失败')
  } finally {
    loading.value = false
  }
}

const handleAdd = () => {
  isEdit.value = false
  formData.value = {
    provider: '',
    provider_name: '',
    models: []
  }
  dialogVisible.value = true
}

const handleEdit = (row: any) => {
  isEdit.value = true
  formData.value = {
    provider: row.provider,
    provider_name: row.provider_name,
    models: JSON.parse(JSON.stringify(row.models))
  }
  dialogVisible.value = true
}

const handleDelete = async (row: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除厂家 ${row.provider_name} 的模型目录吗？`,
      '确认删除',
      {
        type: 'warning'
      }
    )
    
    await configApi.deleteModelCatalog(row.provider)
    ElMessage.success('删除成功')
    await loadCatalogs()
  } catch (error: any) {
    if (error !== 'cancel') {
      console.error('删除失败:', error)
      ElMessage.error('删除失败')
    }
  }
}

const handleAddModel = () => {
  formData.value.models.push({
    name: '',
    display_name: '',
    input_price_per_1k: null,
    output_price_per_1k: null,
    context_length: null,
    currency: 'CNY'
  })
}

const handleRemoveModel = (index: number) => {
  formData.value.models.splice(index, 1)
}

const handleSave = async () => {
  if (!formRef.value) return
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return
    
    if (formData.value.models.length === 0) {
      ElMessage.warning('请至少添加一个模型')
      return
    }
    
    saving.value = true
    try {
      await configApi.saveModelCatalog(formData.value)
      ElMessage.success('保存成功')
      dialogVisible.value = false
      await loadCatalogs()
    } catch (error) {
      console.error('保存失败:', error)
      ElMessage.error('保存失败')
    } finally {
      saving.value = false
    }
  })
}

const formatDate = (date: string) => {
  if (!date) return '-'
  return new Date(date).toLocaleString('zh-CN')
}

onMounted(() => {
  loadCatalogs()
})
</script>

<style lang="scss" scoped>
.model-catalog-management {
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
}
</style>

