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
import { computed } from 'vue'
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
    description: 'TradingAgents项目介绍和学术论文资源'
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

// 文章数据库
const articlesDatabase: Record<string, any[]> = {
  'ai-basics': [
    {
      id: 'what-is-llm',
      title: '什么是大语言模型（LLM）？',
      description: '深入了解大语言模型的定义、工作原理和在股票分析中的应用',
      readTime: '10分钟',
      views: 2345,
      difficulty: 'success',
      difficultyText: '入门'
    }
  ],
  'prompt-engineering': [
    {
      id: 'prompt-basics',
      title: '提示词基础',
      description: '学习提示词的基本概念、结构和编写技巧',
      readTime: '10分钟',
      views: 1876,
      difficulty: 'success',
      difficultyText: '入门'
    },
    {
      id: 'best-practices',
      title: '提示词工程最佳实践',
      description: '掌握提示词编写的核心原则和实用技巧',
      readTime: '12分钟',
      views: 1543,
      difficulty: 'warning',
      difficultyText: '进阶'
    }
  ],
  'model-selection': [
    {
      id: 'model-comparison',
      title: '大语言模型对比与选择',
      description: '对比主流大语言模型的特点，学会选择最适合的模型',
      readTime: '15分钟',
      views: 1987,
      difficulty: 'warning',
      difficultyText: '进阶'
    }
  ],
  'analysis-principles': [
    {
      id: 'multi-agent-system',
      title: '多智能体系统详解',
      description: '深入理解TradingAgents-CN的多智能体协作机制',
      readTime: '15分钟',
      views: 1654,
      difficulty: 'warning',
      difficultyText: '进阶'
    }
  ],
  'risks-limitations': [
    {
      id: 'risk-warnings',
      title: 'AI股票分析的风险与局限性',
      description: '了解AI的主要局限性、使用风险和正确的使用方式',
      readTime: '12分钟',
      views: 2134,
      difficulty: 'success',
      difficultyText: '入门'
    }
  ],
  'resources': [
    {
      id: 'finrobot-intro',
      title: 'TradingAgents项目介绍',
      description: '了解TradingAgents-CN的源项目TradingAgents的架构和特性',
      readTime: '15分钟',
      views: 1432,
      difficulty: 'warning',
      difficultyText: '进阶'
    },
    {
      id: 'paper-guide',
      title: 'TradingAgents论文解读',
      description: '深度解读TradingAgents学术论文的核心内容和创新点',
      readTime: '20分钟',
      views: 987,
      difficulty: 'danger',
      difficultyText: '高级'
    }
  ],
  'tutorials': [
    {
      id: 'getting-started',
      title: '快速入门教程',
      description: '从零开始学习如何使用TradingAgents-CN进行股票分析',
      readTime: '10分钟',
      views: 3456,
      difficulty: 'success',
      difficultyText: '入门'
    }
  ],
  'faq': [
    {
      id: 'general-questions',
      title: '常见问题解答',
      description: '快速找到关于功能、模型选择、使用技巧等常见问题的答案',
      readTime: '15分钟',
      views: 2876,
      difficulty: 'success',
      difficultyText: '入门'
    }
  ]
}

// 根据当前分类获取文章列表
const articles = computed(() => {
  return articlesDatabase[category.value] || []
})

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

