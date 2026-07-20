<template>
  <div class="dashboard">
    <!-- 欢迎区域 -->
    <div class="welcome-section">
      <div class="welcome-content">
        <h1 class="welcome-title">
          欢迎使用 TradingAgents-CN
          <span class="version-badge">v1.0.1</span>
        </h1>
        <p class="welcome-subtitle">
          多智能体期货分析平台
        </p>
      </div>
      <div class="welcome-actions">
        <el-button type="primary" size="large" @click="goToCommodityAnalysis">
          <el-icon><TrendCharts /></el-icon>
          商品分析
        </el-button>
      </div>
    </div>

    <!-- 主要功能区域 -->
    <el-row :gutter="24" class="main-content">
      <!-- 左侧：快速操作 -->
      <el-col :span="16">
        <el-card class="quick-actions-card" header="快速操作">
          <div class="quick-actions">
            <div class="action-item" @click="goToCommodityAnalysis">
              <div class="action-icon">
                <el-icon><Box /></el-icon>
              </div>
              <div class="action-content">
                <h3>商品分析</h3>
                <p>多智能体决策链分析大宗商品期货</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToQueue">
              <div class="action-icon">
                <el-icon><List /></el-icon>
              </div>
              <div class="action-content">
                <h3>任务中心</h3>
                <p>查看和管理商品分析任务列表</p>
              </div>
              <el-icon class="action-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>

        <!-- 最近分析（任务中心联动） -->
        <RecentAnalysesCard style="margin-top: 24px;" />
      </el-col>

      <!-- 右侧：自选品种和快讯 -->
      <el-col :span="8">
        <!-- 我的自选品种 -->
        <FavoritesCard />

        <!-- 市场快讯（带标注、双标签页） -->
        <el-card class="market-news-card" style="margin-top: 24px;">
          <template #header>
            <div style="display:flex; align-items:center; justify-content:space-between">
              <span>市场快讯</span>
              <div style="display:flex; align-items:center; gap:8px;">
                <el-radio-group v-model="newsTab" size="small" @change="reloadMarketNews">
                  <el-radio-button value="all">全市场</el-radio-button>
                  <el-radio-button value="favorites">自选相关</el-radio-button>
                </el-radio-group>
                <el-button
                  size="small"
                  text
                  :loading="newsRefreshing"
                  @click="refreshNews"
                >
                  <el-icon><Refresh /></el-icon> 刷新
                </el-button>
              </div>
            </div>
          </template>
          <div v-if="filteredNews.length > 0" class="news-list">
            <div
              v-for="(news, idx) in filteredNews.slice(0, 8)"
              :key="idx"
              class="news-item"
              @click="openNewsUrl(news.url)"
            >
              <div class="news-meta">
                <el-tag size="small" :type="sentimentTag(news.llm_sentiment || news.sentiment)" effect="plain">
                  {{ news.llm_sentiment || news.sentiment }}
                </el-tag>
                <span v-for="rv in (news.relevant_varieties || []).slice(0, 3)" :key="rv" class="news-variety-tag">{{ rv }}</span>
                <span class="news-time">{{ newsRelativeTime(news.published_at || news.annotated_at) }}</span>
              </div>
              <div class="news-title">{{ news.llm_summary || news.title }}</div>
            </div>
          </div>
          <div v-else class="empty-state">
            <el-icon class="empty-icon"><InfoFilled /></el-icon>
            <p>{{ newsTab === 'favorites' ? '暂无自选品种相关新闻' : '暂无市场快讯' }}</p>
          </div>
        </el-card>

        <!-- 数据源和 LLM 供应商状态 -->
        <DataSourceLlmStatusCard style="margin-top: 24px;" />
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  TrendCharts,
  Box,
  List,
  ArrowRight,
  InfoFilled,
  Refresh,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import DataSourceLlmStatusCard from '@/components/Dashboard/DataSourceLlmStatusCard.vue'
import RecentAnalysesCard from '@/components/Dashboard/RecentAnalysesCard.vue'
import FavoritesCard from '@/components/Dashboard/FavoritesCard.vue'
import { commodityApi } from '@/api/commodity'
import { useFavoritesStore } from '@/stores/favorites'

const router = useRouter()
const favoritesStore = useFavoritesStore()

// 提取用户自选品种的品种代码列表（CU、AL 等）
const favoriteVarietyCodes = computed(() => {
  return favoritesStore.commodityItems
    .map(item => (item.full_symbol || '').split('.')[0]?.replace(/\d+$/, '') || '')
    .filter(Boolean)
})

// 市场快讯数据
const marketNews = ref<any[]>([])
const newsTab = ref<'all' | 'favorites'>('all')
const newsRefreshing = ref(false)

/** 基于当前 tab 加载新闻（借鉴期货详情页方式：tab 切换触发后端筛选） */
const filteredNews = computed(() => marketNews.value)

async function reloadMarketNews() {
  if (newsTab.value === 'all') {
    // 全市场: 拉取全部新闻
    await loadMarketNews()
  } else {
    // 自选相关: 借鉴详情页方式,逐品种从后端筛选
    // 确保自选已加载
    if (!favoritesStore.commodityItems.length && !favoritesStore.loading) {
      await favoritesStore.loadFavorites('commodity')
    }
    const codes = favoriteVarietyCodes.value
    if (!codes.length) {
      marketNews.value = []
      return
    }
    // 逐品种调 API（同详情页 store.loadNews(category, limit, variety)）
    const seen = new Set<string>()
    const items: any[] = []
    for (const code of codes) {
      try {
        const res = await commodityApi.getNews('all', 8, code)
        const batch = ((res as any)?.data?.items ?? []) as any[]
        for (const item of batch) {
          const key = item.title || item.content_hash || ''
          if (key && !seen.has(key)) {
            seen.add(key)
            items.push({ ...item, id: key })
          }
        }
      } catch {
        // 单个品种失败不影响其他品种
      }
    }
    items.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''))
    marketNews.value = items
  }
}

function sentimentTag(sent?: string): 'success' | 'danger' | 'info' {
  if (sent === 'positive') return 'success'
  if (sent === 'negative') return 'danger'
  return 'info'
}

// 实时相对时间 tick（每分钟驱动一次）
const tick = ref(0)
let tickTimer: ReturnType<typeof setInterval> | null = null
let newsPollTimer: ReturnType<typeof setInterval> | null = null

// 方法
const goToQueue = () => {
  router.push('/queue')
}

// ---------- 商品分析相关 ----------

/** 前往商品分析页 */
function goToCommodityAnalysis() {
  router.push('/commodity/analysis')
}

const openNewsUrl = (url?: string) => {
  if (url) {
    window.open(url, '_blank')
  } else {
    ElMessage.info('该新闻暂无详情链接')
  }
}

import { formatRelativeTime } from '@/utils/datetime'

/** 相对时间（依赖 tick 以自动刷新） */
const newsRelativeTime = (timeStr: string) => {
  void tick.value
  return formatRelativeTime(timeStr)
}

const loadMarketNews = async () => {
  try {
    const res = await commodityApi.getNews('all', 20)
    const body = (res as any)?.data
    if (body?.items?.length) {
      marketNews.value = body.items
        .map((item: any) => ({
          ...item,
          id: item.title || item.llm_summary || Math.random(),
        }))
        .sort((a: any, b: any) => {
          const ta = a.published_at || a.annotated_at || ''
          const tb = b.published_at || b.annotated_at || ''
          return tb.localeCompare(ta)
        })
    }
  } catch (error) {
    console.error('加载市场快讯失败:', error)
    marketNews.value = []
  }
}

/** 手动触发后端拉取+重新 LLM 标注 */
async function refreshNews() {
  newsRefreshing.value = true
  try {
    await commodityApi.refreshNews()
    ElMessage.success('已触发新闻刷新,约 30 秒后生效')
  } catch (e: any) {
    ElMessage.error(`刷新失败: ${e?.message || e}`)
  } finally {
    newsRefreshing.value = false
  }
}

// 生命周期
onMounted(async () => {
  await loadMarketNews()
  tickTimer = setInterval(() => { tick.value++ }, 60_000)
  newsPollTimer = setInterval(() => { reloadMarketNews() }, 30_000)
})

onUnmounted(() => {
  if (tickTimer) {
    clearInterval(tickTimer)
    tickTimer = null
  }
  if (newsPollTimer) {
    clearInterval(newsPollTimer)
    newsPollTimer = null
  }
})
</script>

<style lang="scss" scoped>
.dashboard {
  .welcome-section {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    border-radius: 12px;
    padding: 40px;
    color: white;
    margin-bottom: 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;

    .welcome-content {
      .welcome-title {
        font-size: 32px;
        font-weight: 600;
        margin: 0 0 12px 0;
        display: flex;
        align-items: center;
        gap: 16px;

        .version-badge {
          background: rgba(255, 255, 255, 0.2);
          padding: 4px 12px;
          border-radius: 20px;
          font-size: 14px;
          font-weight: 400;
        }
      }

      .welcome-subtitle {
        font-size: 16px;
        opacity: 0.9;
        margin: 0;
      }
    }

    .welcome-actions {
      display: flex;
      gap: 16px;
    }
  }

  .quick-actions-card {
    .quick-actions {
      display: grid;
      gap: 16px;

      .action-item {
        display: flex;
        align-items: center;
        gap: 16px;
        padding: 20px;
        border: 1px solid var(--el-border-color-lighter);
        border-radius: 8px;
        cursor: pointer;
        transition: all 0.3s ease;

        &:hover {
          border-color: var(--el-color-primary);
          background-color: var(--el-color-primary-light-9);
        }

        .action-icon {
          width: 40px;
          height: 40px;
          border-radius: 8px;
          background: var(--el-color-primary-light-8);
          display: flex;
          align-items: center;
          justify-content: center;
          color: var(--el-color-primary);
          font-size: 20px;
        }

        .action-content {
          flex: 1;

          h3 {
            margin: 0 0 4px 0;
            font-size: 16px;
            font-weight: 600;
            color: var(--el-text-color-primary);
          }

          p {
            margin: 0;
            font-size: 14px;
            color: var(--el-text-color-regular);
          }
        }

        .action-arrow {
          color: var(--el-text-color-placeholder);
          transition: transform 0.3s ease;
        }

        &:hover .action-arrow {
          transform: translateX(4px);
        }
      }
    }
  }

    .system-status-card {
    .status-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 8px 0;

      &:not(:last-child) {
        border-bottom: 1px solid var(--el-border-color-lighter);
      }

      .status-label {
        color: var(--el-text-color-regular);
      }

      .status-value {
        font-weight: 600;
        color: var(--el-text-color-primary);
      }
    }
  }

  .market-news-card {
    .news-list {
      .news-item {
        padding: 10px 0;
        cursor: pointer;
        border-bottom: 1px solid var(--el-border-color-lighter);

        &:last-child {
          border-bottom: none;
        }

        &:hover {
          background-color: var(--el-fill-color-lighter);
          margin: 0 -16px;
          padding: 10px 16px;
          border-radius: 4px;
        }
      }

      .news-meta {
        display: flex;
        align-items: center;
        gap: 6px;
        margin-bottom: 4px;
      }

      .news-variety-tag {
        font-size: 11px;
        background: var(--el-color-primary-light-9);
        color: var(--el-color-primary);
        padding: 1px 6px;
        border-radius: 3px;
      }

      .news-title {
        font-size: 14px;
        color: var(--el-text-color-primary);
        line-height: 1.4;
        margin-left: 0;
      }

      .news-time {
        font-size: 12px;
        color: var(--el-text-color-placeholder);
        white-space: nowrap;
      }
    }
  }

  .tips-card {
    .tip-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 0;
      font-size: 14px;
      color: var(--el-text-color-regular);

      .tip-icon {
        color: var(--el-color-primary);
      }
    }
  }

  .favorites-card {

  }

  /* 空数据状态（快讯暂无时） */
  .empty-state {
    text-align: center; padding: 20px 0;
    .empty-icon { font-size: 48px; color: var(--el-text-color-placeholder); }
    p { color: var(--el-text-color-secondary); font-size: 14px; }
  }
}
</style>
