<template>
  <PagePlaceholder
    title="知识维护与导入中心"
    task="T-15"
    description="知识单元台账、拖拽导入与四维权限分配尚未实现"
    :features="[
      '台账列表：编号、标题、格式、所属分类、权限标签、更新时间、启用状态（FR-01）',
      '筛选：关键词、格式、分类、状态；分页',
      '导入抽屉：拖拽批量上传 + 逐文件阶段进度（解析 → 切片 → 向量化 → 入库）（FR-02/03/07）',
      '支持格式：PDF / Word / Markdown / TXT / PPT / Excel / 图片（决策 D1）',
      '编辑 / 删除（级联清理向量与权限，FR-09）',
      '数据权限弹窗：复用「权限实体选择器」组件（全局开关 + 部门树 + 角色 + 个人）（FR-17）',
    ]"
  />
</template>

<script setup>
import PagePlaceholder from '@/components/PagePlaceholder.vue'
</script>
