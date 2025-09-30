<template>
  <div class="app-footer">
    <div class="footer-content">
      <span>&copy; 2024 TradingAgents-CN v0.1.16</span>
      <div class="footer-links">
        <el-link type="primary" href="#" target="_blank">使用文档</el-link>
        <el-link type="primary" href="#" target="_blank">API文档</el-link>
        <el-link type="primary" href="#" target="_blank">问题反馈</el-link>
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
    justify-content: space-between;
    align-items: center;
    color: var(--el-text-color-regular);
    font-size: 14px;

    .footer-links {
      display: flex;
      gap: 16px;
    }
  }
}

@media (max-width: 768px) {
  .app-footer .footer-content {
    flex-direction: column;
    gap: 8px;
    text-align: center;
  }
}
</style>
