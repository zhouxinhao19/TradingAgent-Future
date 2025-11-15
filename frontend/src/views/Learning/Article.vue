<template>
  <div class="learning-article">
    <el-page-header @back="goBack" :content="article.title">
      <template #extra>
        <el-button type="primary" :icon="Download" @click="downloadArticle">下载</el-button>
      </template>
    </el-page-header>

    <div class="article-container">
      <div class="article-meta">
        <el-tag :type="article.categoryType" size="small">{{ article.category }}</el-tag>
        <span class="read-time">
          <el-icon><Clock /></el-icon>
          {{ article.readTime }}
        </span>
        <span class="views">
          <el-icon><View /></el-icon>
          {{ article.views }}
        </span>
        <span class="update-time">更新于 {{ article.updateTime }}</span>
      </div>

      <div class="article-content" v-html="article.content"></div>

      <div class="article-footer">
        <el-divider />
        <div class="navigation">
          <el-button v-if="prevArticle" @click="navigateToArticle(prevArticle.id)">
            <el-icon><ArrowLeft /></el-icon>
            上一篇：{{ prevArticle.title }}
          </el-button>
          <el-button v-if="nextArticle" @click="navigateToArticle(nextArticle.id)">
            下一篇：{{ nextArticle.title }}
            <el-icon><ArrowRight /></el-icon>
          </el-button>
        </div>
      </div>
    </div>

    <!-- 侧边栏目录 -->
    <div class="article-toc">
      <div class="toc-title">目录</div>
      <ul class="toc-list">
        <li v-for="heading in tableOfContents" :key="heading.id" 
            :class="['toc-item', `toc-level-${heading.level}`]"
            @click="scrollToHeading(heading.id)">
          {{ heading.text }}
        </li>
      </ul>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Clock, View, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'

const route = useRoute()
const router = useRouter()

const articleId = computed(() => route.params.id as string)

// 文章数据（示例，后续从API或Markdown文件加载）
const article = ref({
  id: 'what-is-llm',
  title: '什么是大语言模型（LLM）？',
  category: 'AI基础知识',
  categoryType: 'primary',
  readTime: '8分钟',
  views: 2345,
  updateTime: '2025-11-14',
  content: `
    <h2 id="introduction">引言</h2>
    <p>大语言模型（Large Language Model，简称LLM）是近年来人工智能领域最重要的突破之一...</p>
    
    <h2 id="what-is-llm">什么是大语言模型？</h2>
    <p>大语言模型是一种基于深度学习的自然语言处理模型...</p>
    
    <h3 id="key-features">核心特点</h3>
    <ul>
      <li><strong>大规模参数</strong>：通常包含数十亿甚至数千亿个参数</li>
      <li><strong>预训练</strong>：在海量文本数据上进行预训练</li>
      <li><strong>通用性</strong>：可以处理多种自然语言任务</li>
    </ul>
    
    <h2 id="how-it-works">工作原理</h2>
    <p>大语言模型基于Transformer架构...</p>
    
    <h2 id="applications">应用场景</h2>
    <p>在股票分析领域，大语言模型可以...</p>
  `
})

// 目录
const tableOfContents = ref([
  { id: 'introduction', text: '引言', level: 2 },
  { id: 'what-is-llm', text: '什么是大语言模型？', level: 2 },
  { id: 'key-features', text: '核心特点', level: 3 },
  { id: 'how-it-works', text: '工作原理', level: 2 },
  { id: 'applications', text: '应用场景', level: 2 }
])

// 上一篇/下一篇
const prevArticle = ref({
  id: 'what-is-ai',
  title: '什么是人工智能（AI）？'
})

const nextArticle = ref({
  id: 'transformer-architecture',
  title: 'Transformer架构详解'
})

const goBack = () => {
  router.back()
}

const downloadArticle = () => {
  ElMessage.success('文章下载功能开发中...')
}

const navigateToArticle = (id: string) => {
  router.push(`/learning/article/${id}`)
}

const scrollToHeading = (id: string) => {
  const element = document.getElementById(id)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}
</script>

<style scoped lang="scss">
.learning-article {
  display: flex;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  gap: 24px;

  .el-page-header {
    margin-bottom: 24px;
  }

  .article-container {
    flex: 1;
    min-width: 0;
    background: white;
    border-radius: 8px;
    padding: 32px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);

    .article-meta {
      display: flex;
      align-items: center;
      gap: 16px;
      margin-bottom: 32px;
      padding-bottom: 16px;
      border-bottom: 1px solid #ebeef5;

      span {
        display: flex;
        align-items: center;
        font-size: 14px;
        color: #909399;

        .el-icon {
          margin-right: 4px;
        }
      }
    }

    .article-content {
      font-size: 16px;
      line-height: 1.8;
      color: #303133;

      :deep(h2) {
        font-size: 24px;
        margin: 32px 0 16px;
        padding-bottom: 8px;
        border-bottom: 2px solid #409eff;
        color: #303133;
      }

      :deep(h3) {
        font-size: 20px;
        margin: 24px 0 12px;
        color: #606266;
      }

      :deep(p) {
        margin: 16px 0;
        text-align: justify;
      }

      :deep(ul), :deep(ol) {
        margin: 16px 0;
        padding-left: 24px;

        li {
          margin: 8px 0;
        }
      }

      :deep(code) {
        background: #f5f7fa;
        padding: 2px 6px;
        border-radius: 4px;
        font-family: 'Consolas', 'Monaco', monospace;
        font-size: 14px;
      }

      :deep(pre) {
        background: #282c34;
        color: #abb2bf;
        padding: 16px;
        border-radius: 8px;
        overflow-x: auto;
        margin: 16px 0;

        code {
          background: none;
          padding: 0;
          color: inherit;
        }
      }

      :deep(blockquote) {
        border-left: 4px solid #409eff;
        padding-left: 16px;
        margin: 16px 0;
        color: #606266;
        background: #f5f7fa;
        padding: 12px 16px;
        border-radius: 4px;
      }
    }

    .article-footer {
      margin-top: 48px;

      .navigation {
        display: flex;
        justify-content: space-between;
        gap: 16px;

        .el-button {
          flex: 1;
          max-width: 400px;
        }
      }
    }
  }

  .article-toc {
    width: 240px;
    position: sticky;
    top: 80px;
    height: fit-content;
    background: white;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);

    .toc-title {
      font-size: 16px;
      font-weight: 600;
      margin-bottom: 16px;
      color: #303133;
    }

    .toc-list {
      list-style: none;
      padding: 0;
      margin: 0;

      .toc-item {
        padding: 8px 0;
        cursor: pointer;
        color: #606266;
        font-size: 14px;
        transition: all 0.3s;
        border-left: 2px solid transparent;
        padding-left: 12px;

        &:hover {
          color: #409eff;
          border-left-color: #409eff;
        }

        &.toc-level-3 {
          padding-left: 24px;
          font-size: 13px;
        }

        &.toc-level-4 {
          padding-left: 36px;
          font-size: 12px;
        }
      }
    }
  }
}

@media (max-width: 1200px) {
  .learning-article {
    .article-toc {
      display: none;
    }
  }
}

@media (max-width: 768px) {
  .learning-article {
    padding: 16px;

    .article-container {
      padding: 20px;

      .article-content {
        font-size: 15px;

        :deep(h2) {
          font-size: 20px;
        }

        :deep(h3) {
          font-size: 18px;
        }
      }

      .article-footer {
        .navigation {
          flex-direction: column;

          .el-button {
            max-width: 100%;
          }
        }
      }
    }
  }
}
</style>

