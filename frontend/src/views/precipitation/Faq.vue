<template>
  <PagePlaceholder
    title="FAQ 挖掘与审核发布"
    task="T-34"
    description="候选 FAQ 列表、审核流转与缓存控制尚未实现"
    :features="[
      '状态筛选：全部 / 待审核 / 已发布 / 已驳回',
      '候选 FAQ 卡片：问题、聚合频次、关联知识、置信度得分（FR-45）',
      '审核弹窗：在线编辑标准答案 → 发布上线 / 驳回（FR-46）',
      '发布后写入快速应答缓存，同类提问毫秒级直出（FR-47）',
      '已发布 FAQ 管理：缓存生效开关、快速检索（FR-48）',
      'FAQ 数据权限配置（默认语义待 PRD Q8 确认）（FR-49）',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
