<template>
  <div class="kb-page">
    <el-card shadow="never">
      <template #header>
        <div class="ph-header">
          <span class="ph-title">{{ title }}</span>
          <el-tag v-if="task" size="small" type="info" effect="plain">待实现 · {{ task }}</el-tag>
        </div>
      </template>

      <el-empty :description="description">
        <template #image>
          <el-icon class="ph-icon"><Tools /></el-icon>
        </template>
      </el-empty>

      <div v-if="features.length" class="ph-features">
        <div class="ph-sub">规划要点（依据 SPEC §3 模块划分）</div>
        <ul>
          <li v-for="(item, index) in features" :key="index">{{ item }}</li>
        </ul>
      </div>
    </el-card>
  </div>
</template>

<script setup>
/**
 * 页面占位组件。
 *
 * 骨架阶段（T-01~T-04）各业务页面均使用本组件占位，
 * 后续任务实现真实页面时直接替换对应 view 文件即可。
 */
defineProps({
  /** 页面标题 */
  title: { type: String, required: true },
  /** 说明文案 */
  description: { type: String, default: '该页面将在后续任务中实现' },
  /** 所属任务编号，如 'T-15' */
  task: { type: String, default: '' },
  /** 规划要点列表 */
  features: { type: Array, default: () => [] },
})
</script>

<style scoped>
.ph-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ph-title {
  font-size: 15px;
  font-weight: 600;
}

.ph-icon {
  font-size: 56px;
  color: #c0c4cc;
}

.ph-features {
  max-width: 720px;
  margin: 0 auto;
  padding: 16px 20px;
  background: #fafafa;
  border-radius: 6px;
}

.ph-sub {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
}

.ph-features ul {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.9;
  color: #909399;
}
</style>
