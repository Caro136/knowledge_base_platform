<template>
  <div class="kb-page">
    <el-row :gutter="16">
      <!-- 左：部门树 -->
      <el-col :span="10">
        <el-card shadow="never">
          <template #header>
            <div class="card-head">
              <span class="card-title">部门结构</span>
              <el-button
                v-permission="'dept:create'"
                type="primary"
                size="small"
                @click="openCreate(0)"
              >
                <el-icon><Plus /></el-icon>新增根部门
              </el-button>
            </div>
          </template>

          <div v-loading="loading">
            <el-tree
              v-if="tree.length"
              :data="tree"
              node-key="id"
              default-expand-all
              highlight-current
              :expand-on-click-node="false"
              :props="{ label: 'name', children: 'children' }"
              @node-click="onSelect"
            >
              <template #default="{ data }">
                <div class="tree-node">
                  <span class="tree-label">
                    {{ data.name }}
                    <el-tag v-if="!data.enabled" size="small" type="info" effect="plain">停用</el-tag>
                  </span>
                  <span class="tree-actions">
                    <el-button v-permission="'dept:create'" link size="small" @click.stop="openCreate(data.id)">
                      新增
                    </el-button>
                    <el-button v-permission="'dept:update'" link size="small" type="primary" @click.stop="openEdit(data)">
                      编辑
                    </el-button>
                    <el-button v-permission="'dept:delete'" link size="small" type="danger" @click.stop="onDelete(data)">
                      删除
                    </el-button>
                  </span>
                </div>
              </template>
            </el-tree>
            <el-empty v-else-if="!loading" description="暂无部门" :image-size="70" />
          </div>
        </el-card>
      </el-col>

      <!-- 右：部门详情 -->
      <el-col :span="14">
        <el-card shadow="never">
          <template #header><span class="card-title">部门详情</span></template>
          <el-descriptions v-if="current" :column="1" border>
            <el-descriptions-item label="部门名称">{{ current.name }}</el-descriptions-item>
            <el-descriptions-item label="上级部门">{{ parentName(current.parentId) }}</el-descriptions-item>
            <el-descriptions-item label="排序号">{{ current.orderNo }}</el-descriptions-item>
            <el-descriptions-item label="状态">
              <el-tag :type="current.enabled ? 'success' : 'info'" size="small">
                {{ current.enabled ? '启用' : '停用' }}
              </el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="直属子部门">
              {{ (current.children || []).length }} 个
            </el-descriptions-item>
          </el-descriptions>
          <el-empty v-else description="点击左侧部门查看详情" :image-size="80" />
          <el-alert
            class="tip"
            type="info"
            :closable="false"
            show-icon
            title="部门是四维数据权限中「部门可见」的实体来源；删除前需先清空其下的子部门与用户。"
          />
        </el-card>
      </el-col>
    </el-row>

    <!-- 新增 / 编辑 -->
    <el-dialog v-model="dialog" :title="form.id ? '编辑部门' : '新增部门'" width="480px">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="上级部门">
          <el-tree-select
            v-model="form.parentId"
            :data="parentOptions"
            node-key="id"
            :props="{ label: 'name', children: 'children' }"
            :render-after-expand="false"
            check-strictly
            clearable
            placeholder="不选择表示根部门"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="部门名称" prop="name">
          <el-input v-model.trim="form.name" maxlength="64" show-word-limit />
        </el-form-item>
        <el-form-item label="排序号">
          <el-input-number v-model="form.orderNo" :min="0" :max="9999" />
        </el-form-item>
        <el-form-item label="状态">
          <el-switch v-model="form.enabled" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import { deptCreate, deptDelete, deptTree, deptUpdate } from '@/api'

const tree = ref([])
const current = ref(null)
const loading = ref(false)

const dialog = ref(false)
const saving = ref(false)
const formRef = ref(null)

const form = reactive({
  id: null,
  name: '',
  parentId: 0,
  orderNo: 0,
  enabled: true,
})

const rules = {
  name: [{ required: true, message: '请输入部门名称', trigger: 'blur' }],
}

/** 编辑时把自己及其子树从「上级部门」候选中剔除，避免形成环 */
const parentOptions = computed(() => excludeSubtree(tree.value, form.id))

function excludeSubtree(nodes, excludeId) {
  if (!excludeId) return nodes
  return nodes
    .filter((node) => node.id !== excludeId)
    .map((node) => ({ ...node, children: excludeSubtree(node.children || [], excludeId) }))
}

function findNode(nodes, id) {
  for (const node of nodes) {
    if (node.id === id) return node
    const hit = findNode(node.children || [], id)
    if (hit) return hit
  }
  return null
}

function parentName(parentId) {
  if (!parentId) return '（根部门）'
  return findNode(tree.value, parentId)?.name || `未知(${parentId})`
}

async function load() {
  loading.value = true
  try {
    tree.value = await deptTree()
    // 刷新后保持详情区与最新数据同步（节点可能已被重命名或删除）
    if (current.value) {
      current.value = findNode(tree.value, current.value.id)
    }
  } finally {
    loading.value = false
  }
}

function onSelect(data) {
  current.value = data
}

function openCreate(parentId) {
  Object.assign(form, { id: null, name: '', parentId: parentId || 0, orderNo: 0, enabled: true })
  dialog.value = true
}

function openEdit(node) {
  Object.assign(form, {
    id: node.id,
    name: node.name,
    parentId: node.parentId,
    orderNo: node.orderNo,
    enabled: node.enabled,
  })
  dialog.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  const payload = {
    name: form.name,
    parentId: form.parentId || 0,
    orderNo: form.orderNo,
    enabled: form.enabled,
  }

  saving.value = true
  try {
    if (form.id) {
      await deptUpdate(form.id, payload)
      ElMessage.success('部门已更新')
    } else {
      await deptCreate(payload)
      ElMessage.success('部门已创建')
    }
    dialog.value = false
    await load()
  } catch {
    // 错误提示由 axios 拦截器统一处理（例如上级部门不能是自身下级）
  } finally {
    saving.value = false
  }
}

async function onDelete(node) {
  try {
    await ElMessageBox.confirm(
      `确认删除部门「${node.name}」？若其下存在子部门或用户，删除将被拒绝。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }

  try {
    await deptDelete(node.id)
    ElMessage.success('部门已删除')
    if (current.value?.id === node.id) {
      current.value = null
    }
    await load()
  } catch {
    // 错误提示由拦截器处理（例如仍有子部门或用户）
  }
}

onMounted(load)
</script>

<style scoped>
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
}

.tree-node {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}

.tree-label {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tree-actions {
  display: none;
}

.tree-node:hover .tree-actions {
  display: inline-flex;
}

.tip {
  margin-top: 12px;
}
</style>
