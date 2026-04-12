<template>
  <div>
    <!-- Step 1: Upload test suite -->
    <a-card title="上传测试集" style="margin-bottom: 16px">
      <a-upload
        :beforeUpload="handleBeforeUpload"
        :showUploadList="false"
        accept=".xlsx"
      >
        <a-button :loading="uploading">
          <upload-outlined />
          选择 .xlsx 文件
        </a-button>
      </a-upload>
      <span v-if="uploadedSuite" style="margin-left: 12px">
        <a-tag color="green">{{ uploadedSuite.name }} — {{ uploadedSuite.total_cases }} 条用例</a-tag>
      </span>
    </a-card>

    <!-- Step 2: Select rules & start test -->
    <a-card title="选择规则并启动测试" style="margin-bottom: 16px" v-if="uploadedSuite">
      <a-row :gutter="16" align="middle">
        <a-col :span="16">
          <a-select
            v-model:value="selectedRuleIds"
            mode="multiple"
            placeholder="选择要使用的规则"
            style="width: 100%"
            :options="ruleOptions"
            :loading="rulesLoading"
          />
        </a-col>
        <a-col :span="8">
          <a-button
            type="primary"
            @click="startTest"
            :loading="starting"
            :disabled="selectedRuleIds.length === 0"
          >
            启动测试
          </a-button>
        </a-col>
      </a-row>
    </a-card>

    <!-- Step 3: Progress -->
    <a-card title="测试进度" style="margin-bottom: 16px" v-if="testRecordId">
      <a-progress
        :percent="progressPercent"
        :status="progressStatus"
        :format="() => `${progress.current} / ${progress.total}`"
      />
      <p style="margin-top: 8px">
        状态：<a-tag :color="statusColor(progress.statusText)">{{ progress.statusText }}</a-tag>
      </p>
    </a-card>

    <!-- Step 4: Report -->
    <a-card title="测试报告" style="margin-bottom: 16px" v-if="report">
      <a-row :gutter="16" style="margin-bottom: 16px">
        <a-col :span="6">
          <a-statistic title="准确率" :value="formatPct(report.accuracy)" suffix="%" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="召回率" :value="formatPct(report.recall)" suffix="%" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="F1 分数" :value="formatPct(report.f1_score)" suffix="%" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="文案标签准确率" :value="formatPct(report.text_label_accuracy)" suffix="%" />
        </a-col>
      </a-row>
      <a-row :gutter="16" style="margin-bottom: 16px">
        <a-col :span="6">
          <a-statistic title="图片标签准确率" :value="formatPct(report.image_label_accuracy)" suffix="%" />
        </a-col>
      </a-row>

      <!-- Confusion matrix -->
      <a-divider>混淆矩阵</a-divider>
      <a-table
        v-if="report.confusion_matrix"
        :columns="cmColumns"
        :dataSource="cmData"
        :pagination="false"
        size="small"
        bordered
        rowKey="label"
        style="max-width: 400px; margin-bottom: 16px"
      />

      <!-- Rule hit distribution -->
      <a-divider>规则命中分布</a-divider>
      <div v-if="report.rule_hit_distribution && Object.keys(report.rule_hit_distribution).length > 0">
        <a-descriptions bordered :column="2" size="small">
          <a-descriptions-item
            v-for="(count, ruleName) in report.rule_hit_distribution"
            :key="ruleName"
            :label="String(ruleName)"
          >
            {{ count }} 次
          </a-descriptions-item>
        </a-descriptions>
      </div>
      <a-empty v-else description="无规则命中数据" />

      <!-- Error cases -->
      <a-divider>错误案例</a-divider>
      <a-table
        v-if="report.error_cases && report.error_cases.length > 0"
        :columns="errorColumns"
        :dataSource="report.error_cases"
        :pagination="{ pageSize: 10, showSizeChanger: true, showTotal: (t: number) => `共 ${t} 条` }"
        size="small"
        rowKey="index"
      />
      <a-empty v-else description="无错误案例" />

      <!-- Export -->
      <div style="margin-top: 16px; text-align: right">
        <a-button @click="handleExport" :loading="exporting">导出报告</a-button>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onBeforeUnmount } from 'vue'
import { message } from 'ant-design-vue'
import { UploadOutlined } from '@ant-design/icons-vue'
import apiClient from '../api/client'

// ---- Types ----
interface UploadedSuite {
  id: string
  name: string
  total_cases: number
  created_at: string
}

interface RuleOption {
  label: string
  value: string
}

interface TestReport {
  test_record_id: string
  test_suite_id: string
  status: string
  accuracy: number | null
  recall: number | null
  f1_score: number | null
  text_label_accuracy: number | null
  image_label_accuracy: number | null
  confusion_matrix: Record<string, number> | null
  error_cases: Array<Record<string, unknown>> | null
  rule_hit_distribution: Record<string, number> | null
  started_at: string | null
  completed_at: string | null
}

// ---- State ----
const uploading = ref(false)
const uploadedSuite = ref<UploadedSuite | null>(null)

const rulesLoading = ref(false)
const ruleOptions = ref<RuleOption[]>([])
const selectedRuleIds = ref<string[]>([])

const starting = ref(false)
const testRecordId = ref<string | null>(null)

const progress = ref({ current: 0, total: 0, statusText: 'pending' })
let pollTimer: ReturnType<typeof setInterval> | null = null

const report = ref<TestReport | null>(null)
const exporting = ref(false)

// ---- Computed ----
const progressPercent = computed(() => {
  if (progress.value.total === 0) return 0
  return Math.round((progress.value.current / progress.value.total) * 100)
})

const progressStatus = computed(() => {
  if (progress.value.statusText === 'completed') return 'success' as const
  if (progress.value.statusText === 'failed') return 'exception' as const
  return 'active' as const
})

// ---- Confusion matrix table ----
const cmColumns = [
  { title: '指标', dataIndex: 'label', width: 200 },
  { title: '数量', dataIndex: 'value', width: 100 },
]

const cmData = computed(() => {
  const cm = report.value?.confusion_matrix
  if (!cm) return []
  return [
    { label: 'TP (真正例)', value: cm.TP ?? 0 },
    { label: 'FP (假正例)', value: cm.FP ?? 0 },
    { label: 'TN (真负例)', value: cm.TN ?? 0 },
    { label: 'FN (假负例)', value: cm.FN ?? 0 },
  ]
})

// ---- Error cases table ----
const errorColumns = [
  { title: '序号', dataIndex: 'index', width: 70 },
  { title: '内容', dataIndex: 'content', ellipsis: true },
  { title: '期望结果', dataIndex: 'expected', width: 100 },
  { title: '实际结果', dataIndex: 'actual', width: 100 },
  { title: '期望文案标签', dataIndex: 'expected_text_label', width: 120 },
  { title: '实际文案标签', dataIndex: 'actual_text_label', width: 120 },
  { title: '期望图片标签', dataIndex: 'expected_image_label', width: 120 },
  { title: '实际图片标签', dataIndex: 'actual_image_label', width: 120 },
]

// ---- Helpers ----
function statusColor(s: string) {
  return { completed: 'green', failed: 'red', running: 'blue', pending: 'default' }[s] || 'default'
}

function formatPct(v: number | null | undefined): string {
  if (v == null) return '-'
  return (v * 100).toFixed(1)
}

// ---- Upload ----
async function handleBeforeUpload(file: File) {
  if (!file.name.endsWith('.xlsx')) {
    message.error('仅支持 .xlsx 格式的文件')
    return false
  }

  uploading.value = true
  // Reset state
  uploadedSuite.value = null
  testRecordId.value = null
  report.value = null
  selectedRuleIds.value = []
  stopPolling()

  const formData = new FormData()
  formData.append('file', file)

  try {
    const { data } = await apiClient.post('/admin/test-suites/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    uploadedSuite.value = data
    message.success(`测试集上传成功，共 ${data.total_cases} 条用例`)
    loadRules()
  } catch (e: any) {
    const detail = e.response?.data?.detail || '上传失败'
    message.error(detail)
  } finally {
    uploading.value = false
  }
  return false // prevent default upload behavior
}

// ---- Load rules ----
async function loadRules() {
  rulesLoading.value = true
  try {
    const { data } = await apiClient.get('/admin/rules')
    ruleOptions.value = data.map((r: any) => ({
      label: `${r.name} (${r.type})`,
      value: r.id,
    }))
  } catch {
    message.error('加载规则列表失败')
  } finally {
    rulesLoading.value = false
  }
}

// ---- Start test ----
async function startTest() {
  if (!uploadedSuite.value) return
  starting.value = true
  report.value = null
  testRecordId.value = null
  stopPolling()

  try {
    const { data } = await apiClient.post(
      `/admin/test-suites/${uploadedSuite.value.id}/run`,
      { rule_ids: selectedRuleIds.value }
    )
    testRecordId.value = data.test_record_id
    progress.value = { current: 0, total: uploadedSuite.value.total_cases, statusText: 'pending' }
    message.success('测试已启动')
    startPolling()
  } catch (e: any) {
    const detail = e.response?.data?.detail || '启动测试失败'
    message.error(detail)
  } finally {
    starting.value = false
  }
}

// ---- Polling progress ----
function startPolling() {
  stopPolling()
  pollTimer = setInterval(pollProgress, 2000)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function pollProgress() {
  if (!uploadedSuite.value) return
  try {
    const { data } = await apiClient.get(`/admin/test-suites/${uploadedSuite.value.id}/progress`)
    progress.value = {
      current: data.progress_current,
      total: data.progress_total,
      statusText: data.status,
    }
    if (data.status === 'completed' || data.status === 'failed') {
      stopPolling()
      if (data.status === 'completed') {
        loadReport()
      }
    }
  } catch {
    // Silently ignore polling errors
  }
}

// ---- Load report ----
async function loadReport() {
  if (!uploadedSuite.value) return
  try {
    const { data } = await apiClient.get(`/admin/test-suites/${uploadedSuite.value.id}/report`)
    report.value = data
  } catch {
    message.error('加载测试报告失败')
  }
}

// ---- Export ----
async function handleExport() {
  if (!uploadedSuite.value) return
  exporting.value = true
  try {
    const { data } = await apiClient.post(`/admin/test-suites/${uploadedSuite.value.id}/export`)
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `test-report-${new Date().toISOString().slice(0, 10)}.json`
    a.click()
    URL.revokeObjectURL(url)
    message.success('报告已导出')
  } catch {
    message.error('导出失败')
  } finally {
    exporting.value = false
  }
}

// ---- Cleanup ----
onBeforeUnmount(() => {
  stopPolling()
})
</script>
