<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-brand">
        <el-icon class="login-logo"><Reading /></el-icon>
        <h1 class="login-title">{{ APP_TITLE }}</h1>
        <p class="login-subtitle">企业知识 · 智能问答 · 权限可控</p>
      </div>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        size="large"
        label-position="top"
        @keyup.enter="onSubmit"
      >
        <el-form-item label="账号" prop="username">
          <el-input v-model.trim="form.username" placeholder="请输入账号" clearable>
            <template #prefix><el-icon><User /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            show-password
          >
            <template #prefix><el-icon><Lock /></el-icon></template>
          </el-input>
        </el-form-item>

        <el-button
          type="primary"
          class="login-btn"
          size="large"
          :loading="loading"
          @click="onSubmit"
        >
          登 录
        </el-button>
      </el-form>

      <p class="login-tip">
        账号由系统管理员分配；如需开通或重置密码，请联系管理员。
      </p>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { APP_TITLE } from '@/router'
import { useUserStore } from '@/store/user'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()

const formRef = ref(null)
const loading = ref(false)

const form = reactive({
  username: '',
  password: '',
})

const rules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  loading.value = true
  try {
    await userStore.login({ username: form.username, password: form.password })
    // 登录成功后优先回到拦截前的目标页
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/'
    await router.replace(redirect)
  } catch {
    // 错误提示已由 axios 拦截器统一处理，这里只需结束 loading
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, #1f2d3d 0%, #2b4a6f 100%);
}

.login-card {
  width: 400px;
  padding: 36px 36px 24px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.25);
}

.login-brand {
  text-align: center;
  margin-bottom: 24px;
}

.login-logo {
  font-size: 38px;
  color: #409eff;
}

.login-title {
  margin: 10px 0 4px;
  font-size: 20px;
  font-weight: 600;
}

.login-subtitle {
  margin: 0;
  font-size: 13px;
  color: #909399;
}

.login-btn {
  width: 100%;
  margin-top: 4px;
}

.login-tip {
  margin: 18px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: #a8abb2;
  text-align: center;
}
</style>
