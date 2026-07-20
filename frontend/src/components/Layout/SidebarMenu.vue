<template>
  <div class="sidebar-menu-wrapper">
    <!-- 签名元素：顶部细微暖金装饰线 -->
    <div class="sidebar-accent-line" />

    <el-menu
      :default-active="activeMenu"
      :collapse="appStore.sidebarCollapsed"
      :unique-opened="true"
      router
      class="sidebar-menu"
    >
      <el-menu-item index="/dashboard">
        <el-icon><Odometer /></el-icon>
        <template #title>仪表板</template>
      </el-menu-item>

      <el-menu-item index="/tasks">
        <el-icon><List /></el-icon>
        <template #title>任务中心</template>
      </el-menu-item>

      <!-- 大宗商品(Phase 3a · Feature Flag 控制) -->
      <el-menu-item v-if="featureStore.commodityEnabled" index="/commodity/list">
        <el-icon><Box /></el-icon>
        <template #title>商品列表</template>
      </el-menu-item>
      <el-menu-item v-if="featureStore.commodityAnalysis" index="/commodity/analysis">
        <el-icon><TrendCharts /></el-icon>
        <template #title>商品分析</template>
      </el-menu-item>
      <el-menu-item v-if="featureStore.commodityEnabled" index="/favorites">
        <el-icon><Star /></el-icon>
        <template #title>自选品种</template>
      </el-menu-item>

      <el-sub-menu index="/settings">
        <template #title>
          <el-icon><Setting /></el-icon>
          <span>设置</span>
        </template>
        <el-menu-item index="/settings">系统配置</el-menu-item>
        <el-menu-item index="/settings/config">配置管理</el-menu-item>
        <el-menu-item index="/settings/cache">缓存管理</el-menu-item>
        <el-menu-item index="/settings/usage">使用统计</el-menu-item>
      </el-sub-menu>
    </el-menu>

    <!-- 底部版本信息 -->
    <div class="sidebar-version" v-show="!appStore.sidebarCollapsed">
      <span class="version-text">TradingAgents-Future</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useFeatureStore } from '@/stores/feature'
import {
  Odometer,
  List,
  Setting,
  TrendCharts,
  Box,
  Star,
} from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()
const featureStore = useFeatureStore()

const activeMenu = computed(() => route.path)

onMounted(() => {
  featureStore.load()
})
</script>

<style lang="scss" scoped>
.sidebar-menu-wrapper {
  display: flex;
  flex-direction: column;
  height: 100%;
  position: relative;
}

/* 签名元素：暖金装饰线 */
.sidebar-accent-line {
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent 0%,
    $sidebar-accent 50%,
    transparent 100%
  );
  opacity: 0.6;
  margin: 0 16px;
}

.sidebar-menu {
  flex: 1;
  border: none !important;
  background: transparent;
  padding: 8px 0;
  overflow-y: auto;

  /* 菜单项 */
  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    height: 42px;
    line-height: 42px;
    margin: 2px 8px;
    border-radius: 8px;
    color: $sidebar-text;
    font-size: 14px;
    transition: all var(--app-transition-fast);

    &:hover {
      color: #c8d6e0;
      background-color: $sidebar-bg;  /* 修复：需要用实际颜色 */
      background-color: var(--app-sidebar-item-hover-bg);
    }
  }

  :deep(.el-menu-item) {
    &.is-active {
      color: #ffffff;
      background-color: var(--app-sidebar-item-active-bg);
      font-weight: 600;

      &::before {
        content: '';
        position: absolute;
        left: 0;
        top: 50%;
        transform: translateY(-50%);
        width: 3px;
        height: 20px;
        background: var(--app-sidebar-accent);
        border-radius: 0 2px 2px 0;
      }
    }
  }

  /* 子菜单标题 */
  :deep(.el-sub-menu__title) {
    .el-sub-menu__icon-arrow {
      color: $sidebar-text;
    }
  }

  /* 子菜单弹出框 */
  :deep(.el-menu--inline) {
    background: rgba(0, 0, 0, 0.15);
    border-radius: 6px;
    margin: 2px 8px;

    .el-menu-item {
      padding-left: 56px !important;
      height: 38px;
      line-height: 38px;
      font-size: 13px;

      &.is-active {
        &::before { display: none; }
      }
    }
  }

  /* 折叠状态 */
  &.el-menu--collapse {
    width: 64px;
    overflow: hidden;

    :deep(.el-menu-item) {
      margin: 2px 7px;
      padding: 0 !important;
      justify-content: center;

      .el-icon {
        margin-right: 0 !important;
        vertical-align: middle;
      }
    }

    :deep(.el-sub-menu__title) {
      margin: 2px 7px;
      padding: 0 !important;
      justify-content: center;

      .el-icon {
        margin-right: 0 !important;
      }

      .el-sub-menu__icon-arrow {
        display: none;
      }
    }

    :deep(.el-menu-item.is-active::before) {
      display: none;
    }
  }
}

/* 底部版本 */
.sidebar-version {
  padding: 12px 20px 16px;
  .version-text {
    font-size: 11px;
    color: rgba(255, 255, 255, 0.25);
    letter-spacing: 0.04em;
  }
}
</style>
