<template>
  <div id="app" class="app-container">
    <!-- 网络状态指示器 -->
    <NetworkStatus />

    <!-- 主要内容区域 -->
    <router-view v-slot="{ Component, route }">
      <transition
        :name="route?.meta?.transition || 'fade'"
        mode="out-in"
        appear
      >
        <keep-alive :include="keepAliveComponents">
          <component :is="Component" :key="route?.fullPath || 'default'" />
        </keep-alive>
      </transition>
    </router-view>

    <!-- 配置向导 -->
    <ConfigWizard
      v-model="showConfigWizard"
      @complete="handleWizardComplete"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import NetworkStatus from '@/components/NetworkStatus.vue'
import ConfigWizard from '@/components/ConfigWizard.vue'
import axios from 'axios'

// 需要缓存的组件
const keepAliveComponents = computed(() => [
  'Dashboard',
  'StockScreening',
  'AnalysisHistory'
])

// 配置向导
const showConfigWizard = ref(false)

// 检查是否需要显示配置向导
const checkFirstTimeSetup = async () => {
  try {
    // 检查是否已经完成过配置向导
    const wizardCompleted = localStorage.getItem('config_wizard_completed')
    if (wizardCompleted === 'true') {
      return
    }

    // 验证配置完整性
    const response = await axios.get('/api/system/config/validate')
    if (response.data.success) {
      const result = response.data.data

      // 如果有缺少的必需配置，显示配置向导
      if (!result.success && result.missing_required?.length > 0) {
        // 延迟显示，等待页面加载完成
        setTimeout(() => {
          showConfigWizard.value = true
        }, 1000)
      }
    }
  } catch (error) {
    console.error('检查配置失败:', error)
  }
}

// 配置向导完成处理
const handleWizardComplete = async (data: any) => {
  try {
    // 标记配置向导已完成
    localStorage.setItem('config_wizard_completed', 'true')

    ElMessage.success({
      message: '配置完成！欢迎使用 TradingAgents-CN',
      duration: 3000
    })

    // 可以在这里保存配置到后端
    console.log('配置数据:', data)
  } catch (error) {
    console.error('保存配置失败:', error)
    ElMessage.error('保存配置失败，请稍后重试')
  }
}

// 生命周期
onMounted(() => {
  checkFirstTimeSetup()
})
</script>

<style lang="scss">
.app-container {
  min-height: 100vh;
  background-color: var(--el-bg-color-page);
  transition: background-color 0.3s ease;
}

.global-loading {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  background: linear-gradient(90deg, #409EFF 0%, #67C23A 100%);
  height: 2px;
}

// 路由过渡动画
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.slide-left-enter-active,
.slide-left-leave-active {
  transition: all 0.3s ease;
}

.slide-left-enter-from {
  transform: translateX(30px);
  opacity: 0;
}

.slide-left-leave-to {
  transform: translateX(-30px);
  opacity: 0;
}

.slide-up-enter-active,
.slide-up-leave-active {
  transition: all 0.3s ease;
}

.slide-up-enter-from {
  transform: translateY(30px);
  opacity: 0;
}

.slide-up-leave-to {
  transform: translateY(-30px);
  opacity: 0;
}

// 响应式设计
@media (max-width: 768px) {
  .app-container {
    padding: 0;
  }
}
</style>
