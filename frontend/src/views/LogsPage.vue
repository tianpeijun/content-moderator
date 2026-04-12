<template>
  <div>
    <!-- Filter bar -->
    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="6">
        <a-range-picker
          v-model:value="filters.dateRange"
          :placeholder="['开始时间', '结束时间']"
          show-time
          style="width: 100%"
          @change="fetchLogs"
        />
      </a-col>
      <a-col :span="4">
        <a-select
          v-model:value="filters.result"
          placeholder="审核结果"
          allowClear
          style="width: 100%"
          @change="fetchLogs"
        >
          <a-select-option value="pass">通过</a-select-option>
          <a-select-option value="reject">拒绝</a-select-option>
          <a-select-option value="review">人工复审</a-select-option>
          <a-select-option value="flag">标记</a-select-option>
        </a-select>
      </a-col>
      <a-col :span="4">
        <a-input
          v-model:value="filters.business_type"
          placeholder="业务类型"
          allowClear
          @pressEnter="fetchLogs"
          @change="onBusinessTypeChange"
        />
      </a-col>
      <a-col :span="4">
        <a-select
          v-model:value="filters.text_label"
          placeholder="文案标签"
          allowClear
          style="width: 100%"
          @change="fetchLogs"
        >
          <a-select-option v-for="opt in textLabelOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</a-select-option>
        </a-select>
      </a-col>
    </a-row>
    <a-row :gutter="16" style="margin-bottom: 16px">
      <a-col :span="4">
        <a-select
          v-model:value="filters.image_label"
          placeholder="图片标签"
          allowClear
          style="width: 100%"
          @change="fetchLogs"
        >
          <a-select-option v-for="opt in imageLabelOptions" :key="opt.value" :value="opt.value">{{ opt.label }}</a-select-option>
        </a-select>
      </a-col>
      <a-col :span="4">
        <a-button type="primary" @click="fetchLogs">查询</a-button>
        <a-button style="margin-left: 8px" @click="resetFilters">重置</a-button>
      </a-col>
      <a-col :span="6" style="text-align: right">
        <a-button @click="handleExport" :loading="exporting">导出日志</a-button>
      </a-col>
    </a-row>

    <!-- Logs table -->
    <a-table
      :columns="columns"
      :dataSource="logs"
      :loading="loading"
      rowKey="id"
      :pagination="pagination"
      @change="onTableChange"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.dataIndex === 'result'">
          <a-tag :color="resultColor(record.result)">{{ resultLabel(record.result) }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'status'">
          <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
        </template>
        <template v-else-if="column.dataIndex === 'text_label'">
          <a-tag v-if="record.text_label" :color="textLabelColor(record.text_label)">{{ record.text_label }}</a-tag>
          <span v-else>-</span>
        </template>
        <template v-else-if="column.dataIndex === 'image_label'">
          <a-tag v-if="record.image_label" :color="imageLabelColor(record.image_label)">{{ record.image_label }}</a-tag>
          <span v-else>-</span>
        </template>
        <template v-else-if="column.dataIndex === 'created_at'">
          {{ formatTime(record.created_at) }}
        </template>
        <template v-else-if="column.dataIndex === 'processing_time_ms'">
          {{ record.processing_time_ms != null ? `${record.processing_time_ms} ms` : '-' }}
        </template>
        <template v-else-if="column.dataIndex === 'actions'">
          <a-button type="link" size="small" @click="openDetail(record)">查看详情</a-button>
        </template>
      </template>
    </a-table>

    <!-- Detail drawer -->
    <a-drawer
      v-model:open="drawerVisible"
      title="审核日志详情"
      width="640"
      @close="drawerVisible = false"
    >
      <a-spin :spinning="detailLoading">
        <template v-if="detail">
          <a-descriptions bordered :column="1" size="small">
            <a-descriptions-item label="任务ID">{{ detail.task_id }}</a-descriptions-item>
            <a-descriptions-item label="状态">
              <a-tag :color="statusColor(detail.status)">{{ detail.status }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="审核结果">
              <a-tag :color="resultColor(detail.result)">{{ resultLabel(detail.result) }}</a-tag>
            </a-descriptions-item>
            <a-descriptions-item label="文案标签">
              <a-tag v-if="detail.text_label" :color="textLabelColor(detail.text_label)">{{ detail.text_label }}</a-tag>
              <span v-else>-</span>
            </a-descriptions-item>
            <a-descriptions-item label="图片标签">
              <a-tag v-if="detail.image_label" :color="imageLabelColor(detail.image_label)">{{ detail.image_label }}</a-tag>
              <span v-else>-</span>
            </a-descriptions-item>
            <a-descriptions-item label="置信度">{{ detail.confidence != null ? detail.confidence : '-' }}</a-descriptions-item>
            <a-descriptions-item label="业务类型">{{ detail.business_type || '-' }}</a-descriptions-item>
            <a-descriptions-item label="处理耗时">{{ detail.processing_time_ms != null ? `${detail.processing_time_ms} ms` : '-' }}</a-descriptions-item>
            <a-descriptions-item label="模型ID">{{ detail.model_id || '-' }}</a-descriptions-item>
            <a-descriptions-item label="降级处理">{{ detail.degraded ? '是' : '否' }}</a-descriptions-item>
            <a-descriptions-item label="创建时间">{{ formatTime(detail.created_at) }}</a-descriptions-item>
          </a-descriptions>

          <a-divider>原始内容</a-divider>
          <div v-if="detail.input_text" style="margin-bottom: 12px">
            <strong>文本内容：</strong>
            <p style="white-space: pre-wrap; background: #f5f5f5; padding: 8px; border-radius: 4px">{{ detail.input_text }}</p>
          </div>
          <div v-if="detail.input_image_url" style="margin-bottom: 12px">
            <strong>图片URL：</strong>
            <p>{{ detail.input_image_url }}</p>
          </div>

          <a-divider>提示词</a-divider>
          <pre style="white-space: pre-wrap; background: #f5f5f5; padding: 8px; border-radius: 4px; max-height: 300px; overflow: auto; font-size: 12px">{{ detail.final_prompt || '-' }}</pre>

          <a-divider>模型响应</a-divider>
          <pre style="white-space: pre-wrap; background: #f5f5f5; padding: 8px; border-radius: 4px; max-height: 300px; overflow: auto; font-size: 12px">{{ detail.model_response || '-' }}</pre>

          <a-divider>命中规则</a-divider>
          <pre v-if="detail.matched_rules" style="white-space: pre-wrap; background: #f5f5f5; padding: 8px; border-radius: 4px; max-height: 200px; overflow: auto; font-size: 12px">{{ JSON.stringify(detail.matched_rules, null, 2) }}</pre>
          <span v-else>-</span>
        </template>
      </a-spin>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { message } from 'ant-design-vue'
import type { Dayjs } from 'dayjs'
import apiClient from '../api/client'

// ---- Types ----
interface LogListItem {
  id: string
  task_id: string
  status: string
  result: string | null
  text_label: string | null
  image_label: string | null
  business_type: string | null
  created_at: string
  processing_time_ms: number | null
}

interface LogDetail {
  id: string
  task_id: string
  status: string
  input_text: string | null
  input_image_url: string | null
  business_type: string | null
  final_prompt: string | null
  model_response: string | null
  result: string | null
  text_label: string | null
  image_label: string | null
  confidence: number | null
  matched_rules: unknown
  processing_time_ms: number | null
  degraded: boolean
  model_id: string | null
  created_at: string
}

// ---- Table columns ----
const columns = [
  { title: '任务ID', dataIndex: 'task_id', ellipsis: true, width: 180 },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '审核结果', dataIndex: 'result', width: 100 },
  { title: '文案标签', dataIndex: 'text_label', width: 120 },
  { title: '图片标签', dataIndex: 'image_label', width: 120 },
  { title: '业务类型', dataIndex: 'business_type', width: 120 },
  { title: '创建时间', dataIndex: 'created_at', width: 180 },
  { title: '处理耗时', dataIndex: 'processing_time_ms', width: 110 },
  { title: '操作', dataIndex: 'actions', width: 100 },
]

// ---- State ----
const logs = ref<LogListItem[]>([])
const loading = ref(false)
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

const filters = reactive<{
  dateRange: [Dayjs, Dayjs] | null
  result?: string
  business_type?: string
  text_label?: string
  image_label?: string
}>({
  dateRange: null,
})

// Detail drawer
const drawerVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<LogDetail | null>(null)

// Export
const exporting = ref(false)

// ---- Pagination ----
const pagination = computed(() => ({
  current: currentPage.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
}))

// ---- Helpers ----
function resultLabel(r: string | null) {
  if (!r) return '-'
  return { pass: '通过', reject: '拒绝', review: '人工复审', flag: '标记' }[r] || r
}
function resultColor(r: string | null) {
  if (!r) return 'default'
  return { pass: 'green', reject: 'red', review: 'orange', flag: 'blue' }[r] || 'default'
}
function statusColor(s: string) {
  return { completed: 'green', failed: 'red', processing: 'blue', pending: 'default' }[s] || 'default'
}
function textLabelColor(label: string) {
  return label === 'safe' ? 'green' : 'red'
}
function imageLabelColor(label: string) {
  return label === '无' ? 'default' : 'red'
}
function formatTime(iso: string) {
  return new Date(iso).toLocaleString('zh-CN')
}

// ---- Label filter options ----
const textLabelOptions = [
  { value: 'safe', label: 'safe' },
  { value: 'spam', label: 'spam' },
  { value: 'toxic', label: 'toxic' },
  { value: 'hate_speech', label: 'hate_speech' },
  { value: 'privacy_leak', label: 'privacy_leak' },
  { value: 'political', label: 'political' },
  { value: 'self_harm', label: 'self_harm' },
  { value: 'illegal_trade', label: 'illegal_trade' },
  { value: 'misleading', label: 'misleading' },
]
const imageLabelOptions = [
  { value: '无', label: '无' },
  { value: 'pornography', label: 'pornography' },
  { value: 'gambling', label: 'gambling' },
  { value: 'drugs', label: 'drugs' },
  { value: 'violence', label: 'violence' },
  { value: 'terrorism', label: 'terrorism' },
  { value: 'qr_code_spam', label: 'qr_code_spam' },
  { value: 'contact_info', label: 'contact_info' },
  { value: 'ad_overlay', label: 'ad_overlay' },
  { value: 'minor_exploitation', label: 'minor_exploitation' },
]

// ---- Build query params ----
function buildParams() {
  const params: Record<string, unknown> = {
    page: currentPage.value,
    page_size: pageSize.value,
  }
  if (filters.dateRange && filters.dateRange[0] && filters.dateRange[1]) {
    params.start_date = filters.dateRange[0].toISOString()
    params.end_date = filters.dateRange[1].toISOString()
  }
  if (filters.result) params.result = filters.result
  if (filters.business_type) params.business_type = filters.business_type
  if (filters.text_label) params.text_label = filters.text_label
  if (filters.image_label) params.image_label = filters.image_label
  return params
}

// ---- Fetch logs ----
async function fetchLogs() {
  loading.value = true
  try {
    const params = buildParams()
    const { data } = await apiClient.get('/admin/logs', { params })
    logs.value = data.items
    total.value = data.total
    currentPage.value = data.page
    pageSize.value = data.page_size
  } catch {
    message.error('加载审核日志失败')
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  filters.dateRange = null
  filters.result = undefined
  filters.business_type = undefined
  filters.text_label = undefined
  filters.image_label = undefined
  currentPage.value = 1
  fetchLogs()
}

function onBusinessTypeChange() {
  if (!filters.business_type) fetchLogs()
}

function onTableChange(pag: { current?: number; pageSize?: number }) {
  if (pag.current) currentPage.value = pag.current
  if (pag.pageSize) pageSize.value = pag.pageSize
  fetchLogs()
}

// ---- Detail drawer ----
async function openDetail(record: LogListItem) {
  drawerVisible.value = true
  detailLoading.value = true
  detail.value = null
  try {
    const { data } = await apiClient.get(`/admin/logs/${record.id}`)
    detail.value = data
  } catch {
    message.error('加载日志详情失败')
  } finally {
    detailLoading.value = false
  }
}

// ---- Export ----
async function handleExport() {
  exporting.value = true
  try {
    const params = buildParams()
    // Remove pagination params for export
    delete params.page
    delete params.page_size
    const { data } = await apiClient.post('/admin/logs/export', null, { params })
    // Download as JSON file
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `audit-logs-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success(`已导出 ${data.total} 条日志`)
  } catch {
    message.error('导出失败')
  } finally {
    exporting.value = false
  }
}

// ---- Init ----
fetchLogs()
</script>
