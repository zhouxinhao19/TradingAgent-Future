<template>
  <div class="sortable-datasource-list">
    <div class="list-header">
      <h4>{{ categoryDisplayName }}</h4>
      <div class="header-actions">
        <el-tag type="info" size="small">{{ dataSources.length }} 个数据源</el-tag>
        <el-button
          size="small"
          type="primary"
          icon="Sort"
          @click="$emit('manage-category', categoryId)"
        >
          管理分类
        </el-button>
      </div>
    </div>

    <div
      ref="sortableContainer"
      class="datasource-container"
      :class="{ 'drag-active': isDragging }"
    >
      <div
        v-for="(item, index) in dataSources"
        :key="item.name"
        class="datasource-item"
        :data-id="item.name"
      >
        <div class="drag-handle">
          <el-icon><Rank /></el-icon>
        </div>
        
        <div class="datasource-info">
          <div class="datasource-header">
            <span class="datasource-name">{{ item.display_name || item.name }}</span>
            <div class="datasource-tags">
              <el-tag
                :type="item.enabled ? 'success' : 'danger'"
                size="small"
              >
                {{ item.enabled ? '启用' : '禁用' }}
              </el-tag>
              <el-tag type="info" size="small">
                优先级: {{ item.priority }}
              </el-tag>
            </div>
          </div>
          
          <div class="datasource-details">
            <span class="datasource-type">{{ item.type }}</span>
            <span class="datasource-provider">{{ item.provider || '-' }}</span>
            <span class="datasource-desc">{{ item.description || '暂无描述' }}</span>
          </div>
        </div>

        <div class="datasource-actions">
          <el-input-number
            v-model="item.priority"
            :min="0"
            :max="100"
            size="small"
            controls-position="right"
            style="width: 100px"
            @change="updatePriority(item)"
          />
          <el-button
            size="small"
            @click="$emit('edit-datasource', item)"
          >
            编辑
          </el-button>
          <el-button
            size="small"
            @click="$emit('manage-grouping', item.name)"
          >
            分组
          </el-button>
          <el-button
            size="small"
            :type="item.enabled ? 'warning' : 'success'"
            @click="toggleDataSource(item)"
          >
            {{ item.enabled ? '禁用' : '启用' }}
          </el-button>
        </div>
      </div>

      <div v-if="dataSources.length === 0" class="empty-state">
        <el-empty description="该分类下暂无数据源" :image-size="60">
          <el-button
            type="primary"
            size="small"
            @click="$emit('add-datasource', categoryId)"
          >
            添加数据源
          </el-button>
        </el-empty>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { Rank } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import { configApi, type DataSourceConfig } from '@/api/config'

// Props
interface Props {
  categoryId: string
  categoryDisplayName: string
  dataSources: (DataSourceConfig & { priority: number; enabled: boolean })[]
}

const props = defineProps<Props>()

// Emits
const emit = defineEmits<{
  'update-order': [categoryId: string, orderedItems: Array<{name: string, priority: number}>]
  'edit-datasource': [dataSource: DataSourceConfig]
  'manage-grouping': [dataSourceName: string]
  'manage-category': [categoryId: string]
  'add-datasource': [categoryId: string]
}>()

// Refs
const sortableContainer = ref<HTMLElement>()
const isDragging = ref(false)
let sortableInstance: Sortable | null = null

// 初始化拖拽排序
const initSortable = () => {
  if (!sortableContainer.value) return

  sortableInstance = Sortable.create(sortableContainer.value, {
    handle: '.drag-handle',
    animation: 150,
    ghostClass: 'sortable-ghost',
    chosenClass: 'sortable-chosen',
    dragClass: 'sortable-drag',
    
    onStart: () => {
      isDragging.value = true
    },
    
    onEnd: (evt) => {
      isDragging.value = false
      
      if (evt.oldIndex !== evt.newIndex && evt.oldIndex !== undefined && evt.newIndex !== undefined) {
        // 重新计算优先级
        const orderedItems = props.dataSources.map((item, index) => ({
          name: item.name,
          priority: props.dataSources.length - index // 倒序，第一个优先级最高
        }))
        
        // 发送更新事件
        emit('update-order', props.categoryId, orderedItems)
      }
    }
  })
}

// 销毁拖拽排序
const destroySortable = () => {
  if (sortableInstance) {
    sortableInstance.destroy()
    sortableInstance = null
  }
}

// 更新优先级
const updatePriority = async (item: DataSourceConfig & { priority: number; enabled: boolean }) => {
  try {
    await configApi.updateDataSourceGrouping(
      item.name,
      props.categoryId,
      { priority: item.priority }
    )
    
    ElMessage.success('优先级更新成功')
  } catch (error) {
    console.error('更新优先级失败:', error)
    ElMessage.error('更新优先级失败')
  }
}

// 切换数据源状态
const toggleDataSource = async (item: DataSourceConfig & { priority: number; enabled: boolean }) => {
  try {
    const newEnabled = !item.enabled
    await configApi.updateDataSourceGrouping(
      item.name,
      props.categoryId,
      { enabled: newEnabled }
    )
    
    item.enabled = newEnabled
    ElMessage.success(`数据源已${newEnabled ? '启用' : '禁用'}`)
  } catch (error) {
    console.error('切换数据源状态失败:', error)
    ElMessage.error('切换数据源状态失败')
  }
}

// 生命周期
onMounted(async () => {
  await nextTick()
  initSortable()
})

onUnmounted(() => {
  destroySortable()
})
</script>

<style lang="scss" scoped>
.sortable-datasource-list {
  margin-bottom: 24px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overflow: hidden;

  .list-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 16px 20px;
    background: #f5f7fa;
    border-bottom: 1px solid #ebeef5;

    h4 {
      margin: 0;
      color: #303133;
      font-size: 16px;
    }

    .header-actions {
      display: flex;
      align-items: center;
      gap: 8px;
    }
  }

  .datasource-container {
    &.drag-active {
      background: #f0f9ff;
    }

    .datasource-item {
      display: flex;
      align-items: center;
      padding: 16px 20px;
      border-bottom: 1px solid #f0f0f0;
      transition: all 0.3s ease;

      &:last-child {
        border-bottom: none;
      }

      &:hover {
        background: #f8f9fa;
      }

      .drag-handle {
        cursor: move;
        color: #c0c4cc;
        margin-right: 12px;
        padding: 4px;

        &:hover {
          color: #409eff;
        }
      }

      .datasource-info {
        flex: 1;
        min-width: 0;

        .datasource-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 8px;

          .datasource-name {
            font-weight: 500;
            color: #303133;
            font-size: 14px;
          }

          .datasource-tags {
            display: flex;
            gap: 4px;
          }
        }

        .datasource-details {
          display: flex;
          gap: 16px;
          font-size: 12px;
          color: #909399;

          .datasource-type {
            font-weight: 500;
          }
        }
      }

      .datasource-actions {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-left: 16px;
      }
    }

    .empty-state {
      padding: 40px 20px;
      text-align: center;
    }
  }
}

// 拖拽样式
:global(.sortable-ghost) {
  opacity: 0.5;
  background: #e3f2fd;
}

:global(.sortable-chosen) {
  background: #f0f9ff;
}

:global(.sortable-drag) {
  background: #ffffff;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transform: rotate(2deg);
}
</style>
