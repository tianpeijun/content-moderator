<template>
  <div>
    <!-- Tabs for text / image labels -->
    <a-tabs v-model:activeKey="activeTab" @change="onTabChange">
      <a-tab-pane key="text" tab="文案标签" />
      <a-tab-pane key="image" tab="图片标签" />
    </a-tabs>

    <!-- Action bar -->
    <a-row style="margin-bottom: 16px" justify="end">
      <a-button type="primary" @click="openCreateModal">新建标签</a-button>
    </a-row>

    <!-- Labels table -->
    <a-table
      :columns="columns"
      :dataSource="labels"
      :loading="loading"
      rowKey="id"
      :pagination="{ pageSize: 20, showTotal: (total: number) => `共 ${total} 条` }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'action'">
          <a-tag :color="actionColor(record.action)">{{ actionLabel(record.action) }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'enabled'">
          <a-switch
            :checked="record.enabled"
            @change="(checked: boolean) => toggleEnabled(record, checked)"
            :loading="record._toggling"
          />
        </template>
        <template v-else-if="column.dataIndex === 'operations'">
          <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
          <a-popconfirm
            title="确定删除该标签？"
            okText="确定"
            cancelText="取消"
            @confirm="deleteLabel(record.id)"
          >
            <a-button type="link" size="small" danger>删除</a-button>
          </a-popconfirm>
        </template>
      </template>
    </a-table>

    <!-- Create / Edit modal -->
    <a-modal
      v-model:open="modalVisible"
      :title="isEdit ? '编辑标签' : '新建标签'"
      :confirmLoading="saving"
      @ok="handleSave"
      @cancel="modalVisible = false"
      width="560px"
      destroyOnClose
    >
      <a-form :model="form" :labelCol="{ span: 5 }" :wrapperCol="{ span: 18 }">
        <a-form-item label="标签Key" required>
          <a-input v-model:value="form.label_key" placeholder="如 spam、toxic" :disabled="isEdit" />
        </a-form-item>
        <a-form-item label="标签类型" required>
          <a-select v-model:value="form.label_type" placeholder="请选择" :disabled="isEdit">
            <a-select-option value="text">文案标签</a-select-option>
            <a-select-option value="image">图片标签</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="显示名称" required>
          <a-input v-model:value="form.display_name" placeholder="中文显示名称" />
        </a-form-item>
        <a-form-item label="描述">
          <a-textarea v-model:value="form.description" placeholder="标签详细描述" :rows="2" />
        </a-form-item>
        <a-form-item label="处置动作" required>
          <a-select v-model:value="form.action" placeholder="请选择">
            <a-select-option value="pass">通过 (pass)</a-select-option>
            <a-select-option value="reject">拒绝 (reject)</a-select-option>
            <a-select-option value="reject_warn">拒绝+预警 (reject_warn)</a-select-option>
            <a-select-option value="reject_report">拒绝+上报 (reject_report)</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="启用状态">
          <a-switch v-model:checked="form.enabled" />
        </a-form-item>
        <a-form-item label="排序序号">
          <a-input-number v-model:value="form.sort_order" :min="0" style="width: 100%" placeholder="数值越小越靠前" />
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import apiClient from '../api/client'

// ---- Types ----
interface LabelRecord {
  id: string
  label_key: string
  label_type: string
  display_name: string
  description: string | null
  action: string
  enabled: boolean
  sort_order: number
  created_at: string
  updated_at: string
  _toggling?: boolean
}

// ---- Table columns ----
const columns = [
  { title: '标签Key', dataIndex: 'label_key', width: 140 },
  { title: '显示名称', dataIndex: 'display_name', width: 140 },
  { title: '描述', dataIndex: 'description', ellipsis: true },
  { title: '处置动作', dataIndex: 'action', width: 130 },
  { title: '启用', dataIndex: 'enabled', width: 80 },
  { title: '排序', dataIndex: 'sort_order', width: 80, sorter: (a: LabelRecord, b: LabelRecord) => a.sort_order - b.sort_order },
  { title: '操作', dataIndex: 'operations', width: 150 },
]

// ---- State ----
const labels = ref<LabelRecord[]>([])
const loading = ref(false)
const activeTab = ref('text')

// Modal
const modalVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const form = reactive({
  label_key: '',
  label_type: 'text',
  display_name: '',
  description: '',
  action: 'reject',
  enabled: true,
  sort_order: 0,
})

// ---- Helpers ----
function actionLabel(a: string) {
  const map: Record<string, string> = {
    pass: '通过',
    reject: '拒绝',
    reject_warn: '拒绝+预警',
    reject_report: '拒绝+上报',
  }
  return map[a] || a
}

function actionColor(a: string) {
  const map: Record<string, string> = {
    pass: 'green',
    reject: 'red',
    reject_warn: 'orange',
    reject_report: 'volcano',
  }
  return map[a] || 'default'
}

// ---- Fetch labels ----
async function fetchLabels() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/admin/labels', {
      params: { label_type: activeTab.value },
    })
    labels.value = data.items || []
  } catch {
    message.error('加载标签列表失败')
  } finally {
    loading.value = false
  }
}

function onTabChange() {
  fetchLabels()
}

// ---- Toggle enabled ----
async function toggleEnabled(record: LabelRecord, checked: boolean) {
  record._toggling = true
  try {
    await apiClient.put(`/admin/labels/${record.id}`, { enabled: checked })
    record.enabled = checked
    message.success(checked ? '已启用' : '已禁用')
  } catch {
    message.error('操作失败')
  } finally {
    record._toggling = false
  }
}

// ---- Create / Edit ----
function resetForm() {
  form.label_key = ''
  form.label_type = activeTab.value
  form.display_name = ''
  form.description = ''
  form.action = 'reject'
  form.enabled = true
  form.sort_order = 0
}

function openCreateModal() {
  isEdit.value = false
  editingId.value = null
  resetForm()
  modalVisible.value = true
}

function openEditModal(record: LabelRecord) {
  isEdit.value = true
  editingId.value = record.id
  form.label_key = record.label_key
  form.label_type = record.label_type
  form.display_name = record.display_name
  form.description = record.description || ''
  form.action = record.action
  form.enabled = record.enabled
  form.sort_order = record.sort_order
  modalVisible.value = true
}

async function handleSave() {
  if (!form.label_key || !form.label_type || !form.display_name || !form.action) {
    message.warning('请填写所有必填字段')
    return
  }

  saving.value = true
  try {
    if (isEdit.value && editingId.value) {
      const payload: Record<string, unknown> = {
        display_name: form.display_name,
        description: form.description || null,
        action: form.action,
        enabled: form.enabled,
        sort_order: form.sort_order,
      }
      await apiClient.put(`/admin/labels/${editingId.value}`, payload)
      message.success('标签已更新')
    } else {
      await apiClient.post('/admin/labels', {
        label_key: form.label_key,
        label_type: form.label_type,
        display_name: form.display_name,
        description: form.description || null,
        action: form.action,
        enabled: form.enabled,
        sort_order: form.sort_order,
      })
      message.success('标签已创建')
    }
    modalVisible.value = false
    fetchLabels()
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    message.error(detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// ---- Delete ----
async function deleteLabel(id: string) {
  try {
    await apiClient.delete(`/admin/labels/${id}`)
    message.success('标签已删除')
    fetchLabels()
  } catch {
    message.error('删除失败')
  }
}

// ---- Init ----
fetchLabels()
</script>
