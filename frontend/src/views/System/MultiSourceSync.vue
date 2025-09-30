<template>
  <div class="multi-source-sync">
    <!-- 页面头部 -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-info">
          <h1 class="page-title">
            <el-icon class="title-icon"><Connection /></el-icon>
            多数据源同步
          </h1>
          <p class="page-description">
            管理和监控多个数据源的股票基础信息同步，支持自动fallback和优先级配置
          </p>
        </div>
        <div class="header-actions">
          <el-button
            type="primary"
            size="large"
            :loading="testing"
            @click="runFullTest"
          >
            <el-icon><Operation /></el-icon>
            全面测试
          </el-button>
        </div>
      </div>
    </div>

    <!-- 主要内容 -->
    <div class="page-content">
      <el-row :gutter="24">
        <!-- 左侧列 -->
        <el-col :lg="12" :md="24" :sm="24">
          <!-- 数据源状态 -->
          <div class="content-section">
            <DataSourceStatus ref="dataSourceStatusRef" />
          </div>
          
          <!-- 使用建议 -->
          <div class="content-section">
            <SyncRecommendations />
          </div>
        </el-col>

        <!-- 右侧列 -->
        <el-col :lg="12" :md="24" :sm="24">
          <!-- 同步控制 -->
          <div class="content-section">
            <SyncControl @sync-completed="handleSyncCompleted" />
          </div>
          
          <!-- 同步历史 -->
          <div class="content-section">
            <SyncHistory />
          </div>
        </el-col>
      </el-row>
    </div>

    <!-- 测试结果对话框 -->
    <el-dialog
      v-model="testDialogVisible"
      title="全面测试结果"
      width="80%"
      :close-on-click-modal="false"
    >
      <div v-if="testResults" class="test-results-dialog">
        <div class="test-summary">
          <el-alert
            :title="`测试完成，共测试 ${testResults.length} 个数据源`"
            :type="getOverallTestResult()"
            :closable="false"
            show-icon
          />
        </div>
        
        <div class="test-details">
          <div 
            v-for="result in testResults" 
            :key="result.name"
            class="test-result-item"
          >
            <div class="result-header">
              <el-tag 
                :type="result.available ? 'success' : 'danger'"
                size="large"
              >
                {{ result.name.toUpperCase() }}
              </el-tag>
              <span class="priority-info">优先级: {{ result.priority }}</span>
            </div>
            
            <div class="result-tests">
              <el-row :gutter="16">
                <el-col
                  v-for="(test, testName) in result.tests"
                  :key="testName"
                  :span="8"
                >
                  <div class="test-item">
                    <div class="test-header">
                      <el-icon
                        :class="test.success ? 'success-icon' : 'error-icon'"
                      >
                        <component :is="test.success ? 'SuccessFilled' : 'CircleCloseFilled'" />
                      </el-icon>
                      <span class="test-name">{{ getTestDisplayName(testName) }}</span>
                    </div>
                    <div class="test-message">{{ test.message }}</div>
                    <div v-if="'count' in test && test.count !== undefined" class="test-count">
                      数量: {{ test.count }}
                    </div>
                    <div v-if="'date' in test && test.date" class="test-date">
                      日期: {{ test.date }}
                    </div>
                  </div>
                </el-col>
              </el-row>
            </div>
          </div>
        </div>
      </div>
      
      <template #footer>
        <el-button @click="testDialogVisible = false">关闭</el-button>
        <el-button type="primary" @click="exportTestResults">
          <el-icon><Download /></el-icon>
          导出结果
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Connection,
  Operation,
  Download,
  SuccessFilled,
  CircleCloseFilled
} from '@element-plus/icons-vue'
import { testDataSources, type DataSourceTestResult } from '@/api/sync'
import DataSourceStatus from '@/components/Sync/DataSourceStatus.vue'
import SyncControl from '@/components/Sync/SyncControl.vue'
import SyncRecommendations from '@/components/Sync/SyncRecommendations.vue'
import SyncHistory from '@/components/Sync/SyncHistory.vue'

// 响应式数据
const testing = ref(false)
const testDialogVisible = ref(false)
const testResults = ref<DataSourceTestResult[] | null>(null)
const dataSourceStatusRef = ref()

// 运行全面测试
const runFullTest = async () => {
  try {
    testing.value = true
    ElMessage.info('正在进行全面测试，这可能需要20-30秒，请耐心等待...')

    const response = await testDataSources()
    if (response.success) {
      testResults.value = response.data.test_results
      testDialogVisible.value = true
      ElMessage.success('全面测试完成')
    } else {
      ElMessage.error(`测试失败: ${response.message}`)
    }
  } catch (err: any) {
    console.error('全面测试失败:', err)
    if (err.code === 'ECONNABORTED') {
      ElMessage.error('测试超时，请稍后重试。数据源测试需要较长时间，请确保网络连接稳定。')
    } else {
      ElMessage.error(`测试失败: ${err.message}`)
    }
  } finally {
    testing.value = false
  }
}

// 获取整体测试结果
const getOverallTestResult = (): 'success' | 'warning' | 'info' | 'error' => {
  if (!testResults.value) return 'info'

  const hasFailure = testResults.value.some(result =>
    !result.available || Object.values(result.tests).some(test => !test.success)
  )

  return hasFailure ? 'warning' : 'success'
}

// 获取测试项显示名称
const getTestDisplayName = (testName: string): string => {
  const nameMap: Record<string, string> = {
    stock_list: '股票列表',
    trade_date: '交易日期',
    daily_basic: '财务数据'
  }
  return nameMap[testName] || testName
}

// 导出测试结果
const exportTestResults = () => {
  if (!testResults.value) return
  
  const data = {
    timestamp: new Date().toISOString(),
    results: testResults.value
  }
  
  const blob = new Blob([JSON.stringify(data, null, 2)], { 
    type: 'application/json' 
  })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `data-source-test-results-${new Date().toISOString().split('T')[0]}.json`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  
  ElMessage.success('测试结果已导出')
}

// 处理同步完成事件
const handleSyncCompleted = (status: string) => {
  console.log('🎉 收到同步完成事件，状态:', status)
  // 这里可以触发历史记录刷新
  // 由于我们使用了组件引用，可以直接调用子组件的刷新方法
  // 或者发射一个全局事件让历史组件监听
}
</script>

<style scoped lang="scss">
.multi-source-sync {
  .page-header {
    margin-bottom: 24px;
    padding: 24px;
    background: linear-gradient(135deg, var(--el-color-primary-light-9) 0%, var(--el-color-primary-light-8) 100%);
    border-radius: 12px;
    
    .header-content {
      display: flex;
      align-items: center;
      justify-content: space-between;
      
      .header-info {
        .page-title {
          display: flex;
          align-items: center;
          margin: 0 0 8px 0;
          font-size: 28px;
          font-weight: 600;
          color: var(--el-text-color-primary);
          
          .title-icon {
            margin-right: 12px;
            color: var(--el-color-primary);
          }
        }
        
        .page-description {
          margin: 0;
          font-size: 16px;
          color: var(--el-text-color-regular);
          line-height: 1.5;
        }
      }
      
      .header-actions {
        flex-shrink: 0;
      }
    }
  }

  .page-content {
    .content-section {
      margin-bottom: 24px;
      
      &:last-child {
        margin-bottom: 0;
      }
    }
  }

  .test-results-dialog {
    .test-summary {
      margin-bottom: 24px;
    }
    
    .test-details {
      .test-result-item {
        margin-bottom: 24px;
        padding: 20px;
        border: 1px solid var(--el-border-color-light);
        border-radius: 8px;
        
        &:last-child {
          margin-bottom: 0;
        }
        
        .result-header {
          display: flex;
          align-items: center;
          gap: 12px;
          margin-bottom: 16px;
          
          .priority-info {
            font-size: 14px;
            color: var(--el-text-color-secondary);
          }
        }
        
        .result-tests {
          .test-item {
            padding: 12px;
            border: 1px solid var(--el-border-color-lighter);
            border-radius: 6px;
            height: 100%;
            
            .test-header {
              display: flex;
              align-items: center;
              gap: 6px;
              margin-bottom: 8px;
              
              .success-icon {
                color: var(--el-color-success);
              }
              
              .error-icon {
                color: var(--el-color-danger);
              }
              
              .test-name {
                font-weight: 500;
                font-size: 14px;
              }
            }
            
            .test-message {
              font-size: 12px;
              color: var(--el-text-color-regular);
              margin-bottom: 4px;
              line-height: 1.4;
            }
            
            .test-count,
            .test-date {
              font-size: 12px;
              color: var(--el-text-color-secondary);
            }
          }
        }
      }
    }
  }
}

@media (max-width: 768px) {
  .multi-source-sync {
    .page-header {
      .header-content {
        flex-direction: column;
        align-items: flex-start;
        gap: 16px;
        
        .header-actions {
          width: 100%;
          
          .el-button {
            width: 100%;
          }
        }
      }
    }
    
    .test-results-dialog {
      .test-details {
        .test-result-item {
          .result-tests {
            .el-col {
              margin-bottom: 12px;
            }
          }
        }
      }
    }
  }
}
</style>
