<template>
  <div>
    <!-- Filter bar -->
    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="5">
        <a-select
          v-model:value="filters.type"
          placeholder="按类型筛选"
          allowClear
          style="width: 100%"
          @change="fetchRules"
        >
          <a-select-option value="text">文本</a-select-option>
          <a-select-option value="image">图片</a-select-option>
          <a-select-option value="both">文本+图片</a-select-option>
        </a-select>
      </a-col>
      <a-col :span="5">
        <a-input
          v-model:value="filters.business_type"
          placeholder="业务类型"
          allowClear
          @pressEnter="fetchRules"
          @change="onBusinessTypeChange"
        />
      </a-col>
      <a-col :span="5">
        <a-select
          v-model:value="filters.enabled"
          placeholder="启用状态"
          allowClear
          style="width: 100%"
          @change="fetchRules"
        >
          <a-select-option :value="true">已启用</a-select-option>
          <a-select-option :value="false">已禁用</a-select-option>
        </a-select>
      </a-col>
      <a-col :span="4">
        <a-button type="primary" @click="fetchRules">查询</a-button>
        <a-button style="margin-left: 8px" @click="resetFilters">重置</a-button>
      </a-col>
      <a-col :span="5" style="text-align: right">
        <a-button type="primary" @click="openCreateModal">新建规则</a-button>
      </a-col>
    </a-row>

    <!-- Rules table -->
    <a-table
      :columns="columns"
      :dataSource="rules"
      :loading="loading"
      rowKey="id"
      :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (total: number) => `共 ${total} 条` }"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'type'">
          {{ typeLabel(record.type) }}
        </template>
        <template v-else-if="column.dataIndex === 'action'">
          <a-tag :color="actionColor(record.action)">{{ actionLabel(record.action) }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'enabled'">
          <a-switch
            :checked="record.enabled"
            @change="(checked: boolean) => toggleEnabled(record, checked)"
            :loading="record._toggling"
          />
        </template>
        <template v-else-if="column.dataIndex === 'actions'">
          <a-button type="link" size="small" @click="openEditModal(record)">编辑</a-button>
          <a-popconfirm
            title="确定删除该规则？"
            okText="确定"
            cancelText="取消"
            @confirm="deleteRule(record.id)"
          >
            <a-button type="link" size="small" danger>删除</a-button>
          </a-popconfirm>
          <a-button type="link" size="small" @click="openVersionDrawer(record)">版本历史</a-button>
        </template>
      </template>
    </a-table>

    <!-- Create / Edit modal -->
    <a-modal
      v-model:open="modalVisible"
      :title="isEdit ? '编辑规则' : '新建规则'"
      :confirmLoading="saving"
      @ok="handleSave"
      @cancel="modalVisible = false"
      width="680px"
      destroyOnClose
    >
      <a-form :model="form" :labelCol="{ span: 5 }" :wrapperCol="{ span: 18 }">
        <a-form-item label="规则名称" required>
          <a-input v-model:value="form.name" placeholder="请输入规则名称" />
        </a-form-item>
        <a-form-item label="类型" required>
          <a-select v-model:value="form.type" placeholder="请选择类型">
            <a-select-option value="text">文本</a-select-option>
            <a-select-option value="image">图片</a-select-option>
            <a-select-option value="both">文本+图片</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="业务类型">
          <a-input v-model:value="form.business_type" placeholder="请输入业务类型" />
        </a-form-item>
        <a-form-item label="提示词模板" required>
          <a-textarea
            v-model:value="form.prompt_template"
            placeholder="请输入提示词模板，支持 {{variable}} 变量"
            :rows="5"
          />
        </a-form-item>
        <a-form-item label="变量配置">
          <a-textarea
            v-model:value="variablesJson"
            placeholder='JSON 格式，如 {"competitor_list": ["品牌A","品牌B"]}'
            :rows="3"
          />
        </a-form-item>
        <a-form-item label="触发动作" required>
          <a-select v-model:value="form.action" placeholder="请选择触发动作">
            <a-select-option value="reject">拒绝 (reject)</a-select-option>
            <a-select-option value="review">人工复审 (review)</a-select-option>
            <a-select-option value="flag">标记 (flag)</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="优先级" required>
          <a-input-number v-model:value="form.priority" :min="0" style="width: 100%" placeholder="数值越小优先级越高" />
        </a-form-item>
        <a-form-item label="启用状态">
          <a-switch v-model:checked="form.enabled" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- Version history drawer -->
    <a-drawer
      v-model:open="drawerVisible"
      :title="`版本历史 — ${currentRuleName}`"
      width="600"
      @close="drawerVisible = false"
    >
      <a-spin :spinning="versionsLoading">
        <a-empty v-if="!versionsLoading && versions.length === 0" description="暂无版本记录" />
        <a-timeline v-else>
          <a-timeline-item v-for="v in versions" :key="v.id">
            <p><strong>版本 {{ v.version }}</strong> — {{ formatTime(v.modified_at) }}</p>
            <p v-if="v.modified_by">修改人：{{ v.modified_by }}</p>
            <p v-if="v.change_summary">{{ v.change_summary }}</p>
            <a-collapse :bordered="false">
              <a-collapse-panel header="查看快照">
                <pre style="font-size: 12px; max-height: 300px; overflow: auto">{{ JSON.stringify(v.snapshot, null, 2) }}</pre>
              </a-collapse-panel>
            </a-collapse>
          </a-timeline-item>
        </a-timeline>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import apiClient from '../api/client'

// ---- Types ----
interface RuleRecord {
  id: string
  name: string
  type: string
  business_type: string | null
  prompt_template: string
  variables: Record<string, unknown> | null
  action: string
  priority: number
  enabled: boolean
  created_at: string
  updated_at: string
  _toggling?: boolean
}

interface VersionRecord {
  id: string
  rule_id: string
  version: number
  snapshot: Record<string, unknown>
  modified_by: string | null
  modified_at: string
  change_summary: string | null
}

// ---- Table columns ----
const columns = [
  { title: '规则名称', dataIndex: 'name', ellipsis: true },
  { title: '类型', dataIndex: 'type', width: 100 },
  { title: '业务类型', dataIndex: 'business_type', width: 120 },
  { title: '触发动作', dataIndex: 'action', width: 120 },
  { title: '优先级', dataIndex: 'priority', width: 80, sorter: (a: RuleRecord, b: RuleRecord) => a.priority - b.priority },
  { title: '启用', dataIndex: 'enabled', width: 80 },
  { title: '操作', dataIndex: 'actions', width: 220 },
]

// ---- State ----
const rules = ref<RuleRecord[]>([])
const loading = ref(false)
const filters = reactive<{ type?: string; business_type?: string; enabled?: boolean }>({})

// Modal
const modalVisible = ref(false)
const isEdit = ref(false)
const editingId = ref<string | null>(null)
const saving = ref(false)
const form = reactive({
  name: '',
  type: 'text' as string,
  business_type: '',
  prompt_template: '',
  action: 'reject' as string,
  priority: 0,
  enabled: true,
})
const variablesJson = ref('')

// Version drawer
const drawerVisible = ref(false)
const currentRuleName = ref('')
const versions = ref<VersionRecord[]>([])
const versionsLoading = ref(false)

// ---- Helpers ----
function typeLabel(t: string) {
  return { text: '文本', image: '图片', both: '文本+图片' }[t] || t
}
function actionLabel(a: string) {
  return { reject: '拒绝', review: '人工复审', flag: '标记' }[a] || a
}
function actionColor(a: string) {
  return { reject: 'red', review: 'orange', flag: 'blue' }[a] || 'default'
}
function formatTime(iso: string) {
  return new Date(iso).toLocaleString('zh-CN')
}

// ---- Fetch rules ----
async function fetchRules() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {}
    if (filters.type) params.type = filters.type
    if (filters.business_type) params.business_type = filters.business_type
    if (filters.enabled !== undefined && filters.enabled !== null) params.enabled = filters.enabled
    const { data } = await apiClient.get('/admin/rules', { params })
    rules.value = data
  } catch (e: unknown) {
    message.error('加载规则列表失败')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.type = undefined
  filters.business_type = undefined
  filters.enabled = undefined
  fetchRules()
}

function onBusinessTypeChange() {
  if (!filters.business_type) fetchRules()
}

// ---- Toggle enabled ----
async function toggleEnabled(record: RuleRecord, checked: boolean) {
  record._toggling = true
  try {
    await apiClient.put(`/admin/rules/${record.id}`, { enabled: checked })
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
  form.name = ''
  form.type = 'text'
  form.business_type = ''
  form.prompt_template = ''
  form.action = 'reject'
  form.priority = 0
  form.enabled = true
  variablesJson.value = ''
}

function openCreateModal() {
  isEdit.value = false
  editingId.value = null
  resetForm()
  modalVisible.value = true
}

function openEditModal(record: RuleRecord) {
  isEdit.value = true
  editingId.value = record.id
  form.name = record.name
  form.type = record.type
  form.business_type = record.business_type || ''
  form.prompt_template = record.prompt_template
  form.action = record.action
  form.priority = record.priority
  form.enabled = record.enabled
  variablesJson.value = record.variables ? JSON.stringify(record.variables, null, 2) : ''
  modalVisible.value = true
}

async function handleSave() {
  if (!form.name || !form.type || !form.prompt_template || !form.action || form.priority === undefined) {
    message.warning('请填写所有必填字段')
    return
  }

  let variables: Record<string, unknown> | null = null
  if (variablesJson.value.trim()) {
    try {
      variables = JSON.parse(variablesJson.value)
    } catch {
      message.error('变量配置 JSON 格式不正确')
      return
    }
  }

  const payload = {
    name: form.name,
    type: form.type,
    business_type: form.business_type || null,
    prompt_template: form.prompt_template,
    variables,
    action: form.action,
    priority: form.priority,
    enabled: form.enabled,
  }

  saving.value = true
  try {
    if (isEdit.value && editingId.value) {
      await apiClient.put(`/admin/rules/${editingId.value}`, payload)
      message.success('规则已更新')
    } else {
      await apiClient.post('/admin/rules', payload)
      message.success('规则已创建')
    }
    modalVisible.value = false
    fetchRules()
  } catch {
    message.error('保存失败')
  } finally {
    saving.value = false
  }
}

// ---- Delete ----
async function deleteRule(id: string) {
  try {
    await apiClient.delete(`/admin/rules/${id}`)
    message.success('规则已删除')
    fetchRules()
  } catch {
    message.error('删除失败')
  }
}

// ---- Version history ----
async function openVersionDrawer(record: RuleRecord) {
  currentRuleName.value = record.name
  drawerVisible.value = true
  versionsLoading.value = true
  versions.value = []
  try {
    const { data } = await apiClient.get(`/admin/rules/${record.id}/versions`)
    versions.value = data
  } catch {
    message.error('加载版本历史失败')
  } finally {
    versionsLoading.value = false
  }
}

// ---- Init ----
fetchRules()
</script>
