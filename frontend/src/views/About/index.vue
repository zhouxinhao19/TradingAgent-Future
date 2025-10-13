<template>
  <div class="about">
    <div class="page-header">
      <h1 class="page-title">
        <el-icon><InfoFilled /></el-icon>
        关于 TradingAgents-CN
      </h1>
      <p class="page-description">
        了解TradingAgents-CN的功能特性和技术架构
      </p>
    </div>

    <!-- 产品介绍 -->
    <el-card class="intro-card" shadow="never">
      <template #header>
        <h3>产品介绍</h3>
      </template>
      
      <div class="intro-content">
        <div class="intro-text">
          <h4>TradingAgents-CN v1.0.0-preview</h4>
          <p>
            TradingAgents-CN是一个现代化的多智能体股票分析平台，基于先进的AI技术，
            为投资者提供专业、准确、及时的股票分析服务。
          </p>
          <p>
            平台采用多智能体协作模式，包含基本面分析师、技术分析师、情绪分析师和量化分析师，
            从不同角度对股票进行全方位分析，帮助用户做出更明智的投资决策。
          </p>
        </div>
        
        <div class="intro-image">
          <img src="/about-illustration.svg" alt="TradingAgents-CN" />
        </div>
      </div>
    </el-card>

    <!-- 核心功能 -->
    <el-card class="features-card" shadow="never">
      <template #header>
        <h3>核心功能</h3>
      </template>
      
      <el-row :gutter="24">
        <el-col :span="8">
          <div class="feature-item">
            <div class="feature-icon">
              <el-icon><TrendCharts /></el-icon>
            </div>
            <h4>多智能体分析</h4>
            <p>基本面、技术面、情绪面、量化分析四大智能体协作</p>
          </div>
        </el-col>
        
        <el-col :span="8">
          <div class="feature-item">
            <div class="feature-icon">
              <el-icon><Search /></el-icon>
            </div>
            <h4>智能股票筛选</h4>
            <p>多维度筛选条件，快速发现投资机会</p>
          </div>
        </el-col>
        
        <el-col :span="8">
          <div class="feature-item">
            <div class="feature-icon">
              <el-icon><Files /></el-icon>
            </div>
            <h4>批量分析处理</h4>
            <p>支持批量股票分析，提高分析效率</p>
          </div>
        </el-col>
      </el-row>
      
      <el-row :gutter="24" style="margin-top: 24px;">
        <el-col :span="8">
          <div class="feature-item">
            <div class="feature-icon">
              <el-icon><Document /></el-icon>
            </div>
            <h4>专业分析报告</h4>
            <p>生成详细的分析报告，支持多种格式导出</p>
          </div>
        </el-col>
        
        <el-col :span="8">
          <div class="feature-item">
            <div class="feature-icon">
              <el-icon><Monitor /></el-icon>
            </div>
            <h4>实时监控</h4>
            <p>实时监控分析进度和系统状态</p>
          </div>
        </el-col>
        
        <el-col :span="8">
          <div class="feature-item">
            <div class="feature-icon">
              <el-icon><Setting /></el-icon>
            </div>
            <h4>个性化配置</h4>
            <p>灵活的参数配置和个人偏好设置</p>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 技术架构 -->
    <el-card class="tech-card" shadow="never">
      <template #header>
        <h3>技术架构</h3>
      </template>
      
      <div class="tech-stack">
        <div class="tech-category">
          <h4>前端技术</h4>
          <ul>
            <li>Vue 3 + TypeScript</li>
            <li>Element Plus UI</li>
            <li>Pinia 状态管理</li>
            <li>Vite 构建工具</li>
          </ul>
        </div>
        
        <div class="tech-category">
          <h4>后端技术</h4>
          <ul>
            <li>FastAPI + Python</li>
            <li>Redis 队列系统</li>
            <li>MongoDB 数据存储</li>
            <li>异步任务处理</li>
          </ul>
        </div>
        
        <div class="tech-category">
          <h4>AI技术</h4>
          <ul>
            <li>多智能体协作</li>
            <li>大语言模型集成</li>
          </ul>
        </div>
      </div>
    </el-card>

    <!-- 版本信息 -->
    <el-card class="version-card" shadow="never">
      <template #header>
        <h3>版本信息</h3>
      </template>
      
      <el-descriptions :column="2" border>
        <el-descriptions-item label="当前版本">v1.0.0-preview</el-descriptions-item>
        <el-descriptions-item label="发布日期">2024-01-15</el-descriptions-item>
        <el-descriptions-item label="构建时间">{{ buildTime }}</el-descriptions-item>
        <el-descriptions-item label="API版本">v1.0.0-preview</el-descriptions-item>
        <el-descriptions-item label="前端框架">Vue 3.4.0</el-descriptions-item>
        <el-descriptions-item label="UI组件">Element Plus 2.4.4</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 联系我们 -->
    <el-card class="contact-card" shadow="never">
      <template #header>
        <h3>联系我们</h3>
      </template>
      
      <div class="contact-info">
        <div class="contact-item">
          <el-icon><Message /></el-icon>
          <span>邮箱：support@tradingagents.cn</span>
        </div>
        
        <div class="contact-item">
          <el-icon><Link /></el-icon>
          <span>官网：https://tradingagents.cn</span>
        </div>
        
        <div class="contact-item">
          <el-icon><ChatDotRound /></el-icon>
          <span>微信群：扫描二维码加入用户群</span>
        </div>
        
        <div class="contact-item">
          <el-icon><Document /></el-icon>
          <span>文档：https://docs.tradingagents.cn</span>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import {
  InfoFilled,
  TrendCharts,
  Search,
  Files,
  Document,
  Monitor,
  Setting,
  Message,
  Link,
  ChatDotRound
} from '@element-plus/icons-vue'

const buildTime = ref(new Date().toLocaleString('zh-CN'))
</script>

<style lang="scss" scoped>
.about {
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

  .intro-card {
    margin-bottom: 24px;

    .intro-content {
      display: flex;
      align-items: center;
      gap: 32px;

      .intro-text {
        flex: 1;

        h4 {
          color: var(--el-color-primary);
          margin: 0 0 16px 0;
        }

        p {
          line-height: 1.6;
          color: var(--el-text-color-regular);
          margin-bottom: 16px;
        }
      }

      .intro-image {
        width: 300px;
        text-align: center;

        img {
          width: 100%;
          height: auto;
        }
      }
    }
  }

  .features-card {
    margin-bottom: 24px;

    .feature-item {
      text-align: center;
      padding: 24px 16px;

      .feature-icon {
        width: 64px;
        height: 64px;
        margin: 0 auto 16px;
        background: var(--el-color-primary-light-8);
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        color: var(--el-color-primary);
        font-size: 32px;
      }

      h4 {
        margin: 0 0 8px 0;
        color: var(--el-text-color-primary);
      }

      p {
        margin: 0;
        color: var(--el-text-color-regular);
        line-height: 1.5;
      }
    }
  }

  .tech-card {
    margin-bottom: 24px;

    .tech-stack {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
      gap: 32px;

      .tech-category {
        h4 {
          color: var(--el-color-primary);
          margin: 0 0 16px 0;
          padding-bottom: 8px;
          border-bottom: 2px solid var(--el-color-primary-light-8);
        }

        ul {
          list-style: none;
          padding: 0;
          margin: 0;

          li {
            padding: 8px 0;
            color: var(--el-text-color-regular);
            position: relative;
            padding-left: 20px;

            &::before {
              content: '•';
              color: var(--el-color-primary);
              position: absolute;
              left: 0;
            }
          }
        }
      }
    }
  }

  .version-card {
    margin-bottom: 24px;
  }

  .contact-card {
    .contact-info {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 16px;

      .contact-item {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 16px;
        background: var(--el-fill-color-lighter);
        border-radius: 8px;

        .el-icon {
          color: var(--el-color-primary);
          font-size: 20px;
        }

        span {
          color: var(--el-text-color-regular);
        }
      }
    }
  }
}

// 响应式设计
@media (max-width: 768px) {
  .about {
    .intro-card .intro-content {
      flex-direction: column;
      text-align: center;

      .intro-image {
        width: 200px;
      }
    }

    .tech-card .tech-stack {
      grid-template-columns: 1fr;
    }

    .contact-card .contact-info {
      grid-template-columns: 1fr;
    }
  }
}
</style>
