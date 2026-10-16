<template>
  <PagePlaceholder
    title="运营看板与数据大盘"
    task="T-28 / T-29"
    description="看板数据聚合接口与图表页面尚未实现"
    :features="[
      '指标卡：访问次数（PV）、访问人数（UV）、知识单元数、Token 消耗、平均响应时长、FAQ 缓存命中率',
      '访问趋势图（PV/UV 近 14 天折线，ECharts）',
      '热门知识单元 TOP10（环形/条形图）',
      '常见高频问题 TOP10（表格：排名 | 问题 | 提问次数）',
      'Token 消耗趋势图与响应时长分布图',
      '数据源统一来自 kb_access_log，聚合口径见 SPEC §8 可观测性',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
