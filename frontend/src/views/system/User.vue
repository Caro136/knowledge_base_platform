<template>
  <PagePlaceholder
    title="用户管理"
    task="T-09"
    description="用户账号的增删改查尚未实现"
    :features="[
      '列表：账号、昵称、所属部门、角色、状态；支持关键词与部门筛选（FR-14）',
      '新增 / 编辑：账号、昵称、归属部门、角色分配、启用状态',
      '删除（需校验是否仍被知识权限引用）',
      '按钮级权限：user:create / user:update / user:delete',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
