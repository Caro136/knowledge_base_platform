<template>
  <!-- 有可显示子项 → 渲染为可展开的子菜单 -->
  <el-sub-menu v-if="children.length" :index="indexOf">
    <template #title>
      <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
      <span>{{ item.name }}</span>
    </template>
    <sidebar-item v-for="child in children" :key="child.id ?? child.path ?? child.name" :item="child" />
  </el-sub-menu>

  <!-- 叶子节点 → 渲染为菜单项，index 即路由路径（配合 el-menu 的 router 模式） -->
  <el-menu-item v-else :index="item.path">
    <el-icon v-if="item.icon"><component :is="item.icon" /></el-icon>
    <template #title>{{ item.name }}</template>
  </el-menu-item>
</template>

<script setup>
import { computed } from 'vue'

defineOptions({ name: 'SidebarItem' })

const props = defineProps({
  /** 后端返回的菜单节点：{ id, name, type, path, icon, children } */
  item: { type: Object, required: true },
})

// 菜单类型：0=目录 1=菜单 2=按钮。按钮不进入导航
const MENU_TYPE_BUTTON = 2

const children = computed(() =>
  (props.item.children || []).filter((child) => child.type !== MENU_TYPE_BUTTON),
)

// 目录节点本身无路由，用其路径或名称作为 el-sub-menu 的唯一 index
const indexOf = computed(() => props.item.path || `dir-${props.item.id ?? props.item.name}`)
</script>
