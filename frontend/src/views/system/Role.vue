<template>
  <PagePlaceholder
    title="角色管理"
    task="T-09"
    description="角色维护与权限分配树尚未实现"
    :features="[
      '角色列表：名称、编码、备注、启用状态（FR-15）',
      '新增 / 编辑 / 删除角色',
      '权限分配树：勾选目录 / 菜单 / 按钮级权限点（FR-16）',
      '按钮级权限：role:create / role:update / role:delete / role:perm',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
