<template>
  <div class="settings">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><Setting /></el-icon>
        系统设置
      </h1>
      <p class="page-description">
        个性化配置和系统偏好设置
      </p>
    </div>

    <el-row :gutter="24">
      <!-- 左侧：设置菜单 -->
      <el-col :span="6">
        <el-card class="settings-menu" shadow="never">
          <el-menu
            :default-active="activeTab"
            @select="handleMenuSelect"
            class="settings-nav"
          >
            <el-menu-item index="general">
              <el-icon><User /></el-icon>
              <span>通用设置</span>
            </el-menu-item>
            <el-menu-item index="appearance">
              <el-icon><Brush /></el-icon>
              <span>外观设置</span>
            </el-menu-item>
            <el-menu-item index="analysis">
              <el-icon><TrendCharts /></el-icon>
              <span>分析偏好</span>
            </el-menu-item>
            <el-menu-item index="notifications">
              <el-icon><Bell /></el-icon>
              <span>通知设置</span>
            </el-menu-item>
            <el-menu-item index="security">
              <el-icon><Lock /></el-icon>
              <span>安全设置</span>
            </el-menu-item>
            <el-menu-item index="about">
              <el-icon><InfoFilled /></el-icon>
              <span>关于系统</span>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <!-- 右侧：设置内容 -->
      <el-col :span="18">
        <!-- 通用设置 -->
        <el-card v-show="activeTab === 'general'" class="settings-content" shadow="never">
          <template #header>
            <h3>通用设置</h3>
          </template>
          
          <el-form :model="generalSettings" label-width="120px">
            <el-form-item label="用户名">
              <el-input v-model="generalSettings.username" disabled />
            </el-form-item>
            
            <el-form-item label="邮箱">
              <el-input v-model="generalSettings.email" />
            </el-form-item>
            
            <el-form-item label="语言">
              <el-select v-model="generalSettings.language">
                <el-option label="简体中文" value="zh-CN" />
                <el-option label="English" value="en-US" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="时区">
              <el-select v-model="generalSettings.timezone">
                <el-option label="北京时间 (UTC+8)" value="Asia/Shanghai" />
                <el-option label="纽约时间 (UTC-5)" value="America/New_York" />
                <el-option label="伦敦时间 (UTC+0)" value="Europe/London" />
              </el-select>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="saveGeneralSettings">
                保存设置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 外观设置 -->
        <el-card v-show="activeTab === 'appearance'" class="settings-content" shadow="never">
          <template #header>
            <h3>外观设置</h3>
          </template>
          
          <el-form :model="appearanceSettings" label-width="120px">
            <el-form-item label="主题模式">
              <el-radio-group v-model="appearanceSettings.theme" @change="handleThemeChange">
                <el-radio label="light">浅色主题</el-radio>
                <el-radio label="dark">深色主题</el-radio>
                <el-radio label="auto">跟随系统</el-radio>
              </el-radio-group>
            </el-form-item>
            
            <el-form-item label="主色调">
              <div class="color-picker-group">
                <div
                  v-for="color in themeColors"
                  :key="color.value"
                  class="color-option"
                  :class="{ active: appearanceSettings.primaryColor === color.value }"
                  :style="{ backgroundColor: color.value }"
                  @click="appearanceSettings.primaryColor = color.value"
                >
                  <el-icon v-if="appearanceSettings.primaryColor === color.value">
                    <Check />
                  </el-icon>
                </div>
              </div>
            </el-form-item>
            
            <el-form-item label="字体大小">
              <el-slider
                v-model="appearanceSettings.fontSize"
                :min="12"
                :max="18"
                :step="1"
                show-stops
                show-input
              />
            </el-form-item>
            
            <el-form-item label="侧边栏宽度">
              <el-slider
                v-model="appearanceSettings.sidebarWidth"
                :min="200"
                :max="400"
                :step="20"
                show-input
              />
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="saveAppearanceSettings">
                保存设置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 分析偏好 -->
        <el-card v-show="activeTab === 'analysis'" class="settings-content" shadow="never">
          <template #header>
            <h3>分析偏好</h3>
          </template>
          
          <el-form :model="analysisSettings" label-width="120px">
            <el-form-item label="默认市场">
              <el-select v-model="analysisSettings.defaultMarket">
                <el-option label="A股" value="A股" />
                <el-option label="美股" value="美股" />
                <el-option label="港股" value="港股" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="默认分析深度">
              <el-select v-model="analysisSettings.defaultDepth">
                <el-option label="快速分析" value="快速" />
                <el-option label="标准分析" value="标准" />
                <el-option label="深度分析" value="深度" />
              </el-select>
            </el-form-item>
            
            <el-form-item label="默认分析师">
              <el-checkbox-group v-model="analysisSettings.defaultAnalysts">
                <el-checkbox label="基本面分析师">基本面分析师</el-checkbox>
                <el-checkbox label="技术分析师">技术分析师</el-checkbox>
                <el-checkbox label="情绪分析师">情绪分析师</el-checkbox>
                <el-checkbox label="量化分析师">量化分析师</el-checkbox>
              </el-checkbox-group>
            </el-form-item>


            
            <el-form-item label="自动刷新">
              <el-switch v-model="analysisSettings.autoRefresh" />
              <span class="setting-description">自动刷新分析结果</span>
            </el-form-item>
            
            <el-form-item label="刷新间隔">
              <el-input-number
                v-model="analysisSettings.refreshInterval"
                :min="10"
                :max="300"
                :step="10"
                :disabled="!analysisSettings.autoRefresh"
              />
              <span class="setting-description">秒</span>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="saveAnalysisSettings">
                保存设置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 通知设置 -->
        <el-card v-show="activeTab === 'notifications'" class="settings-content" shadow="never">
          <template #header>
            <h3>通知设置</h3>
          </template>
          
          <el-form :model="notificationSettings" label-width="120px">
            <el-form-item label="桌面通知">
              <el-switch v-model="notificationSettings.desktop" />
              <span class="setting-description">显示桌面通知</span>
            </el-form-item>
            
            <el-form-item label="邮件通知">
              <el-switch v-model="notificationSettings.email" />
              <span class="setting-description">发送邮件通知</span>
            </el-form-item>
            
            <el-form-item label="分析完成通知">
              <el-switch v-model="notificationSettings.analysisComplete" />
            </el-form-item>
            
            <el-form-item label="系统维护通知">
              <el-switch v-model="notificationSettings.systemMaintenance" />
            </el-form-item>
            
            <el-form-item label="新功能通知">
              <el-switch v-model="notificationSettings.newFeatures" />
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="saveNotificationSettings">
                保存设置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <!-- 安全设置 -->
        <el-card v-show="activeTab === 'security'" class="settings-content" shadow="never">
          <template #header>
            <h3>安全设置</h3>
          </template>
          
          <el-form label-width="120px">
            <el-form-item label="修改密码">
              <el-button @click="showChangePassword">修改密码</el-button>
            </el-form-item>
            
            <el-form-item label="两步验证">
              <el-switch v-model="securitySettings.twoFactor" />
              <span class="setting-description">启用两步验证</span>
            </el-form-item>
            
            <el-form-item label="登录通知">
              <el-switch v-model="securitySettings.loginNotification" />
              <span class="setting-description">新设备登录时通知</span>
            </el-form-item>
            
            <el-form-item label="会话管理">
              <el-button @click="showActiveSessions">查看活跃会话</el-button>
            </el-form-item>
            
            <el-form-item>
              <el-button type="primary" @click="saveSecuritySettings">
                保存设置
              </el-button>
            </el-form-item>
          </el-form>
        </el-card>



        <!-- 关于系统 -->
        <el-card v-show="activeTab === 'about'" class="settings-content" shadow="never">
          <template #header>
            <h3>关于系统</h3>
          </template>
          
          <div class="about-content">
            <div class="system-info">
              <h4>TradingAgents-CN</h4>
              <p>版本：v0.1.16</p>
              <p>构建时间：{{ buildTime }}</p>
              <p>API版本：{{ apiVersion }}</p>
            </div>
            
            <div class="system-status">
              <h4>系统状态</h4>
              <el-descriptions :column="2" border>
                <el-descriptions-item label="API服务">
                  <el-tag type="success">正常</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="数据库">
                  <el-tag type="success">正常</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="队列服务">
                  <el-tag type="success">正常</el-tag>
                </el-descriptions-item>
                <el-descriptions-item label="缓存服务">
                  <el-tag type="success">正常</el-tag>
                </el-descriptions-item>
              </el-descriptions>
            </div>
            
            <div class="links">
              <h4>相关链接</h4>
              <el-link href="#" type="primary">使用文档</el-link>
              <el-link href="#" type="primary">API文档</el-link>
              <el-link href="#" type="primary">问题反馈</el-link>
              <el-link href="#" type="primary">更新日志</el-link>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import {
  Setting,
  User,
  Brush,
  TrendCharts,
  Bell,
  Lock,
  InfoFilled,
  Check
} from '@element-plus/icons-vue'

const appStore = useAppStore()

// 响应式数据
const activeTab = ref('analysis')

const generalSettings = ref({
  username: 'demo_user',
  email: 'demo@example.com',
  language: 'zh-CN',
  timezone: 'Asia/Shanghai'
})

const appearanceSettings = ref({
  theme: 'auto',
  primaryColor: '#409EFF',
  fontSize: 14,
  sidebarWidth: 240
})

const analysisSettings = ref({
  defaultMarket: 'A股',
  defaultDepth: '标准',
  defaultAnalysts: ['基本面分析师', '技术分析师'],
  autoRefresh: true,
  refreshInterval: 30
})

const notificationSettings = ref({
  desktop: true,
  email: false,
  analysisComplete: true,
  systemMaintenance: true,
  newFeatures: true
})

const securitySettings = ref({
  twoFactor: false,
  loginNotification: true
})

const buildTime = ref(new Date().toLocaleString())
const apiVersion = ref('v0.1.16')

const themeColors = [
  { name: '默认蓝', value: '#409EFF' },
  { name: '成功绿', value: '#67C23A' },
  { name: '警告橙', value: '#E6A23C' },
  { name: '危险红', value: '#F56C6C' },
  { name: '信息灰', value: '#909399' },
  { name: '紫色', value: '#722ED1' },
  { name: '青色', value: '#13C2C2' },
  { name: '粉色', value: '#EB2F96' }
]

// 方法
const handleMenuSelect = (index: string) => {
  activeTab.value = index
}

const handleThemeChange = (theme: string) => {
  appStore.setTheme(theme as any)
}

const saveGeneralSettings = () => {
  ElMessage.success('通用设置已保存')
}

const saveAppearanceSettings = () => {
  appStore.setSidebarWidth(appearanceSettings.value.sidebarWidth)
  ElMessage.success('外观设置已保存')
}

const saveAnalysisSettings = () => {
  appStore.updatePreferences({
    defaultMarket: analysisSettings.value.defaultMarket as any,
    defaultDepth: analysisSettings.value.defaultDepth as any,
    autoRefresh: analysisSettings.value.autoRefresh,
    refreshInterval: analysisSettings.value.refreshInterval
  })
  ElMessage.success('分析偏好已保存')
}

const saveNotificationSettings = () => {
  ElMessage.success('通知设置已保存')
}

const saveSecuritySettings = () => {
  ElMessage.success('安全设置已保存')
}

const showChangePassword = () => {
  ElMessage.info('修改密码功能开发中...')
}

const showActiveSessions = () => {
  ElMessage.info('会话管理功能开发中...')
}



// 生命周期
onMounted(() => {
  // 从store加载设置
  appearanceSettings.value.theme = appStore.theme
  appearanceSettings.value.sidebarWidth = appStore.sidebarWidth
  
  analysisSettings.value.defaultMarket = appStore.preferences.defaultMarket
  analysisSettings.value.defaultDepth = appStore.preferences.defaultDepth
  analysisSettings.value.autoRefresh = appStore.preferences.autoRefresh
  analysisSettings.value.refreshInterval = appStore.preferences.refreshInterval
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
      color: var(--el-text-color-primary);
      margin: 0 0 8px 0;
    }

    .page-description {
      color: var(--el-text-color-regular);
      margin: 0;
    }
  }

  .settings-menu {
    .settings-nav {
      border: none;
    }
  }

  .settings-content {
    min-height: 500px;

    .setting-description {
      margin-left: 8px;
      font-size: 12px;
      color: var(--el-text-color-placeholder);
    }

    .color-picker-group {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;

      .color-option {
        width: 32px;
        height: 32px;
        border-radius: 6px;
        cursor: pointer;
        border: 2px solid transparent;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.3s ease;

        &:hover {
          transform: scale(1.1);
        }

        &.active {
          border-color: var(--el-color-primary);
          box-shadow: 0 0 0 2px var(--el-color-primary-light-8);
        }

        .el-icon {
          color: white;
          font-size: 16px;
        }
      }
    }

    .about-content {
      .system-info,
      .system-status,
      .links {
        margin-bottom: 32px;

        h4 {
          margin: 0 0 16px 0;
          color: var(--el-text-color-primary);
        }

        p {
          margin: 8px 0;
          color: var(--el-text-color-regular);
        }
      }

      .links {
        .el-link {
          margin-right: 16px;
          margin-bottom: 8px;
        }
      }
    }
  }
}
</style>
