<template>
  <div class="ds-llm-status-card">
    <el-card class="status-card" shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="header-icon"><Monitor /></el-icon>
            <span class="header-title">系统状态</span>
          </div>
          <div class="header-right">
            <el-button
              type="primary"
              size="small"
              link
              :loading="refreshing"
              @click="refreshAll"
            >
              <el-icon><Refresh /></el-icon>
              刷新
            </el-button>
          </div>
        </div>
      </template>

      <div v-loading="loading" class="card-content">
        <!-- 数据源状态 -->
        <div class="section">
          <div class="section-header">
            <el-icon class="section-icon"><Connection /></el-icon>
            <span class="section-title">数据源</span>
          </div>
          <div class="item-list">
            <div
              v-for="source in dataSources"
              :key="source.name"
              class="status-item"
              :class="{ available: source.available }"
            >
              <div class="item-left">
                <el-icon
                  class="status-dot"
                  :class="source.available ? 'dot-success' : 'dot-error'"
                >
                  <component :is="source.available ? 'SuccessFilled' : 'CircleCloseFilled'" />
                </el-icon>
                <span class="item-name">{{ source.name.toUpperCase() }}</span>
              </div>
              <div class="item-right">
                <el-tag
                  :type="source.available ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ source.available ? '可用' : '不可用' }}
                </el-tag>
              </div>
            </div>
          </div>
        </div>

        <el-divider class="section-divider" />

        <!-- LLM 供应商状态 -->
        <div class="section">
          <div class="section-header">
            <el-icon class="section-icon"><Cpu /></el-icon>
            <span class="section-title">LLM 供应商</span>
          </div>
          <div class="item-list">
            <div
              v-for="provider in llmProviders"
              :key="provider.id"
              class="status-item"
              :class="{ active: provider.is_active }"
            >
              <div class="item-left">
                <el-icon
                  class="status-dot"
                  :class="provider.is_active ? 'dot-success' : 'dot-error'"
                >
                  <component :is="provider.is_active ? 'SuccessFilled' : 'CircleCloseFilled'" />
                </el-icon>
                <span class="item-name">{{ provider.display_name || provider.name }}</span>
              </div>
              <div class="item-right">
                <el-tag
                  :type="provider.is_active ? 'success' : 'danger'"
                  size="small"
                  effect="plain"
                >
                  {{ provider.is_active ? '已启用' : '已禁用' }}
                </el-tag>
              </div>
            </div>
            <div v-if="llmProviders.length === 0" class="empty-hint">
              暂无 LLM 供应商配置
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import {
  Monitor,
  Connection,
  Cpu,
  Refresh,
  SuccessFilled,
  CircleCloseFilled
} from '@element-plus/icons-vue'
import { getDataSourcesStatus, type DataSourceStatus } from '@/api/sync'
import { configApi, type LLMProvider } from '@/api/config'

// 响应式数据
const loading = ref(false)
const refreshing = ref(false)
const dataSources = ref<DataSourceStatus[]>([])
const llmProviders = ref<LLMProvider[]>([])
const refreshTimer = ref<NodeJS.Timeout | null>(null)

// 获取数据源状态
const fetchDataSources = async () => {
  try {
    const response = await getDataSourcesStatus()
    if (response.success) {
      dataSources.value = response.data
        .sort((a, b) => b.priority - a.priority)
        .slice(0, 5) // 最多显示 5 个数据源
    }
  } catch (err: any) {
    console.error('获取数据源状态失败:', err)
  }
}

// 获取 LLM 供应商状态
const fetchLLMProviders = async () => {
  try {
    const providers = await configApi.getLLMProviders()
    llmProviders.value = (providers || []).slice(0, 8) // 最多显示 8 个供应商
  } catch (err: any) {
    console.error('获取 LLM 供应商状态失败:', err)
  }
}

// 刷新所有状态
const refreshAll = async () => {
  refreshing.value = true
  await Promise.all([
    fetchDataSources(),
    fetchLLMProviders()
  ])
  refreshing.value = false
}

// 自动轮询（每 30 秒刷新一次）
const startPolling = () => {
  stopPolling()
  refreshTimer.value = setInterval(() => {
    fetchDataSources()
    fetchLLMProviders()
  }, 30000)
}

const stopPolling = () => {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value)
    refreshTimer.value = null
  }
}

// 组件挂载
onMounted(async () => {
  loading.value = true
  await Promise.all([
    fetchDataSources(),
    fetchLLMProviders()
  ])
  loading.value = false
  startPolling()
})

// 组件卸载
onUnmounted(() => {
  stopPolling()
})
</script>

<style scoped lang="scss">
.ds-llm-status-card {
  .status-card {
    height: 100%;

    .card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;

      .header-left {
        display: flex;
        align-items: center;

        .header-icon {
          margin-right: 8px;
          color: var(--el-color-primary);
        }

        .header-title {
          font-weight: 600;
          font-size: 16px;
        }
      }
    }
  }

  .card-content {
    .section {
      .section-header {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 12px;

        .section-icon {
          font-size: 16px;
          color: var(--el-color-primary);
        }

        .section-title {
          font-size: 14px;
          font-weight: 500;
          color: var(--el-text-color-primary);
        }
      }

      .item-list {
        .status-item {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 10px;
          margin-bottom: 6px;
          border-radius: 6px;
          background-color: var(--el-fill-color-lighter);
          transition: background-color 0.2s;

          &.available,
          &.active {
            background-color: var(--el-color-success-light-9);
          }

          .item-left {
            display: flex;
            align-items: center;
            gap: 8px;

            .status-dot {
              font-size: 14px;
            }

            .dot-success {
              color: var(--el-color-success);
            }

            .dot-error {
              color: var(--el-color-danger);
            }

            .item-name {
              font-size: 13px;
              font-weight: 500;
              color: var(--el-text-color-primary);
            }
          }

          .item-right {
            flex-shrink: 0;
          }
        }

        .empty-hint {
          text-align: center;
          padding: 16px;
          font-size: 13px;
          color: var(--el-text-color-secondary);
        }
      }
    }

    .section-divider {
      margin: 16px 0;
    }
  }
}
</style>