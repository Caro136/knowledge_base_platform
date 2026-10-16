<template>
  <PagePlaceholder
    title="AI 智能问答工作台"
    task="T-26"
    description="对话交互、SSE 流式渲染与引用溯源尚未实现"
    :features="[
      '左侧：新建对话 + 历史会话侧边栏 + 常见问题快捷入口（FR-29/30）',
      '右侧：消息列表、输入框、生成中断与重新提问（FR-21/31）',
      'SSE 流式打字机输出、处理步骤可见、Markdown 渲染与代码高亮（FR-27）',
      '知识引用溯源卡片（悬浮展示来源标题与切片摘录）（FR-28）',
      '权限缺失安全提示气泡（文案待 PRD Q5 确认）（FR-25）',
      '回答中图片可点击预览（来源于图片类知识的语义化切片）',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
