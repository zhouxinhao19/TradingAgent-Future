<template>
  <div class="learning-category">
    <el-page-header @back="goBack" :content="categoryInfo.title">
      <template #icon>
        <span class="category-icon">{{ categoryInfo.icon }}</span>
      </template>
    </el-page-header>

    <div class="category-content">
      <div class="category-description">
        <p>{{ categoryInfo.description }}</p>
      </div>

      <el-row :gutter="20">
        <el-col :xs="24" :sm="12" :md="8" v-for="article in articles" :key="article.id">
          <el-card class="article-card" shadow="hover" @click="openArticle(article.id)">
            <div class="article-header">
              <h3>{{ article.title }}</h3>
              <el-tag :type="article.difficulty" size="small">{{ article.difficultyText }}</el-tag>
            </div>
            <p class="article-desc">{{ article.description }}</p>
            <div class="article-footer">
              <span class="read-time">
                <el-icon><Clock /></el-icon>
                {{ article.readTime }}
              </span>
              <span class="views">
                <el-icon><View /></el-icon>
                {{ article.views }}
              </span>
            </div>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Clock, View } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()

const category = computed(() => route.params.category as string)

// 分类信息映射
const categoryMap: Record<string, any> = {
  'ai-basics': {
    title: 'AI基础知识',
    icon: '🤖',
    description: '从零开始了解人工智能和大语言模型的基本概念'
  },
  'prompt-engineering': {
    title: '提示词工程',
    icon: '✍️',
    description: '学习如何编写高质量的提示词，让AI更好地理解你的需求'
  },
  'model-selection': {
    title: '模型选择指南',
    icon: '🎯',
    description: '了解不同大模型的特点，选择最适合你的模型'
  },
  'analysis-principles': {
    title: 'AI分析股票原理',
    icon: '📊',
    description: '深入了解多智能体如何协作分析股票'
  },
  'risks-limitations': {
    title: '风险与局限性',
    icon: '⚠️',
    description: '了解AI的潜在问题和正确使用方式'
  },
  'resources': {
    title: '源项目与论文',
    icon: '📖',
    description: 'FinRobot项目介绍和学术论文资源'
  },
  'tutorials': {
    title: '实战教程',
    icon: '🎓',
    description: '通过实际案例学习如何使用本工具'
  },
  'faq': {
    title: '常见问题',
    icon: '❓',
    description: '快速找到常见问题的答案'
  }
}

const categoryInfo = computed(() => {
  return categoryMap[category.value] || {
    title: '未知分类',
    icon: '📚',
    description: ''
  }
})

// 文章列表（示例数据，后续从API获取）
const articles = ref([
  {
    id: 'what-is-ai',
    title: '什么是人工智能（AI）？',
    description: '了解人工智能的定义、发展历史和应用领域',
    readTime: '5分钟',
    views: 1234,
    difficulty: 'success',
    difficultyText: '入门'
  },
  {
    id: 'what-is-llm',
    title: '什么是大语言模型（LLM）？',
    description: '深入了解大语言模型的工作原理和技术架构',
    readTime: '8分钟',
    views: 2345,
    difficulty: 'warning',
    difficultyText: '进阶'
  },
  {
    id: 'transformer-architecture',
    title: 'Transformer架构详解',
    description: '学习大模型背后的核心技术：Transformer架构',
    readTime: '12分钟',
    views: 987,
    difficulty: 'danger',
    difficultyText: '高级'
  }
])

const goBack = () => {
  router.push('/learning')
}

const openArticle = (articleId: string) => {
  router.push(`/learning/article/${articleId}`)
}
</script>

<style scoped lang="scss">
.learning-category {
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;

  .el-page-header {
    margin-bottom: 32px;

    .category-icon {
      font-size: 24px;
      margin-right: 8px;
    }
  }

  .category-content {
    .category-description {
      margin-bottom: 32px;
      padding: 20px;
      background: #f5f7fa;
      border-radius: 8px;

      p {
        font-size: 16px;
        color: #606266;
        line-height: 1.6;
        margin: 0;
      }
    }

    .article-card {
      cursor: pointer;
      transition: all 0.3s ease;
      margin-bottom: 20px;
      height: 200px;

      &:hover {
        transform: translateY(-4px);
        box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
      }

      .article-header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 12px;

        h3 {
          font-size: 16px;
          color: #303133;
          font-weight: 600;
          flex: 1;
          margin-right: 12px;
        }
      }

      .article-desc {
        font-size: 14px;
        color: #606266;
        line-height: 1.6;
        margin-bottom: 16px;
        min-height: 60px;
      }

      .article-footer {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding-top: 12px;
        border-top: 1px solid #ebeef5;

        span {
          display: flex;
          align-items: center;
          font-size: 13px;
          color: #909399;

          .el-icon {
            margin-right: 4px;
          }
        }
      }
    }
  }
}
</style>

