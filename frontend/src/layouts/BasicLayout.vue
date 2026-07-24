<template>
  <div class="basic-layout">
    <!-- 侧边栏 — 深色品牌风格 -->
    <aside
      class="sidebar"
      :class="{ collapsed: appStore.sidebarCollapsed }"
      :style="{ width: appStore.actualSidebarWidth + 'px' }"
    >
      <div class="sidebar-header">
        <div class="logo">
          <span class="logo-text">TradingAgents-Future</span>
        </div>
      </div>

      <nav class="sidebar-nav">
        <SidebarMenu />
      </nav>

      <div class="sidebar-footer">
        <UserProfile />
      </div>
    </aside>

    <!-- 移动端蒙层 -->
    <div
      v-if="isMobile && !appStore.sidebarCollapsed"
      class="sidebar-overlay"
      @click="appStore.setSidebarCollapsed(true)"
    />

    <!-- 主内容区 -->
    <div class="main-container" :style="{ marginLeft: appStore.actualSidebarWidth + 'px' }" @click="handleMainClick">
      <!-- 顶部导航栏 -->
      <header class="header">
        <div class="header-left">
          <button class="sidebar-toggle-btn" @click.stop="appStore.toggleSidebar()">
            <el-icon :size="18"><Fold v-if="!appStore.sidebarCollapsed" /><Expand v-else /></el-icon>
          </button>
          <Breadcrumb />
        </div>

        <div class="header-right">
          <HeaderActions />
        </div>
      </header>

      <!-- 页面内容 -->
      <main class="main-content">
        <div class="content-wrapper">
          <router-view v-slot="{ Component, route }">
            <transition
              :name="route.meta.transition || 'fade'"
              mode="out-in"
              appear
            >
              <keep-alive :include="keepAliveComponents">
                <component :is="Component" :key="route.fullPath" />
              </keep-alive>
            </transition>
          </router-view>
        </div>
      </main>

      <!-- 页脚 -->
      <footer class="footer">
        <AppFooter />
      </footer>
    </div>

    <!-- 回到顶部 -->
    <el-backtop :right="40" :bottom="40" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'
import SidebarMenu from '@/components/Layout/SidebarMenu.vue'
import UserProfile from '@/components/Layout/UserProfile.vue'
import Breadcrumb from '@/components/Layout/Breadcrumb.vue'
import HeaderActions from '@/components/Layout/HeaderActions.vue'
import AppFooter from '@/components/Layout/AppFooter.vue'
import { Expand, Fold } from '@element-plus/icons-vue'

const appStore = useAppStore()
const route = useRoute()
const { width } = useWindowSize()

const keepAliveComponents = computed(() => [
  'Dashboard',
  'CommodityList',
  'AnalysisHistory',
  'QueueManagement'
])

const isMobile = computed(() => width.value < 768)

const handleMainClick = () => {
  if (isMobile.value && !appStore.sidebarCollapsed) {
    appStore.setSidebarCollapsed(true)
  }
}

watch(width, (newWidth) => {
  if (newWidth < 768 && !appStore.sidebarCollapsed) {
    appStore.setSidebarCollapsed(true)
  }
})

watch(() => route.fullPath, () => {
  if (isMobile.value) {
    appStore.setSidebarCollapsed(true)
  }
})
</script>

<style lang="scss" scoped>
.basic-layout {
  min-height: 100vh;
  background-color: var(--el-bg-color-page);
}

/* ── 侧边栏 ── */
.sidebar {
  position: fixed;
  top: 0;
  left: 0;
  height: 100vh;
  background-color: $sidebar-bg;
  transition: width var(--app-transition-slow);
  z-index: 1000;
  display: flex;
  flex-direction: column;
  overflow: hidden;

  &.collapsed {
    width: $sidebar-collapsed !important;
  }

  .sidebar-header {
    height: $header-height;
    display: flex;
    align-items: center;
    padding: 0 16px;
    flex-shrink: 0;

    .logo {
      display: flex;
      align-items: center;

      .logo-text {
        font-size: 15px;
        font-weight: 700;
        color: #ffffff;
        white-space: nowrap;
        letter-spacing: -0.01em;
      }
    }
  }

  .sidebar-nav {
    flex: 1;
    overflow-y: auto;
  }

  .sidebar-footer {
    flex-shrink: 0;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
  }
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.40);
  z-index: 950;
}

/* ── 主内容区 ── */
.main-container {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  transition: margin-left var(--app-transition-slow);
}

/* ── 顶栏 ── */
.header {
  height: $header-height;
  background-color: var(--app-header-bg);
  border-bottom: 1px solid var(--el-border-color-light);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  position: sticky;
  top: 0;
  z-index: 999;
  box-shadow: var(--app-shadow-sm);

  .header-left {
    display: flex;
    align-items: center;
    gap: 12px;
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.sidebar-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border: none;
  background: transparent;
  border-radius: 8px;
  color: var(--el-text-color-secondary);
  cursor: pointer;
  transition: all var(--app-transition-fast);

  &:hover {
    background: var(--el-fill-color-light);
    color: var(--el-text-color-primary);
  }
}

/* ── 主内容 ── */
.main-content {
  flex: 1;
  padding: $spacing-lg;

  .content-wrapper {
    max-width: $content-max-width;
    margin: 0 auto;
  }
}

/* ── 页脚 ── */
.footer {
  height: $header-height;
  border-top: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

/* ── 路由过渡动画 ── */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.25s ease;
}
.slide-left-enter-from {
  transform: translateX(20px);
  opacity: 0;
}
.slide-left-leave-to {
  transform: translateX(-20px);
  opacity: 0;
}

/* ── 响应式 ── */
@media (max-width: $breakpoint-sm) {
  .sidebar {
    transform: translateX(-100%);
    &:not(.collapsed) {
      transform: translateX(0);
    }
  }
  .main-container {
    margin-left: 0 !important;
  }
  .main-content {
    padding: 16px;
  }
  .header {
    padding: 0 12px;
  }
}
</style>
