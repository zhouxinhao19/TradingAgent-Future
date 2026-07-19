<template>
  <div class="settings">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Setting /></el-icon>
        设置
      </h1>
      <p class="page-description">系统配置、缓存与数据管理</p>
    </div>

    <el-row :gutter="24">
      <el-col :span="6">
        <el-card class="settings-menu" shadow="never">
          <el-menu
            :default-active="activeTab"
            @select="handleMenuSelect"
            class="settings-nav"
          >
            <el-menu-item index="config">
              <el-icon><Tools /></el-icon>
              <span>配置管理</span>
            </el-menu-item>
            <el-menu-item index="cache">
              <el-icon><Coin /></el-icon>
              <span>缓存管理</span>
            </el-menu-item>
            <el-menu-item index="usage">
              <el-icon><DataAnalysis /></el-icon>
              <span>使用统计</span>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <el-col :span="18">
        <!-- 配置管理 -->
        <el-card v-show="activeTab === 'config'" class="settings-content" shadow="never">
          <template #header><h3>配置管理</h3></template>
          <el-alert
            title="LLM 与数据源配置"
            type="info"
            description="管理大模型供应商、数据源接入和市场分类配置"
            :closable="false"
            show-icon
            style="margin-bottom: 20px;"
          />
          <el-button type="primary" @click="goToConfigManagement">
            进入配置管理
          </el-button>
        </el-card>

        <!-- 缓存管理 -->
        <el-card v-show="activeTab === 'cache'" class="settings-content" shadow="never">
          <template #header><h3>缓存管理</h3></template>
          <el-alert
            title="缓存管理"
            type="info"
            description="管理系统缓存，清理过期数据"
            :closable="false"
            show-icon
            style="margin-bottom: 20px;"
          />
          <el-button type="primary" @click="goToCacheManagement">
            进入缓存管理
          </el-button>
        </el-card>

        <!-- 使用统计 -->
        <el-card v-show="activeTab === 'usage'" class="settings-content" shadow="never">
          <template #header><h3>使用统计</h3></template>
          <el-alert
            title="使用统计与计费"
            type="info"
            description="查看模型使用情况、Token 消耗和成本统计"
            :closable="false"
            show-icon
            style="margin-bottom: 20px;"
          />
          <el-button type="primary" @click="goToUsageStatistics">
            查看使用统计
          </el-button>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import {
  Setting,
  Tools,
  Coin,
  DataAnalysis
} from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const activeTab = ref('config')

function handleMenuSelect(index: string) {
  activeTab.value = index
}

const goToConfigManagement = () => router.push('/settings/config')
const goToCacheManagement = () => router.push('/settings/cache')
const goToUsageStatistics = () => router.push('/settings/usage')

onMounted(() => {
  const tab = route.query.tab as string
  if (tab && ['config', 'cache', 'usage'].includes(tab)) {
    activeTab.value = tab
  } else if (route.path === '/settings/cache') {
    activeTab.value = 'cache'
  } else if (route.path === '/settings/usage') {
    activeTab.value = 'usage'
  }
})
</script>

<style lang="scss" scoped>
.settings {
  .page-header {
    margin-bottom: 24px;
    .page-title {
      display: flex;
      align-items: center;
      gap: 8px;
      font-size: 24px;
      font-weight: 600;
      margin: 0 0 8px 0;
    }
    .page-description {
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }
  .settings-menu {
    .settings-nav { border: none; }
  }
  .settings-content {
    min-height: 300px;
  }
}
</style>
