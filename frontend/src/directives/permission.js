/**
 * 按钮级权限指令。
 *
 * 用法：
 *   <el-button v-permission="'knowledge:import'">导入文档</el-button>
 *   <el-button v-permission="['faq:audit', 'faq:delete']">操作</el-button>
 *
 * 语义：指令值支持单个权限点或数组（数组为「命中任一即可」）。
 * 无权时直接从 DOM 移除元素。
 *
 * 注意：这只是展示层的收敛，真正的权限控制必须在后端完成
 * （见 SPEC §8 安全条款：操作权限以后端 require_permission 为准）。
 */

import { useUserStore } from '@/store/user'

function removeElement(el) {
  el.parentNode?.removeChild(el)
}

export default {
  mounted(el, binding) {
    const { value } = binding
    if (!value) return

    const store = useUserStore()
    if (!store.hasAnyPerm(value)) {
      removeElement(el)
    }
  },
}
