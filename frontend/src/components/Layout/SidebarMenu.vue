<template>
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

    <!-- 学习中心（暂屏蔽） -->
    <!--
    <el-menu-item index="/learning">
      <el-icon><Reading /></el-icon>
      <template #title>学习中心</template>
    </el-menu-item>
    -->

    <el-menu-item index="/tasks">
      <el-icon><List /></el-icon>
      <template #title>任务中心</template>
    </el-menu-item>

    <!-- 大宗商品(Phase 3a · Feature Flag 控制) — 提升到一级目录 -->
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
    <!-- 期货模拟交易（暂屏蔽） -->
    <!--
    <el-menu-item v-if="featureStore.commodityPaper" index="/commodity/paper">
      <el-icon><Box /></el-icon>
      <template #title>期货模拟交易</template>
    </el-menu-item>
    -->

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

    <!-- 关于（暂屏蔽） -->
    <!--
    <el-menu-item index="/about">
      <el-icon><InfoFilled /></el-icon>
      <template #title>关于</template>
    </el-menu-item>
    -->
  </el-menu>
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
  Star
} from '@element-plus/icons-vue'

const route = useRoute()
const appStore = useAppStore()
const featureStore = useFeatureStore()

const activeMenu = computed(() => route.path)

// 应用启动拉一次,后续守卫/菜单直接读 store
onMounted(() => {
  featureStore.load()
})
</script>

<style lang="scss" scoped>
.sidebar-menu {
  border: none;
  height: 100%;

  :deep(.el-menu-item),
  :deep(.el-sub-menu__title) {
    height: 48px;
    line-height: 48px;
  }

  :deep(.el-menu-item.is-active) {
    background-color: var(--el-color-primary-light-9);
    color: var(--el-color-primary);
  }
}
</style>
