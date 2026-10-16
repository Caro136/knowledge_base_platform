<template>
  <el-container class="kb-layout">
    <el-aside :width="collapsed ? '64px' : '220px'" class="kb-aside">
      <div class="kb-brand">
        <el-icon class="kb-brand-icon"><Reading /></el-icon>
        <span v-show="!collapsed" class="kb-brand-text">{{ APP_TITLE }}</span>
      </div>

      <el-scrollbar class="kb-menu-scroll">
        <el-menu
          :default-active="activeMenu"
          :collapse="collapsed"
          :collapse-transition="false"
          router
          unique-opened
          background-color="#1f2d3d"
          text-color="#c0c4cc"
          active-text-color="#ffffff"
        >
          <SidebarItem v-for="menu in menus" :key="menu.id ?? menu.path ?? menu.name" :item="menu" />
        </el-menu>

        <el-empty v-if="!menus.length" description="暂无可访问的菜单" :image-size="60" />
      </el-scrollbar>
    </el-aside>

    <el-container>
      <el-header class="kb-header">
        <el-icon class="kb-collapse" @click="collapsed = !collapsed">
          <Fold v-if="!collapsed" />
          <Expand v-else />
        </el-icon>
        <span class="kb-header-title">{{ route.meta.title || '' }}</span>

        <div class="kb-spacer" />

        <el-dropdown @command="onCommand">
          <span class="kb-user">
            <el-avatar :size="26" class="kb-avatar">{{ avatarText }}</el-avatar>
            <span class="kb-user-name">{{ userStore.displayName || '未登录' }}</span>
            <el-icon><ArrowDown /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item disabled>
                {{ userStore.isSuper ? '超级管理员' : '普通用户' }}
              </el-dropdown-item>
              <el-dropdown-item divided command="logout">退出登录</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </el-header>

      <el-main class="kb-main">
        <router-view />
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { APP_TITLE } from '@/router'
import { useUserStore } from '@/store/user'

import SidebarItem from './SidebarItem.vue'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const collapsed = ref(false)

// 菜单树来自后端（/api/auth/me），按当前用户权限裁剪
const menus = computed(() => userStore.menus)

// 高亮当前路由对应的菜单项
const activeMenu = computed(() => route.path)

const avatarText = computed(() => {
  const name = userStore.displayName
  return name ? name.slice(0, 1).toUpperCase() : '?'
})

async function onCommand(command) {
  if (command === 'logout') {
    await userStore.logout()
    router.replace('/login')
  }
}
</script>

<style scoped>
.kb-layout {
  height: 100vh;
}

.kb-aside {
  display: flex;
  flex-direction: column;
  background-color: #1f2d3d;
  transition: width 0.2s;
  overflow: hidden;
}

.kb-brand {
  display: flex;
  align-items: center;
  gap: 8px;
  height: var(--kb-header-height);
  padding: 0 16px;
  color: #fff;
  font-weight: 600;
  white-space: nowrap;
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
}

.kb-brand-icon {
  font-size: 20px;
}

.kb-menu-scroll {
  flex: 1;
}

.kb-aside :deep(.el-menu) {
  border-right: none;
}

.kb-header {
  display: flex;
  align-items: center;
  gap: 12px;
  height: var(--kb-header-height);
  padding: 0 16px;
  background: #fff;
  border-bottom: 1px solid var(--kb-border);
}

.kb-collapse {
  font-size: 18px;
  cursor: pointer;
  color: #606266;
}

.kb-header-title {
  font-size: 15px;
  font-weight: 600;
}

.kb-spacer {
  flex: 1;
}

.kb-user {
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  outline: none;
}

.kb-user-name {
  font-size: 13px;
  color: #303133;
}

.kb-avatar {
  background: #409eff;
  font-size: 13px;
}

.kb-main {
  padding: 0;
  background: var(--kb-page-bg);
  overflow: auto;
}
</style>
