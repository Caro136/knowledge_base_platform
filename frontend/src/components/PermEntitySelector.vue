<template>
  <div class="perm-selector">
    <el-form label-width="88px">
      <el-form-item label="全局可见">
        <el-switch v-model="local.isGlobal" @change="emitChange" />
        <span class="hint">开启后所有登录用户均可访问，忽略下方设置</span>
      </el-form-item>

      <template v-if="!local.isGlobal">
        <el-form-item label="部门">
          <el-tree-select
            v-model="local.deptIds"
            :data="deptOptions"
            node-key="id"
            multiple
            show-checkbox
            check-strictly
            clearable
            :render-after-expand="false"
            :props="{ label: 'name', children: 'children' }"
            placeholder="选择部门（可多选）"
            style="width: 100%"
            @change="emitChange"
          />
        </el-form-item>

        <el-form-item label="角色">
          <el-select
            v-model="local.roleIds"
            multiple
            clearable
            placeholder="选择角色（可多选）"
            style="width: 100%"
            @change="emitChange"
          >
            <el-option v-for="role in roles" :key="role.id" :label="role.name" :value="role.id" />
          </el-select>
        </el-form-item>

        <el-form-item label="个人">
          <el-select
            v-model="local.userIds"
            multiple
            filterable
            remote
            clearable
            :remote-method="searchUsers"
            :loading="userLoading"
            placeholder="搜索用户（可多选）"
            style="width: 100%"
            @change="emitChange"
          >
            <el-option
              v-for="user in userOptions"
              :key="user.id"
              :label="`${user.nickname || user.username}（${user.username}）`"
              :value="user.id"
            />
          </el-select>
        </el-form-item>
      </template>
    </el-form>

    <el-alert class="perm-tip" type="info" :closable="false" show-icon :title="tip" />
  </div>
</template>

<script setup>
/**
 * 权限实体选择器（T-18）。
 *
 * 四维数据权限的统一录入控件：全局开关 + 部门树多选 + 角色多选 + 人员多选。
 * 知识单元（FR-17）与 FAQ（FR-49）共用同一组件，保证两处交互与语义一致。
 *
 * 组件本身不做保存，仅通过 v-model 同步值，由调用方决定提交时机。
 */
import { onMounted, reactive, ref, watch } from 'vue'

import { deptTree, roleList, userList } from '@/api'

const props = defineProps({
  modelValue: { type: Object, required: true },
  tip: {
    type: String,
    default: '默认不授予任何权限；命中下方任一维度即可访问该知识。',
  },
})

const emit = defineEmits(['update:modelValue'])

const local = reactive({
  isGlobal: false,
  deptIds: [],
  roleIds: [],
  userIds: [],
})

const deptOptions = ref([])
const roles = ref([])
const userOptions = ref([])
const userLoading = ref(false)

watch(
  () => props.modelValue,
  (value) => {
    Object.assign(local, {
      isGlobal: Boolean(value?.isGlobal),
      deptIds: [...(value?.deptIds || [])],
      roleIds: [...(value?.roleIds || [])],
      userIds: [...(value?.userIds || [])],
    })
  },
  { immediate: true, deep: true },
)

function emitChange() {
  emit('update:modelValue', {
    isGlobal: local.isGlobal,
    deptIds: [...local.deptIds],
    roleIds: [...local.roleIds],
    userIds: [...local.userIds],
  })
}

async function loadOptions() {
  // 选项加载失败不应阻断权限编辑，静默降级为空列表
  try {
    deptOptions.value = await deptTree()
  } catch {
    deptOptions.value = []
  }
  try {
    roles.value = await roleList()
  } catch {
    roles.value = []
  }
  try {
    // 预取一批用户作为基础选项，保证「已选人员」能正确回显
    const page = await userList({ page: 1, size: 100 })
    userOptions.value = page?.items || []
  } catch {
    userOptions.value = []
  }
}

async function searchUsers(keyword) {
  if (!keyword) return
  userLoading.value = true
  try {
    const page = await userList({ keyword, page: 1, size: 20 })
    const merged = [...userOptions.value]
    for (const item of page?.items || []) {
      if (!merged.some((user) => user.id === item.id)) merged.push(item)
    }
    userOptions.value = merged
  } catch {
    /* 保持现有选项 */
  } finally {
    userLoading.value = false
  }
}

onMounted(loadOptions)
</script>

<style scoped>
.hint {
  margin-left: 10px;
  font-size: 12px;
  color: #909399;
}

.perm-tip {
  margin-top: 4px;
}
</style>
