<template>
  <div class="app-footer">
    <div class="footer-content">
      <div class="copyright">
        <span>© 2025 TradingAgents-CN v1.0.0-preview</span>
        <span class="rights">All rights reserved.</span>
      </div>
      <div class="disclaimer-text">
        TradingAgents-CN 是一个 AI 多 Agents 的股票分析学习平台。平台中的分析结论、观点和“投资建议”均由 AI 自动生成，仅用于学习、研究与交流，不构成任何形式的投资建议或承诺。用户据此进行的任何投资行为及其产生的风险与后果，均由用户自行承担。市场有风险，入市需谨慎。
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Footer组件逻辑
</script>

<style lang="scss" scoped>
.app-footer {
  .footer-content {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    gap: 6px;
    color: var(--el-text-color-regular);
    font-size: 14px;
    padding: 12px 16px;
    text-align: center;
  }

  .rights {
    margin-left: 4px;
  }

  .disclaimer-text {
    color: var(--el-text-color-secondary);
    font-size: 12px;
    line-height: 1.6;
    max-width: 1100px;
  }
}
</style>
