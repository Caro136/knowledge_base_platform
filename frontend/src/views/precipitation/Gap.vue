<template>
  <PagePlaceholder
    title="知识缺口清单"
    task="T-34"
    description="缺口识别结果与转建任务尚未实现"
    :features="[
      '判定口径（决策 D2）：确实检索过 + 无任何有权上下文 + 非权限拒绝',
      '清单字段：未命中提问文本、提问部门、近期频次、时间戳（FR-51）',
      '按出现频次倒序排列，默认仅展示未解决项',
      '一键转建知识补充任务（FR-52）',
      '标记已解决（FR-53）',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
