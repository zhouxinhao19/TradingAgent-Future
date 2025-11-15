<template>
  <div class="learning-article-wrapper">
    <!-- 页面头部 -->
    <el-page-header @back="goBack" :content="article.title">
      <template #extra>
        <el-button type="primary" :icon="Download" @click="downloadArticle">下载</el-button>
      </template>
    </el-page-header>

    <!-- 主容器：文章 + 侧边栏 -->
    <div class="learning-article">
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Download, Clock, View, ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'

const route = useRoute()
const router = useRouter()

const articleId = computed(() => route.params.id as string)

// 文章注册表：通过 Vite 的 ?raw 直接打包 Markdown
const registry: Record<string, { title: string; loader: () => Promise<any>; category: string; categoryType: any; readTime: string }> = {
  'what-is-llm': { title: '什么是大语言模型（LLM）？', loader: () => import('../../../../docs/learning/01-ai-basics/what-is-llm.md?raw'), category: 'AI基础知识', categoryType: 'primary', readTime: '10分钟' },
  'prompt-basics': { title: '提示词基础', loader: () => import('../../../../docs/learning/02-prompt-engineering/prompt-basics.md?raw'), category: '提示词工程', categoryType: 'success', readTime: '10分钟' },
  'best-practices': { title: '提示词工程最佳实践', loader: () => import('../../../../docs/learning/02-prompt-engineering/best-practices.md?raw'), category: '提示词工程', categoryType: 'success', readTime: '12分钟' },
  'model-comparison': { title: '大语言模型对比与选择', loader: () => import('../../../../docs/learning/03-model-selection/model-comparison.md?raw'), category: '模型选择指南', categoryType: 'warning', readTime: '15分钟' },
  'multi-agent-system': { title: '多智能体系统详解', loader: () => import('../../../../docs/learning/04-analysis-principles/multi-agent-system.md?raw'), category: 'AI分析原理', categoryType: 'info', readTime: '15分钟' },
  'risk-warnings': { title: 'AI股票分析的风险与局限性', loader: () => import('../../../../docs/learning/05-risks-limitations/risk-warnings.md?raw'), category: '风险与局限性', categoryType: 'danger', readTime: '12分钟' },
  'tradingagents-intro': { title: 'TradingAgents项目介绍', loader: () => import('../../../../docs/learning/06-resources/tradingagents-intro.md?raw'), category: '源项目与论文', categoryType: 'primary', readTime: '15分钟' },
  'paper-guide': { title: 'TradingAgents论文解读', loader: () => import('../../../../docs/learning/06-resources/paper-guide.md?raw'), category: '源项目与论文', categoryType: 'primary', readTime: '20分钟' },
  'getting-started': { title: '快速入门教程', loader: () => import('../../../../docs/learning/07-tutorials/getting-started.md?raw'), category: '实战教程', categoryType: 'success', readTime: '10分钟' },
  'general-questions': { title: '常见问题解答', loader: () => import('../../../../docs/learning/08-faq/general-questions.md?raw'), category: '常见问题', categoryType: 'info', readTime: '15分钟' }
}

// 文章顺序用于上一页/下一页
const articleOrder = [
  'what-is-llm',
  'prompt-basics',
  'best-practices',
  'model-comparison',
  'multi-agent-system',
  'risk-warnings',
  'tradingagents-intro',
  'paper-guide',
  'getting-started',
  'general-questions'
]

// 当前文章数据
const article = ref({
  id: '',
  title: '',
  category: '',
  categoryType: 'primary' as any,
  readTime: '',
  views: 0,
  updateTime: '',
  content: ''
})

// 目录
const tableOfContents = ref<{ id: string; text: string; level: number }[]>([])

const prevArticle = ref<{ id: string; title: string } | null>(null)
const nextArticle = ref<{ id: string; title: string } | null>(null)

const goBack = () => {
  router.back()
}

const downloadArticle = async () => {
  if (!article.value.id) return
  const info = registry[article.value.id]
  if (!info) {
    ElMessage.warning('未找到文章资源')
    return
  }
  try {
    const mod = await info.loader()
    const md: string = typeof mod === 'string' ? mod : (mod.default || '')
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${article.value.id}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  } catch (e) {
    console.error(e)
    ElMessage.error('下载失败')
  }
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

// 将 markdown 中的本地链接转换为应用内路由链接
function convertLocalLinks(html: string): string {
  const div = document.createElement('div')
  div.innerHTML = html

  // 处理所有链接
  const links = div.querySelectorAll('a')
  for (const link of links) {
    const href = link.getAttribute('href')
    if (href && href.endsWith('.md')) {
      // 提取文件名（不含扩展名）
      const fileName = href.split('/').pop()?.replace('.md', '')
      if (fileName && registry[fileName]) {
        // 转换为应用内路由链接
        link.setAttribute('href', `/learning/article/${fileName}`)
        link.setAttribute('data-internal', 'true')
      }
    }
  }

  return div.innerHTML
}

// 从 markdown 加载文章
async function loadArticle(id: string) {
  const info = registry[id]
  if (!info) {
    ElMessage.error('未找到文章')
    return
  }
  article.value = {
    id,
    title: info.title,
    category: info.category,
    categoryType: info.categoryType,
    readTime: info.readTime,
    views: 0,
    updateTime: new Date().toISOString().slice(0, 10),
    content: ''
  }

  try {
    const mod = await info.loader()
    const md: string = typeof mod === 'string' ? mod : (mod.default || '')
    // 解析 markdown -> html，并开启 heading id
    marked.setOptions({ headerIds: true, mangle: false })
    let html = marked.parse(md) as string
    // 转换本地链接
    html = convertLocalLinks(html)
    article.value.content = html
    buildTOCFromHTML(html)
    buildPrevNext(id)
    // 在 DOM 更新后设置内部链接处理
    setupInternalLinks()
  } catch (e) {
    console.error(e)
    ElMessage.error('加载文章失败：无法访问文档资源')
  }
}

function buildTOCFromHTML(html: string) {
  const div = document.createElement('div')
  div.innerHTML = html
  const headings = Array.from(div.querySelectorAll('h2, h3, h4')) as HTMLHeadingElement[]
  tableOfContents.value = headings.map(h => ({
    id: h.id || h.textContent?.trim().toLowerCase().replace(/\s+/g, '-') || '',
    text: h.textContent || '',
    level: Number(h.tagName.substring(1))
  }))
}

// 在 DOM 更新后处理内部链接
function setupInternalLinks() {
  nextTick(() => {
    const container = document.querySelector('.article-content')
    if (!container) return

    const links = container.querySelectorAll('a[data-internal="true"]')
    for (const link of links) {
      link.addEventListener('click', (e) => {
        e.preventDefault()
        const href = link.getAttribute('href')
        if (href) {
          router.push(href)
        }
      })
    }
  })
}

function buildPrevNext(id: string) {
  const idx = articleOrder.indexOf(id)
  prevArticle.value = idx > 0 ? { id: articleOrder[idx - 1], title: registry[articleOrder[idx - 1]].title } : null
  nextArticle.value = idx >= 0 && idx < articleOrder.length - 1 ? { id: articleOrder[idx + 1], title: registry[articleOrder[idx + 1]].title } : null
}

onMounted(() => {
  loadArticle(articleId.value)
})

watch(articleId, (id) => {
  loadArticle(id)
})
</script>

<style scoped lang="scss">
.learning-article-wrapper {
  display: flex;
  flex-direction: column;
  min-height: 100vh;

  .el-page-header {
    padding: 16px 24px;
    background: white;
    border-bottom: 1px solid #ebeef5;
    flex-shrink: 0;
  }
}

.learning-article {
  display: flex;
  padding: 24px;
  max-width: 1400px;
  margin: 0 auto;
  gap: 24px;
  flex: 1;
  width: 100%;

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
        margin: 16px 0;
        padding: 12px 16px;
        color: #606266;
        background: #f5f7fa;
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

