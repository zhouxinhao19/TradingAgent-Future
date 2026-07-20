<template>
  <div class="user-profile" :class="{ collapsed: appStore.sidebarCollapsed }">
    <el-dropdown trigger="click" @command="handleCommand">
      <div class="profile-info">
        <el-avatar :size="32" :src="userAvatar">
          <el-icon><User /></el-icon>
        </el-avatar>
        <div v-if="!appStore.sidebarCollapsed" class="user-info">
          <div class="username">{{ userDisplayName }}</div>
          <div class="user-role">{{ userRole }}</div>
        </div>
      </div>
      
      <template #dropdown>
        <el-dropdown-menu>
          <el-dropdown-item command="settings">
            <el-icon><Setting /></el-icon>
            设置
          </el-dropdown-item>
          <el-dropdown-item divided command="logout">
            <el-icon><SwitchButton /></el-icon>
            退出登录
          </el-dropdown-item>
        </el-dropdown-menu>
      </template>
    </el-dropdown>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import { User, Setting, SwitchButton } from '@element-plus/icons-vue'

const router = useRouter()
const appStore = useAppStore()
const authStore = useAuthStore()

// 用户头像：优先使用用户设置的头像，否则返回 undefined 使用 el-avatar 的默认图标
const userAvatar = computed(() => authStore.user?.avatar || undefined)
const userDisplayName = computed(() => authStore.user?.username || '未登录')
const userRole = computed(() => {
  if (!authStore.user) return '未登录'
  return '用户'
})

const handleCommand = async (command: string) => {
  switch (command) {
    case 'settings':
      router.push('/settings')
      break
    case 'logout':
      await authStore.logout()
      ElMessage.success('已退出登录')
      router.push('/login')
      break
  }
}
</script>

<style lang="scss" scoped>
.user-profile {
  padding: 8px 12px;

  &.collapsed {
    padding: 8px;
    text-align: center;
  }

  .profile-info {
    display: flex;
    align-items: center;
    gap: 10px;
    cursor: pointer;
    padding: 8px 10px;
    border-radius: 8px;
    transition: background-color var(--app-transition-fast);

    &:hover {
      background-color: var(--app-sidebar-item-hover-bg);
    }

    :deep(.el-avatar) {
      background-color: rgba(255, 255, 255, 0.12);
      color: $sidebar-accent;
    }

    .user-info {
      flex: 1;
      min-width: 0;

      .username {
        font-size: 13px;
        font-weight: 600;
        color: #c8d6e0;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }

      .user-role {
        font-size: 11px;
        color: $sidebar-text;
        margin-top: 1px;
      }
    }
  }
}
</style>
