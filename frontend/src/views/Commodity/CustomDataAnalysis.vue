<template>
  <div class="custom-data-analysis">
    <div class="page-header">
      <h2>自定义数据分析</h2>
      <p class="text-secondary">上传 Excel / CSV 数据文件，选择分析技能进行自定义数据驱动分析</p>
    </div>

    <el-row :gutter="24">
      <!-- 左侧: 文件上传 & 配置 -->
      <el-col :span="8">
        <!-- 文件上传卡 -->
        <el-card shadow="never" class="form-card">
          <template #header><span><b>数据文件</b></span></template>

          <el-upload
            ref="uploadRef"
            drag
            multiple
            :auto-upload="true"
            :http-request="handleUpload"
            :before-upload="beforeUpload"
            :on-remove="handleRemove"
            :on-error="handleUploadError"
            accept=".xlsx,.xls,.csv"
          >
            <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              拖拽文件到此处，或 <em>点击选择</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                支持 .xlsx / .xls / .csv 格式，单个文件最大 50MB，最多 10 个文件
              </div>
            </template>
          </el-upload>

          <!-- 已上传文件列表 -->
          <div v-if="uploadedFiles.length" style="margin-top: 12px">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px">
              <span style="font-size: 13px; font-weight: 600">已上传 ({{ uploadedFiles.length }})</span>
              <el-button text size="small" @click="clearAllUploaded">清空</el-button>
            </div>
            <div v-for="(f, i) in uploadedFiles" :key="f.file_id" class="uploaded-file-item">
              <el-icon><Document /></el-icon>
              <span class="file-name" :title="f.original_name">{{ f.original_name }}</span>
              <el-tag size="small" type="success">ok</el-tag>
              <el-button text size="small" @click="removeUploaded(i)">
                <el-icon><Close /></el-icon>
              </el-button>
            </div>
          </div>
        </el-card>

        <!-- 分析配置卡 -->
        <el-card shadow="never" class="form-card" style="margin-top: 16px">
          <template #header><span><b>分析配置</b></span></template>

          <el-form label-position="top" size="large">
            <el-form-item label="分析技能" required>
              <el-select v-model="skillName" placeholder="选择分析技能" style="width: 100%" @change="onSkillChange">
                <el-option
                  v-for="s in skills"
                  :key="s.name"
                  :value="s.name"
                  :label="s.title"
                >
                  <span>{{ s.title }}</span>
                  <span class="text-secondary" style="font-size: 12px; margin-left: 8px">{{ s.description }}</span>
                </el-option>
              </el-select>
            </el-form-item>

            <el-form-item label="用户上下文（可选）">
              <el-input
                v-model="userContext"
                type="textarea"
                :rows="3"
                placeholder="描述数据的背景和目的，例如：这份是2026年6月RB库存周报，包含华东各仓库的库存变化"
              />
            </el-form-item>

            <el-form-item label="关联合约（可选）">
              <el-input
                v-model="fullSymbol"
                placeholder="如 RB2510.SHF，留空则不关联合约"
              />
            </el-form-item>

            <el-form-item label="分析日期">
              <el-date-picker
                v-model="tradeDate"
                type="date"
                placeholder="默认当天"
                style="width: 100%"
                value-format="YYYY-MM-DD"
              />
            </el-form-item>

            <el-button
              type="primary"
              size="large"
              :loading="submitting"
              :disabled="submitting || !canSubmit"
              style="width: 100%"
              @click="submitAnalysis"
            >
              {{ submitting ? '提交中...' : '提交分析' }}
            </el-button>

            <!-- 进度提示 -->
            <el-alert
              v-if="pollingActive && progressMessage"
              :title="progressMessage"
              type="info"
              :closable="false"
              show-icon
              style="margin-top: 12px"
            />
          </el-form>
        </el-card>
      </el-col>

      <!-- 右侧: 结果展示 -->
      <el-col :span="16">
        <!-- 分析结果 -->
        <el-card v-if="analysisResult" shadow="never">
          <template #header>
            <div style="display: flex; justify-content: space-between; align-items: center">
              <span><b>数据分析报告</b></span>
              <el-button text size="small" @click="clearResult">
                <el-icon><Close /></el-icon> 关闭
              </el-button>
            </div>
          </template>

          <div v-if="reportLoading" v-loading="reportLoading" style="min-height: 100px" />

          <div v-else-if="reportContent" class="report-content" v-html="reportContent" />

          <div v-else-if="analysisResult.custom_data_report" class="report-content" v-html="renderMarkdown(analysisResult.custom_data_report)" />

          <el-empty v-else description="暂未获取到分析报告" />
        </el-card>

        <!-- 空状态 -->
        <el-card v-else shadow="never">
          <el-empty description="上传文件并提交分析">
            <p class="text-secondary">
              支持上传 Excel(.xlsx/.xls) 和 CSV 文件，系统将自动读取数据并<br>
              基于所选技能进行统计分析，生成结构化数据洞察报告
            </p>
          </el-empty>
        </el-card>

        <!-- 当前技能说明 -->
        <el-card v-if="selectedSkillDesc" shadow="never" style="margin-top: 16px">
          <template #header><span><b>当前技能：{{ selectedSkillTitle }}</b></span></template>
          <p class="text-secondary">{{ selectedSkillDesc }}</p>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { UploadRequestOptions, UploadFile } from 'element-plus'
import { UploadFilled, Document, Close } from '@element-plus/icons-vue'
import { commodityApi } from '@/api/commodity'
import { renderMarkdown } from '@/utils/markdown'

// ====== 状态 ======

// 文件
const uploadRef = ref()
const uploadedFiles = ref<Array<{
  file_id: string
  original_name: string
  size: number
}>>([])
/** filename → file_id 映射，用于 onRemove 回调中查找 */
const fileIdMap = new Map<string, string>()

// 技能
const skills = ref<Array<{
  name: string
  title: string
  description: string
  content_types: string[]
}>>([])
const skillName = ref('general-analysis')
const selectedSkillTitle = ref('')
const selectedSkillDesc = ref('')

// 配置
const userContext = ref('')
const fullSymbol = ref('')
const tradeDate = ref('')

// 提交
const submitting = ref(false)

// 轮询
let pollingTimer: ReturnType<typeof setTimeout> | null = null
const pollingActive = ref(false)
const progressMessage = ref('')
const lastTaskId = ref('')
const analysisResult = ref<Record<string, any> | null>(null)
const reportContent = ref('')
const reportLoading = ref(false)

// ====== 计算属性 ======

const canSubmit = computed(() => {
  return uploadedFiles.value.length > 0 && skillName.value
})

// ====== 文件上传 ======

function beforeUpload(rawFile: File): boolean {
  const ext = '.' + (rawFile.name.split('.').pop()?.toLowerCase() || '')
  if (!['.xlsx', '.xls', '.csv'].includes(ext)) {
    ElMessage.error(`不支持的文件格式: ${ext}，仅支持 .xlsx/.xls/.csv`)
    return false
  }
  if (rawFile.size > 50 * 1024 * 1024) {
    ElMessage.error(`文件过大: ${rawFile.name}（最大 50MB）`)
    return false
  }
  if (uploadedFiles.value.length >= 10) {
    ElMessage.error('最多上传 10 个文件')
    return false
  }
  return true
}

async function handleUpload(options: UploadRequestOptions) {
  const file = options.file as File
  try {
    const res = await commodityApi.uploadCustomData(file, (pct) => {
      options.onProgress({
        percent: pct,
        total: 100,
        loaded: pct,
      } as any)
    })
    if (res?.success && res.data) {
      fileIdMap.set(file.name, res.data.file_id)
      uploadedFiles.value.push(res.data)
      options.onSuccess(res.data)
    } else {
      options.onError(new Error(res?.message || '上传失败') as any)
    }
  } catch (e: any) {
    options.onError(e)
    ElMessage.error(`${file.name} 上传失败: ${e.message}`)
  }
}

function handleRemove(uploadFile: UploadFile) {
  const fileId = fileIdMap.get(uploadFile.name)
  if (fileId) {
    fileIdMap.delete(uploadFile.name)
    const idx = uploadedFiles.value.findIndex(f => f.file_id === fileId)
    if (idx >= 0) uploadedFiles.value.splice(idx, 1)
  }
}

function handleUploadError(err: any) {
  console.error('[custom-data] upload error:', err)
}

function removeUploaded(index: number) {
  const f = uploadedFiles.value[index]
  if (f) {
    fileIdMap.delete(f.original_name)
    uploadedFiles.value.splice(index, 1)
    // 也通知 el-upload 移除
    if (uploadRef.value) {
      const uploadInstance = uploadRef.value as any
      uploadInstance.handleRemove({ name: f.original_name } as UploadFile)
    }
  }
}

function clearAllUploaded() {
  uploadedFiles.value = []
  fileIdMap.clear()
  if (uploadRef.value) {
    const uploadInstance = uploadRef.value as any
    uploadInstance.clearFiles()
  }
}

// ====== 技能加载 ======

function onSkillChange(name: string) {
  const found = skills.value.find(s => s.name === name)
  selectedSkillTitle.value = found?.title || ''
  selectedSkillDesc.value = found?.description || ''
}

async function loadSkills() {
  try {
    const res = await commodityApi.listCustomSkills()
    const items = (res as any)?.data
    if (items && Array.isArray(items)) {
      skills.value = items
      if (skills.value.length > 0) {
        const defaultSkill = skills.value.find(s => s.name === skillName.value) || skills.value[0]
        skillName.value = defaultSkill.name
        selectedSkillTitle.value = defaultSkill.title
        selectedSkillDesc.value = defaultSkill.description
      }
    }
  } catch (e) {
    console.error('[custom-data] loadSkills error:', e)
  }
}

// ====== 提交分析 ======

async function submitAnalysis() {
  if (!canSubmit.value) {
    ElMessage.warning('请先上传数据文件并选择分析技能')
    return
  }

  submitting.value = true
  progressMessage.value = ''
  lastTaskId.value = ''

  try {
    const res = await commodityApi.submitCustomDataAnalysis({
      file_ids: uploadedFiles.value.map(f => f.file_id),
      skill_name: skillName.value,
      user_context: userContext.value,
      full_symbol: fullSymbol.value || undefined,
      trade_date: tradeDate.value || undefined,
    })

    if ((res as any)?.success) {
      const tid = (res as any)?.data?.task_id
      lastTaskId.value = tid || ''
      progressMessage.value = '任务已提交，后台分析中...'
      pollingActive.value = true
      submitting.value = false
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

// ====== 轮询 ======

function stopPolling() {
  if (pollingTimer !== null) {
    clearTimeout(pollingTimer)
    pollingTimer = null
  }
}

function startPolling(taskId: string) {
  let attempts = 0
  const maxAttempts = 60

  const poll = async () => {
    attempts++
    try {
      const res = await commodityApi.getTaskStatus(taskId)
      const data = (res as any)?.data
      if (!data) {
        // continue polling
      } else if (data.status === 'completed') {
        pollingActive.value = false
        progressMessage.value = ''
        reportLoading.value = true
        try {
          const detail = await commodityApi.getTaskResult(taskId)
          if ((detail as any)?.data) {
            analysisResult.value = (detail as any).data
            const report = (detail as any).data.custom_data_report || ''
            reportContent.value = report ? renderMarkdown(report) : ''
          }
          ElMessage.success('分析完成！')
        } finally {
          reportLoading.value = false
        }
        return
      } else if (data.status === 'failed') {
        pollingActive.value = false
        progressMessage.value = ''
        ElMessage.error(data.progress_message || '分析失败')
        return
      } else {
        // processing
        if (data.progress_message) {
          progressMessage.value = data.progress_message
        }
      }
    } catch {
      // continue polling
    }
    if (attempts < maxAttempts) {
      pollingTimer = setTimeout(poll, 5000)
    } else {
      pollingActive.value = false
      progressMessage.value = ''
      ElMessage.warning('分析超时，请稍后查看任务中心')
    }
  }
  pollingTimer = setTimeout(poll, 5000)
}

function clearResult() {
  analysisResult.value = null
  reportContent.value = ''
}

// ====== 生命周期 ======

onMounted(() => {
  loadSkills()
})

onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped>
.custom-data-analysis { padding: 24px; max-width: 1400px; margin: 0 auto; }
.page-header { margin-bottom: 24px; }
.page-header h2 { margin: 0 0 4px; }
.text-secondary { color: #909399; font-size: 14px; }
.form-card { border: 1px solid var(--el-border-color-light, #e4e7ed); }

.uploaded-file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
  font-size: 13px;
}
.uploaded-file-item .file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.report-content {
  font-size: 14px;
  line-height: 1.7;
  color: var(--el-text-color-primary);
}
.report-content :deep(h4) {
  margin: 16px 0 8px;
  font-size: 15px;
  font-weight: 600;
}
.report-content :deep(h5) {
  margin: 12px 0 6px;
  font-size: 14px;
  font-weight: 600;
}
.report-content :deep(pre) {
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 4px;
  padding: 12px;
  overflow-x: auto;
  font-size: 13px;
}
.report-content :deep(code) {
  background: var(--el-fill-color-lighter, #f5f7fa);
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 13px;
}
.report-content :deep(table.md-table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 13px;
}
.report-content :deep(table.md-table th),
.report-content :deep(table.md-table td) {
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  padding: 6px 10px;
  text-align: left;
}
.report-content :deep(table.md-table th) {
  background: var(--el-fill-color-lighter, #f5f7fa);
  font-weight: 600;
}
.report-content :deep(br) {
  display: block;
  margin: 4px 0;
}
</style>
