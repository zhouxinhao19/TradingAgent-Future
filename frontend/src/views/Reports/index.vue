<template>
  <div class="reports">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Document /></el-icon>
        分析报告
      </h1>
      <p class="page-description">
        查看和管理股票分析报告，支持多种格式导出
      </p>
    </div>

    <!-- 筛选和操作栏 -->
    <el-card class="filter-card" shadow="never">
      <el-row :gutter="16" align="middle">
        <el-col :span="6">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索股票代码或名称"
            clearable
            @input="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </el-col>
        
        <el-col :span="4">
          <el-select v-model="statusFilter" placeholder="状态筛选" clearable>
            <el-option label="已完成" value="completed" />
            <el-option label="处理中" value="processing" />
            <el-option label="失败" value="failed" />
          </el-select>
        </el-col>
        
        <el-col :span="6">
          <el-date-picker
            v-model="dateRange"
            type="daterange"
            range-separator="至"
            start-placeholder="开始日期"
            end-placeholder="结束日期"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            @change="handleDateChange"
          />
        </el-col>
        
        <el-col :span="8">
          <div class="action-buttons">
            <el-button type="primary" @click="generateReport">
              <el-icon><Plus /></el-icon>
              生成报告
            </el-button>
            <el-button @click="exportSelected" :disabled="selectedReports.length === 0">
              <el-icon><Download /></el-icon>
              批量导出
            </el-button>
            <el-button @click="refreshReports">
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 报告列表 -->
    <el-card class="reports-list-card" shadow="never">
      <el-table
        :data="filteredReports"
        @selection-change="handleSelectionChange"
        v-loading="loading"
        style="width: 100%"
      >
        <el-table-column type="selection" width="55" />
        
        <el-table-column prop="title" label="报告标题" min-width="200">
          <template #default="{ row }">
            <div class="report-title">
              <el-link type="primary" @click="viewReport(row)">
                {{ row.title }}
              </el-link>
              <div class="report-subtitle">
                {{ row.stock_code }} - {{ row.stock_name }}
              </div>
            </div>
          </template>
        </el-table-column>
        
        <el-table-column prop="type" label="报告类型" width="120">
          <template #default="{ row }">
            <el-tag :type="getTypeColor(row.type)">
              {{ getTypeText(row.type) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="format" label="格式" width="100">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.format.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusType(row.status)">
              {{ getStatusText(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        
        <el-table-column prop="created_at" label="创建时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        
        <el-table-column prop="file_size" label="文件大小" width="120">
          <template #default="{ row }">
            {{ formatFileSize(row.file_size) }}
          </template>
        </el-table-column>
        
        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <el-button type="text" size="small" @click="viewReport(row)">
              查看
            </el-button>
            <el-button
              v-if="row.status === 'completed'"
              type="text"
              size="small"
              @click="downloadReport(row)"
            >
              下载
            </el-button>
            <el-button
              type="text"
              size="small"
              @click="deleteReport(row)"
              style="color: var(--el-color-danger)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :page-sizes="[20, 50, 100]"
          :total="totalReports"
          layout="total, sizes, prev, pager, next, jumper"
          @size-change="handleSizeChange"
          @current-change="handleCurrentChange"
        />
      </div>
    </el-card>

    <!-- 生成报告对话框 -->
    <el-dialog
      v-model="generateDialogVisible"
      title="生成分析报告"
      width="600px"
    >
      <el-form :model="reportForm" label-width="120px">
        <el-form-item label="报告标题">
          <el-input v-model="reportForm.title" placeholder="请输入报告标题" />
        </el-form-item>
        
        <el-form-item label="股票代码">
          <el-input v-model="reportForm.stock_code" placeholder="请输入股票代码" />
        </el-form-item>
        
        <el-form-item label="报告类型">
          <el-select v-model="reportForm.type" placeholder="选择报告类型">
            <el-option label="单股分析报告" value="single" />
            <el-option label="批量分析汇总" value="batch" />
            <el-option label="投资组合报告" value="portfolio" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="输出格式">
          <el-checkbox-group v-model="reportForm.formats">
            <el-checkbox label="pdf">PDF</el-checkbox>
            <el-checkbox label="html">HTML</el-checkbox>
            <el-checkbox label="markdown">Markdown</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        
        <el-form-item label="包含内容">
          <el-checkbox-group v-model="reportForm.sections">
            <el-checkbox label="summary">执行摘要</el-checkbox>
            <el-checkbox label="analysis">详细分析</el-checkbox>
            <el-checkbox label="charts">图表数据</el-checkbox>
            <el-checkbox label="recommendation">投资建议</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="generateDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmGenerate" :loading="generating">
          生成报告
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Document,
  Search,
  Plus,
  Download,
  Refresh
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

// 使用路由和认证store
const router = useRouter()
const authStore = useAuthStore()

// 响应式数据
const loading = ref(false)
const generating = ref(false)
const generateDialogVisible = ref(false)
const searchKeyword = ref('')
const statusFilter = ref('')
const dateRange = ref<[string, string] | null>(null)
const selectedReports = ref([])
const currentPage = ref(1)
const pageSize = ref(20)
const totalReports = ref(0)

const reportForm = ref({
  title: '',
  stock_code: '',
  type: 'single',
  formats: ['pdf'],
  sections: ['summary', 'analysis', 'recommendation']
})

const reports = ref([])

// 计算属性
const filteredReports = computed(() => {
  // 现在数据直接从API获取，不需要前端筛选
  return reports.value
})

// API调用函数
const fetchReports = async () => {
  loading.value = true
  try {
    const params = new URLSearchParams({
      page: currentPage.value.toString(),
      page_size: pageSize.value.toString()
    })

    if (searchKeyword.value) {
      params.append('search_keyword', searchKeyword.value)
    }
    if (statusFilter.value) {
      params.append('status_filter', statusFilter.value)
    }
    if (dateRange.value) {
      params.append('start_date', dateRange.value[0])
      params.append('end_date', dateRange.value[1])
    }

    const response = await fetch(`/api/reports/list?${params}`, {
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const result = await response.json()

    if (result.success) {
      reports.value = result.data.reports
      totalReports.value = result.data.total
    } else {
      throw new Error(result.message || '获取报告列表失败')
    }
  } catch (error) {
    console.error('获取报告列表失败:', error)
    ElMessage.error('获取报告列表失败')
  } finally {
    loading.value = false
  }
}

// 方法
const handleSearch = () => {
  currentPage.value = 1
  fetchReports()
}

const handleDateChange = () => {
  currentPage.value = 1
  fetchReports()
}

const handleSelectionChange = (selection: any[]) => {
  selectedReports.value = selection
}

const generateReport = () => {
  generateDialogVisible.value = true
  // 重置表单
  reportForm.value = {
    title: '',
    stock_code: '',
    type: 'single',
    formats: ['pdf'],
    sections: ['summary', 'analysis', 'recommendation']
  }
}

const confirmGenerate = async () => {
  generating.value = true
  try {
    // TODO: 实现报告生成API调用
    await new Promise(resolve => setTimeout(resolve, 2000))

    ElMessage.success('报告生成任务已提交')
    generateDialogVisible.value = false
    refreshReports()
  } catch (error) {
    ElMessage.error('生成报告失败')
  } finally {
    generating.value = false
  }
}

const viewReport = (report: any) => {
  // 跳转到报告详情页面
  router.push(`/reports/view/${report.id}`)
}

const downloadReport = async (report: any) => {
  try {
    const response = await fetch(`/api/reports/${report.id}/download?format=markdown`, {
      headers: {
        'Authorization': `Bearer ${authStore.token}`
      }
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const blob = await response.blob()
    const url = window.URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${report.stock_code}_${report.analysis_date}_report.md`
    document.body.appendChild(a)
    a.click()
    window.URL.revokeObjectURL(url)
    document.body.removeChild(a)

    ElMessage.success(`报告下载成功`)
  } catch (error) {
    console.error('下载报告失败:', error)
    ElMessage.error('下载报告失败')
  }
}

const deleteReport = async (report: any) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除报告 "${report.title}" 吗？`,
      '确认删除',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )

    // 调用删除API
    const response = await fetch(`/api/reports/${report.id}`, {
      method: 'DELETE',
      headers: {
        'Authorization': `Bearer ${authStore.token}`,
        'Content-Type': 'application/json'
      }
    })

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`)
    }

    const result = await response.json()

    if (result.success) {
      ElMessage.success('报告已删除')
      refreshReports()
    } else {
      throw new Error(result.message || '删除失败')
    }
  } catch (error) {
    if (error.message !== 'cancel') {
      console.error('删除报告失败:', error)
      ElMessage.error('删除报告失败')
    }
  }
}

const exportSelected = () => {
  ElMessage.info('批量导出功能开发中...')
}

const refreshReports = () => {
  fetchReports()
}

const getTypeColor = (type: string) => {
  const colorMap: Record<string, string> = {
    single: 'primary',
    batch: 'success',
    portfolio: 'warning'
  }
  return colorMap[type] || 'info'
}

const getTypeText = (type: string) => {
  const textMap: Record<string, string> = {
    single: '单股分析',
    batch: '批量分析',
    portfolio: '投资组合'
  }
  return textMap[type] || type
}

const getStatusType = (status: string) => {
  const statusMap: Record<string, string> = {
    completed: 'success',
    processing: 'warning',
    failed: 'danger'
  }
  return statusMap[status] || 'info'
}

const getStatusText = (status: string) => {
  const statusMap: Record<string, string> = {
    completed: '已完成',
    processing: '生成中',
    failed: '失败'
  }
  return statusMap[status] || status
}

import { formatDateTime } from '@/utils/datetime'

const formatTime = (time: string) => {
  return formatDateTime(time)
}

const formatFileSize = (size: number) => {
  if (size === 0) return '-'
  const units = ['B', 'KB', 'MB', 'GB']
  let index = 0
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024
    index++
  }
  return `${size.toFixed(1)} ${units[index]}`
}

const handleSizeChange = (size: number) => {
  pageSize.value = size
  currentPage.value = 1
  fetchReports()
}

const handleCurrentChange = (page: number) => {
  currentPage.value = page
  fetchReports()
}

// 生命周期
onMounted(() => {
  fetchReports()
})
</script>

<style lang="scss" scoped>
.reports {
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

  .filter-card {
    margin-bottom: 24px;

    .action-buttons {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    }
  }

  .reports-list-card {
    .report-title {
      .report-subtitle {
        font-size: 12px;
        color: var(--el-text-color-placeholder);
        margin-top: 2px;
      }
    }

    .pagination-wrapper {
      display: flex;
      justify-content: center;
      margin-top: 24px;
    }
  }
}
</style>
