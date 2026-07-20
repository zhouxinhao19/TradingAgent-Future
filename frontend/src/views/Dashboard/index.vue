<template>
  <div class="dashboard">
    <!-- 欢迎区域 — "精密终端"风格 -->
    <section class="hero">
      <div class="hero-body">
        <div class="hero-text">
          <h1 class="hero-title">TradingAgents-Future</h1>
          <p class="hero-subtitle">多智能体期货分析平台 — 技术面 · 产业链 · 持仓情绪 · 新闻语义，四维决策链驱动</p>
        </div>
        <div class="hero-actions">
          <el-button type="primary" size="large" @click="goToCommodityAnalysis">
            <el-icon><TrendCharts /></el-icon>
            开始分析
          </el-button>
          <el-button size="large" @click="goToCommodityList">
            <el-icon><Box /></el-icon>
            浏览品种
          </el-button>
        </div>
      </div>
      <!-- 签名元素：数据脉动条 -->
      <div class="hero-pulse">
        <span class="pulse-bar" v-for="i in 40" :key="i" :style="{ animationDelay: `${i * 0.08}s` }" />
      </div>
    </section>

    <!-- 主要功能区域 -->
    <el-row :gutter="20" class="dashboard-grid">
      <!-- 左侧 -->
      <el-col :span="16">
        <!-- 快速操作 -->
        <el-card class="section-card" shadow="never">
          <template #header>
            <div class="card-header-row">
              <span class="card-header-title">快速操作</span>
            </div>
          </template>
          <div class="quick-actions">
            <div class="action-item" @click="goToCommodityAnalysis">
              <div class="action-icon action-icon--analysis">
                <el-icon :size="20"><TrendCharts /></el-icon>
              </div>
              <div class="action-body">
                <h4>商品分析</h4>
                <p>多智能体决策链分析大宗商品期货，技术面 + 产业链 + 持仓情绪 + 新闻语义</p>
              </div>
              <el-icon class="action-chevron"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToTasks">
              <div class="action-icon action-icon--tasks">
                <el-icon :size="20"><List /></el-icon>
              </div>
              <div class="action-body">
                <h4>任务中心</h4>
                <p>查看和管理商品分析任务列表，跟踪批量分析进度</p>
              </div>
              <el-icon class="action-chevron"><ArrowRight /></el-icon>
            </div>

            <div class="action-item" @click="goToFavorites">
              <div class="action-icon action-icon--fav">
                <el-icon :size="20"><Star /></el-icon>
              </div>
              <div class="action-body">
                <h4>自选品种</h4>
                <p>管理关注品种，快速查看行情和涨跌幅</p>
              </div>
              <el-icon class="action-chevron"><ArrowRight /></el-icon>
            </div>
          </div>
        </el-card>

        <!-- 最近分析 -->
        <RecentAnalysesCard style="margin-top: 20px;" />
      </el-col>

      <!-- 右侧 -->
      <el-col :span="8">
        <!-- 自选品种 -->
        <FavoritesCard />

        <!-- 市场快讯 -->
        <el-card class="section-card news-card" shadow="never" style="margin-top: 20px;">
          <template #header>
            <div class="card-header-row">
              <span class="card-header-title">市场快讯</span>
              <div class="card-header-actions">
                <el-radio-group v-model="newsTab" size="small" @change="reloadMarketNews">
                  <el-radio-button value="all">全市场</el-radio-button>
                  <el-radio-button value="favorites">自选</el-radio-button>
                </el-radio-group>
                <el-button size="small" text :loading="newsRefreshing" @click="refreshNews">
                  <el-icon><Refresh /></el-icon>
                </el-button>
              </div>
            </div>
          </template>
          <div v-if="filteredNews.length > 0" class="news-list">
            <div
              v-for="(news, idx) in filteredNews.slice(0, 6)"
              :key="idx"
              class="news-item"
              @click="openNewsUrl(news.url)"
            >
              <div class="news-head">
                <el-tag size="small" :type="sentimentTag(news.llm_sentiment || news.sentiment)" effect="plain">
                  {{ news.llm_sentiment || news.sentiment }}
                </el-tag>
                <span class="news-time">{{ newsRelativeTime(news.published_at || news.annotated_at) }}</span>
              </div>
              <div class="news-title">{{ news.llm_summary || news.title }}</div>
              <div class="news-tags" v-if="(news.relevant_varieties || []).length">
                <span v-for="rv in (news.relevant_varieties || []).slice(0, 3)" :key="rv" class="news-tag">{{ rv }}</span>
              </div>
            </div>
          </div>
          <div v-else class="empty-state">
            <el-icon class="empty-icon"><InfoFilled /></el-icon>
            <p>{{ newsTab === 'favorites' ? '暂无自选品种相关新闻' : '暂无市场快讯' }}</p>
          </div>
        </el-card>

        <!-- 数据源和 LLM 状态 -->
        <DataSourceLlmStatusCard style="margin-top: 20px;" />
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
  Star,
} from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import DataSourceLlmStatusCard from '@/components/Dashboard/DataSourceLlmStatusCard.vue'
import RecentAnalysesCard from '@/components/Dashboard/RecentAnalysesCard.vue'
import FavoritesCard from '@/components/Dashboard/FavoritesCard.vue'
import { commodityApi } from '@/api/commodity'
import { useFavoritesStore } from '@/stores/favorites'

const router = useRouter()
const favoritesStore = useFavoritesStore()

const favoriteVarietyCodes = computed(() => {
  return favoritesStore.commodityItems
    .map(item => (item.full_symbol || '').split('.')[0]?.replace(/\d+$/, '') || '')
    .filter(Boolean)
})

const marketNews = ref<any[]>([])
const newsTab = ref<'all' | 'favorites'>('all')
const newsRefreshing = ref(false)

const filteredNews = computed(() => marketNews.value)

async function reloadMarketNews() {
  if (newsTab.value === 'all') {
    await loadMarketNews()
  } else {
    if (!favoritesStore.commodityItems.length && !favoritesStore.loading) {
      await favoritesStore.loadFavorites('commodity')
    }
    const codes = favoriteVarietyCodes.value
    if (!codes.length) {
      marketNews.value = []
      return
    }
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
      } catch { /* 单品种失败不影响其他 */ }
    }
    items.sort((a, b) => (b.published_at || '').localeCompare(a.published_at || ''))
    marketNews.value = items
  }
}

function sentimentTag(sent?: string): 'success' | 'danger' | 'info' {
  if (sent === 'positive') return 'danger'   // 利好 → 红（中国习惯）
  if (sent === 'negative') return 'success'   // 利空 → 绿
  return 'info'
}

const tick = ref(0)
let tickTimer: ReturnType<typeof setInterval> | null = null
let newsPollTimer: ReturnType<typeof setInterval> | null = null

function goToCommodityAnalysis() { router.push('/commodity/analysis') }
function goToCommodityList() { router.push('/commodity/list') }
function goToTasks() { router.push('/tasks') }
function goToFavorites() { router.push('/favorites') }

const openNewsUrl = (url?: string) => {
  if (url) window.open(url, '_blank')
  else ElMessage.info('该新闻暂无详情链接')
}

import { formatRelativeTime } from '@/utils/datetime'

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

async function refreshNews() {
  newsRefreshing.value = true
  try {
    await commodityApi.refreshNews()
    ElMessage.success('已触发新闻刷新，约 30 秒后生效')
  } catch (e: any) {
    ElMessage.error(`刷新失败: ${e?.message || e}`)
  } finally {
    newsRefreshing.value = false
  }
}

onMounted(async () => {
  await loadMarketNews()
  tickTimer = setInterval(() => { tick.value++ }, 60_000)
  newsPollTimer = setInterval(() => { reloadMarketNews() }, 30_000)
})

onUnmounted(() => {
  if (tickTimer) { clearInterval(tickTimer); tickTimer = null }
  if (newsPollTimer) { clearInterval(newsPollTimer); newsPollTimer = null }
})
</script>

<style lang="scss" scoped>
.dashboard {
  /* ── 欢迎区域 ── */
  .hero {
    background: linear-gradient(135deg, #1a3048 0%, #162031 40%, #1a3a54 100%);
    border-radius: 12px;
    padding: 36px 40px 28px;
    margin-bottom: 24px;
    position: relative;
    overflow: hidden;

    .hero-body {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      position: relative;
      z-index: 1;
    }

    .hero-text {
      .hero-title {
        font-size: 28px;
        font-weight: 700;
        color: #ffffff;
        margin: 0 0 8px 0;
        letter-spacing: -0.02em;
      }
      .hero-subtitle {
        font-size: 14px;
        color: rgba(255, 255, 255, 0.65);
        margin: 0;
        max-width: 500px;
        line-height: 1.5;
      }
    }

    .hero-actions {
      display: flex;
      gap: 12px;
      flex-shrink: 0;

      :deep(.el-button--primary) {
        background-color: $sidebar-accent;
        border-color: $sidebar-accent;
        &:hover {
          background-color: #ecb44d;
          border-color: #ecb44d;
        }
      }
      :deep(.el-button:not(.el-button--primary)) {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.15);
        color: rgba(255, 255, 255, 0.9);
        &:hover {
          background: rgba(255, 255, 255, 0.14);
          border-color: rgba(255, 255, 255, 0.25);
        }
      }
    }

    /* 数据脉动条 */
    .hero-pulse {
      display: flex;
      gap: 3px;
      margin-top: 24px;
      position: relative;
      z-index: 1;

      .pulse-bar {
        flex: 1;
        height: 2px;
        background: rgba(255, 255, 255, 0.15);
        border-radius: 1px;
        animation: pulseFade 2.4s ease-in-out infinite;
        opacity: 0.3;
      }
    }
  }

  /* ── 通用卡片 ── */
  .section-card {
    border-radius: 10px;
    :deep(.el-card__header) {
      padding: 16px 20px;
      border-bottom: 1px solid var(--el-border-color-lighter);
    }
    :deep(.el-card__body) {
      padding: 20px;
    }
  }

  .card-header-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .card-header-title {
    font-size: 15px;
    font-weight: 650;
    color: var(--el-text-color-primary);
  }
  .card-header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  /* ── 快速操作 ── */
  .quick-actions {
    display: flex;
    flex-direction: column;
    gap: 12px;

    .action-item {
      display: flex;
      align-items: center;
      gap: 14px;
      padding: 18px 20px;
      border: 1px solid var(--el-border-color-lighter);
      border-radius: 10px;
      cursor: pointer;
      transition: all var(--app-transition-normal);

      &:hover {
        border-color: var(--el-color-primary-light-5);
        background-color: var(--el-color-primary-light-9);
        box-shadow: var(--app-shadow-sm);

        .action-chevron {
          transform: translateX(3px);
          color: var(--el-color-primary);
        }
      }
    }

    .action-icon {
      width: 44px;
      height: 44px;
      border-radius: 10px;
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;

      &--analysis { background: #e8f4fd; color: #3b8cbf; }
      &--tasks    { background: #fdf3e5; color: #e0902a; }
      &--fav      { background: #fce8e8; color: #dc4e4e; }
    }

    .action-body {
      flex: 1;
      h4 {
        font-size: 15px;
        font-weight: 600;
        color: var(--el-text-color-primary);
        margin: 0 0 2px 0;
      }
      p {
        font-size: 13px;
        color: var(--el-text-color-secondary);
        margin: 0;
        line-height: 1.4;
      }
    }

    .action-chevron {
      color: var(--el-text-color-placeholder);
      transition: all var(--app-transition-fast);
    }
  }

  /* ── 新闻卡片 ── */
  .news-card {
    .news-list {
      .news-item {
        padding: 10px 0;
        cursor: pointer;
        border-bottom: 1px solid var(--el-border-color-lighter);
        transition: background var(--app-transition-fast);

        &:last-child { border-bottom: none; }

        &:hover {
          background: var(--el-fill-color-lighter);
          margin: 0 -20px;
          padding-left: 20px;
          padding-right: 20px;
          border-radius: 6px;
        }
      }
    }

    .news-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 4px;
    }

    .news-time {
      font-size: 11px;
      color: var(--el-text-color-placeholder);
    }

    .news-title {
      font-size: 13px;
      color: var(--el-text-color-primary);
      line-height: 1.45;
    }

    .news-tags {
      display: flex;
      gap: 4px;
      margin-top: 4px;
    }

    .news-tag {
      font-size: 10px;
      background: var(--el-color-primary-light-9);
      color: var(--el-color-primary);
      padding: 1px 6px;
      border-radius: 3px;
      font-weight: 500;
    }
  }

  /* ── 空状态 ── */
  .empty-state {
    text-align: center;
    padding: 24px 0;
    .empty-icon { font-size: 40px; color: var(--el-text-color-placeholder); }
    p { color: var(--el-text-color-secondary); font-size: 13px; margin-top: 8px; }
  }
}

/* ── 动画 ── */
@keyframes pulseFade {
  0%, 100% { opacity: 0.3; }
  50%      { opacity: 0.8; }
}
</style>
