<template>
  <div>
    <a-table
      :columns="columns"
      :dataSource="configs"
      :loading="loading"
      rowKey="id"
      :pagination="false"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'is_primary'">
          <a-tag v-if="record.is_primary" color="green">主模型</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'is_fallback'">
          <a-tag v-if="record.is_fallback" color="orange">备用</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'cost'">
          <span>输入 ${{ record.cost_per_1k_input }} / 输出 ${{ record.cost_per_1k_output }}</span>
        </template>
        <template v-else-if="column.dataIndex === 'fallback_result'">
          {{ record.fallback_result || '-' }}
        </template>
        <template v-else-if="column.dataIndex === 'actions'">
          <a-button type="link" size="small" @click="openEdit(record)">编辑</a-button>
        </template>
      </template>
    </a-table>

    <!-- Edit modal -->
    <a-modal
      v-model:open="modalVisible"
      title="编辑模型配置"
      :confirmLoading="saving"
      @ok="handleSave"
      @cancel="modalVisible = false"
      width="520px"
      destroyOnClose
    >
      <a-form :labelCol="{ span: 7 }" :wrapperCol="{ span: 16 }">
        <a-form-item label="模型名称">
          <a-input :value="editRecord?.model_name" disabled />
        </a-form-item>
        <a-form-item label="模型 ID">
          <a-input :value="editRecord?.model_id" disabled />
        </a-form-item>
        <a-form-item label="Temperature">
          <a-slider v-model:value="form.temperature" :min="0" :max="2" :step="0.1" />
        </a-form-item>
        <a-form-item label="Max Tokens">
          <a-input-number v-model:value="form.max_tokens" :min="1" :max="100000" style="width: 100%" />
        </a-form-item>
        <a-form-item label="主模型">
          <a-switch v-model:checked="form.is_primary" />
        </a-form-item>
        <a-form-item label="备用模型">
          <a-switch v-model:checked="form.is_fallback" />
        </a-form-item>
        <a-form-item label="降级默认结果">
          <a-select v-model:value="form.fallback_result" placeholder="请选择" allowClear>
            <a-select-option value="pass">通过 (pass)</a-select-option>
            <a-select-option value="reject">拒绝 (reject)</a-select-option>
            <a-select-option value="review">人工复审 (review)</a-select-option>
            <a-select-option value="flag">标记 (flag)</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { message } from 'ant-design-vue'
import apiClient from '../api/client'

interface ConfigRecord {
  id: string
  model_id: string
  model_name: string
  temperature: number
  max_tokens: number
  is_primary: boolean
  is_fallback: boolean
  fallback_result: string | null
  cost_per_1k_input: number
  cost_per_1k_output: number
  updated_at: string
}

const columns = [
  { title: '模型名称', dataIndex: 'model_name', width: 160 },
  { title: '模型 ID', dataIndex: 'model_id', ellipsis: true },
  { title: 'Temperature', dataIndex: 'temperature', width: 110 },
  { title: 'Max Tokens', dataIndex: 'max_tokens', width: 110 },
  { title: '主模型', dataIndex: 'is_primary', width: 90 },
  { title: '备用', dataIndex: 'is_fallback', width: 80 },
  { title: '参考成本 (每千token)', dataIndex: 'cost', width: 200 },
  { title: '降级结果', dataIndex: 'fallback_result', width: 100 },
  { title: '操作', dataIndex: 'actions', width: 80 },
]

const configs = ref<ConfigRecord[]>([])
const loading = ref(false)

const modalVisible = ref(false)
const saving = ref(false)
const editRecord = ref<ConfigRecord | null>(null)
const form = reactive({
  temperature: 0,
  max_tokens: 4096,
  is_primary: false,
  is_fallback: false,
  fallback_result: null as string | null,
})

async function fetchConfigs() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/admin/model-config')
    configs.value = data
  } catch {
    message.error('加载模型配置失败')
  } finally {
    loading.value = false
  }
}

function openEdit(record: ConfigRecord) {
  editRecord.value = record
  form.temperature = record.temperature
  form.max_tokens = record.max_tokens
  form.is_primary = record.is_primary
  form.is_fallback = record.is_fallback
  form.fallback_result = record.fallback_result
  modalVisible.value = true
}

async function handleSave() {
  if (!editRecord.value) return
  saving.value = true
  try {
    await apiClient.put(`/admin/model-config/${editRecord.value.id}`, {
      temperature: form.temperature,
      max_tokens: form.max_tokens,
      is_primary: form.is_primary,
      is_fallback: form.is_fallback,
      fallback_result: form.fallback_result,
    })
    message.success('模型配置已更新')
    modalVisible.value = false
    fetchConfigs()
  } catch {
    message.error('更新失败')
  } finally {
    saving.value = false
  }
}

fetchConfigs()
</script>
