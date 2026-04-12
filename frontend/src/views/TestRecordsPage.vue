<template>
  <div>
    <!-- Test Records Table -->
    <a-card title="历史测试记录" style="margin-bottom: 16px">
      <a-table
        :columns="columns"
        :dataSource="records"
        :loading="loading"
        :pagination="pagination"
        @change="handleTableChange"
        rowKey="id"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'status'">
            <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
          </template>
          <template v-if="column.dataIndex === 'progress'">
            {{ record.progress_current }} / {{ record.progress_total }}
          </template>
          <template v-if="column.dataIndex === 'started_at'">
            {{ formatTime(record.started_at) }}
          </template>
          <template v-if="column.dataIndex === 'completed_at'">
            {{ formatTime(record.completed_at) }}
          </template>
          <template v-if="column.dataIndex === 'actions'">
            <a-button size="small" @click="selectForCompare(record.id)">选择对比</a-button>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Compare Section -->
    <a-card title="结果对比" style="margin-bottom: 16px">
      <a-row :gutter="16" align="middle" style="margin-bottom: 16px">
        <a-col :span="8">
          <a-select
            v-model:value="compareA"
            placeholder="选择记录 A"
            style="width: 100%"
            allowClear
            showSearch
            :filterOption="filterOption"
            :options="recordOptions"
          />
        </a-col>
        <a-col :span="8">
          <a-select
            v-model:value="compareB"
            placeholder="选择记录 B"
            style="width: 100%"
            allowClear
            showSearch
            :filterOption="filterOption"
            :options="recordOptions"
          />
        </a-col>
        <a-col :span="8">
          <a-button
            type="primary"
            @click="doCompare"
            :loading="comparing"
            :disabled="!compareA || !compareB || compareA === compareB"
          >
            对比
          </a-button>
        </a-col>
      </a-row>

      <!-- Compare Results Side by Side -->
      <a-row v-if="compareResult" :gutter="24">
        <a-col :span="12">
          <a-card title="记录 A" size="small">
            <template v-if="compareResult.record_a.report">
              <p>准确率: {{ fmtPct(compareResult.record_a.report.accuracy) }}</p>
              <p>召回率: {{ fmtPct(compareResult.record_a.report.recall) }}</p>
              <p>F1 分数: {{ fmtPct(compareResult.record_a.report.f1_score) }}</p>
              <div v-if="compareResult.record_a.report.confusion_matrix" style="margin-top: 8px">
                <strong>混淆矩阵</strong>
                <p>TP: {{ compareResult.record_a.report.confusion_matrix.TP ?? 0 }}  FP: {{ compareResult.record_a.report.confusion_matrix.FP ?? 0 }}</p>
                <p>TN: {{ compareResult.record_a.report.confusion_matrix.TN ?? 0 }}  FN: {{ compareResult.record_a.report.confusion_matrix.FN ?? 0 }}</p>
              </div>
            </template>
            <span v-else>暂无报告数据</span>
          </a-card>
        </a-col>
        <a-col :span="12">
          <a-card title="记录 B" size="small">
            <template v-if="compareResult.record_b.report">
              <p>准确率: {{ fmtPct(compareResult.record_b.report.accuracy) }}</p>
              <p>召回率: {{ fmtPct(compareResult.record_b.report.recall) }}</p>
              <p>F1 分数: {{ fmtPct(compareResult.record_b.report.f1_score) }}</p>
              <div v-if="compareResult.record_b.report.confusion_matrix" style="margin-top: 8px">
                <strong>混淆矩阵</strong>
                <p>TP: {{ compareResult.record_b.report.confusion_matrix.TP ?? 0 }}  FP: {{ compareResult.record_b.report.confusion_matrix.FP ?? 0 }}</p>
                <p>TN: {{ compareResult.record_b.report.confusion_matrix.TN ?? 0 }}  FN: {{ compareResult.record_b.report.confusion_matrix.FN ?? 0 }}</p>
              </div>
            </template>
            <span v-else>暂无报告数据</span>
          </a-card>
        </a-col>
      </a-row>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import type { TablePaginationConfig } from 'ant-design-vue'
import apiClient from '../api/client'

// ---- Types ----
interface TestRecord {
  id: string
  test_suite_id: string
  status: string
  progress_current: number
  progress_total: number
  report: Record<string, any> | null
  started_at: string | null
  completed_at: string | null
}

interface CompareResult {
  record_a: TestRecord
  record_b: TestRecord
}

// ---- State ----
const loading = ref(false)
const records = ref<TestRecord[]>([])
const currentPage = ref(1)
const pageSize = ref(20)
const total = ref(0)

const compareA = ref<string | undefined>(undefined)
const compareB = ref<string | undefined>(undefined)
const comparing = ref(false)
const compareResult = ref<CompareResult | null>(null)

// ---- Table columns ----
const columns = [
  { title: 'ID', dataIndex: 'id', width: 120, ellipsis: true },
  { title: '测试集 ID', dataIndex: 'test_suite_id', width: 120, ellipsis: true },
  { title: '状态', dataIndex: 'status', width: 100 },
  { title: '进度', dataIndex: 'progress', width: 120 },
  { title: '开始时间', dataIndex: 'started_at', width: 180 },
  { title: '完成时间', dataIndex: 'completed_at', width: 180 },
  { title: '操作', dataIndex: 'actions', width: 100 },
]

const pagination = computed<TablePaginationConfig>(() => ({
  current: currentPage.value,
  pageSize: pageSize.value,
  total: total.value,
  showSizeChanger: true,
  showTotal: (t: number) => `共 ${t} 条`,
}))

const recordOptions = computed(() =>
  records.value.map((r) => ({
    label: `${r.id.slice(0, 8)}… (${r.status})`,
    value: r.id,
  }))
)

// ---- Helpers ----
function statusColor(s: string) {
  return (
    { completed: 'green', failed: 'red', running: 'blue', pending: 'default' }[s] || 'default'
  )
}

function formatTime(t: string | null): string {
  if (!t) return '-'
  return new Date(t).toLocaleString()
}

function fmtPct(v: any): string {
  if (v == null) return '-'
  return (v * 100).toFixed(1) + '%'
}

function filterOption(input: string, option: { label: string }) {
  return option.label.toLowerCase().includes(input.toLowerCase())
}

// ---- Load records ----
async function loadRecords() {
  loading.value = true
  try {
    const { data } = await apiClient.get('/admin/test-records', {
      params: { page: currentPage.value, page_size: pageSize.value },
    })
    records.value = data
    total.value =
      data.length < pageSize.value
        ? (currentPage.value - 1) * pageSize.value + data.length
        : currentPage.value * pageSize.value + 1
  } catch {
    message.error('加载测试记录失败')
  } finally {
    loading.value = false
  }
}

function handleTableChange(pag: TablePaginationConfig) {
  currentPage.value = pag.current ?? 1
  pageSize.value = pag.pageSize ?? 20
  loadRecords()
}

// ---- Select for compare ----
function selectForCompare(id: string) {
  if (!compareA.value) {
    compareA.value = id
    message.info('已选为记录 A，请再选择记录 B')
  } else if (!compareB.value && id !== compareA.value) {
    compareB.value = id
  } else {
    compareA.value = id
    compareB.value = undefined
    compareResult.value = null
  }
}

// ---- Compare ----
async function doCompare() {
  if (!compareA.value || !compareB.value) return
  comparing.value = true
  compareResult.value = null
  try {
    const { data } = await apiClient.post('/admin/test-records/compare', {
      record_id_a: compareA.value,
      record_id_b: compareB.value,
    })
    compareResult.value = data
  } catch (e: any) {
    const detail = e.response?.data?.detail || '对比失败'
    message.error(detail)
  } finally {
    comparing.value = false
  }
}

// ---- Init ----
onMounted(() => {
  loadRecords()
})
</script>
