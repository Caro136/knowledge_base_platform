<template>
  <PagePlaceholder
    title="部门管理"
    task="T-09"
    description="部门树形结构维护尚未实现"
    :features="[
      '部门树：增删改查、拖拽或上下级调整（FR-13）',
      '部门是四维数据权限中「部门可见」的实体来源',
      '删除前需校验是否存在在职用户或知识数据权限引用',
      '按钮级权限：dept:create / dept:update / dept:delete',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
