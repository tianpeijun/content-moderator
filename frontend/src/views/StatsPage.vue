<template>
  <div>
    <!-- Shared Date Range Picker -->
    <a-card style="margin-bottom: 16px">
      <a-space>
        <span>日期范围：</span>
        <a-range-picker
          v-model:value="sharedDateRange"
          :placeholder="['开始日期', '结束日期']"
          @change="onSharedDateChange"
        />
      </a-space>
    </a-card>

    <!-- Volume Stats -->
    <a-card title="审核量趋势" style="margin-bottom: 16px">
      <template #extra>
        <a-radio-group v-model:value="volumeGranularity" button-style="solid" size="small" @change="fetchVolume">
          <a-radio-button value="day">按天</a-radio-button>
          <a-radio-button value="week">按周</a-radio-button>
          <a-radio-button value="month">按月</a-radio-button>
        </a-radio-group>
      </template>
      <a-table
        :columns="volumeColumns"
        :dataSource="volumeData"
        :loading="volumeLoading"
        rowKey="period"
        :pagination="false"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'pass_count'">
            <a-tag color="green">{{ record.pass_count }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'reject_count'">
            <a-tag color="red">{{ record.reject_count }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'review_count'">
            <a-tag color="orange">{{ record.review_count }}</a-tag>
          </template>
          <template v-else-if="column.dataIndex === 'flag_count'">
            <a-tag color="blue">{{ record.flag_count }}</a-tag>
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Rule Hits Stats -->
    <a-card title="规则命中率统计" style="margin-bottom: 16px">
      <template #extra>
        <a-statistic title="审核总量" :value="ruleHitsTotalCount" style="display: inline-block" />
      </template>
      <a-table
        :columns="ruleHitsColumns"
        :dataSource="ruleHitsData"
        :loading="ruleHitsLoading"
        rowKey="rule_id"
        :pagination="false"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'hit_rate'">
            {{ (record.hit_rate * 100).toFixed(2) }}%
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Cost Stats -->
    <a-card title="模型调用成本统计" style="margin-bottom: 16px">
      <template #extra>
        <a-statistic title="总成本" :value="costTotal" prefix="$" :precision="4" style="display: inline-block" />
      </template>
      <a-table
        :columns="costColumns"
        :dataSource="costData"
        :loading="costLoading"
        rowKey="_key"
        :pagination="false"
        size="small"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'estimated_cost'">
            ${{ record.estimated_cost.toFixed(4) }}
          </template>
        </template>
      </a-table>
    </a-card>

    <!-- Text Label Distribution -->
    <a-card title="文案标签分布" style="margin-bottom: 16px">
      <template #extra>
        <a-statistic title="总数" :value="textLabelTotal" style="display: inline-block" />
      </template>
      <a-table
        :columns="textLabelColumns"
        :dataSource="textLabelData"
        :loading="textLabelLoading"
        rowKey="label"
        :pagination="false"
        size="small"
      />
    </a-card>

    <!-- Image Label Distribution -->
    <a-card title="图片标签分布" style="margin-bottom: 16px">
      <template #extra>
        <a-statistic title="总数" :value="imageLabelTotal" style="display: inline-block" />
      </template>
      <a-table
        :columns="imageLabelColumns"
        :dataSource="imageLabelData"
        :loading="imageLabelLoading"
        rowKey="label"
        :pagination="false"
        size="small"
      />
    </a-card>

    <!-- Language Distribution -->
    <a-card title="语言分布">
      <template #extra>
        <a-statistic title="总数" :value="languageTotal" style="display: inline-block" />
      </template>
      <a-table
        :columns="languageColumns"
        :dataSource="languageData"
        :loading="languageLoading"
        rowKey="language"
        :pagination="false"
        size="small"
      />
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import type { Dayjs } from 'dayjs'
import apiClient from '../api/client'

// ---- Types ----
interface VolumeDataPoint {
  period: string
  total: number
  pass_count: number
  reject_count: number
  review_count: number
  flag_count: number
}

interface RuleHitItem {
  rule_id: string
  rule_name: string
  hit_count: number
  hit_rate: number
}

interface CostDataPoint {
  period: string
  model_id: string
  call_count: number
  estimated_cost: number
  _key?: string
}

interface LabelDistributionItem {
  label: string
  display_name: string
  count: number
}

interface LanguageDistributionItem {
  language: string
  count: number
}

// ---- Shared Date Range ----
const sharedDateRange = ref<[Dayjs, Dayjs] | null>(null)

function getDateParams(): Record<string, string> {
  const params: Record<string, string> = {}
  if (sharedDateRange.value && sharedDateRange.value[0] && sharedDateRange.value[1]) {
    params.start_date = sharedDateRange.value[0].format('YYYY-MM-DD')
    params.end_date = sharedDateRange.value[1].format('YYYY-MM-DD')
  }
  return params
}

function onSharedDateChange() {
  fetchVolume()
  fetchRuleHits()
  fetchCost()
  fetchTextLabels()
  fetchImageLabels()
  fetchLanguages()
}

// ---- Volume Stats ----
const volumeGranularity = ref('day')
const volumeData = ref<VolumeDataPoint[]>([])
const volumeLoading = ref(false)

const volumeColumns = [
  { title: '时间段', dataIndex: 'period', width: 180 },
  { title: '总量', dataIndex: 'total', width: 100 },
  { title: '通过', dataIndex: 'pass_count', width: 100 },
  { title: '拒绝', dataIndex: 'reject_count', width: 100 },
  { title: '人工复审', dataIndex: 'review_count', width: 100 },
  { title: '标记', dataIndex: 'flag_count', width: 100 },
]

async function fetchVolume() {
  volumeLoading.value = true
  try {
    const params: Record<string, string> = { granularity: volumeGranularity.value, ...getDateParams() }
    const { data } = await apiClient.get('/admin/stats/volume', { params })
    volumeData.value = data.data
  } catch {
    message.error('加载审核量趋势失败')
  } finally {
    volumeLoading.value = false
  }
}

// ---- Rule Hits Stats ----
const ruleHitsData = ref<RuleHitItem[]>([])
const ruleHitsLoading = ref(false)
const ruleHitsTotalCount = ref(0)

const ruleHitsColumns = [
  { title: '规则名称', dataIndex: 'rule_name', width: 200 },
  { title: '命中次数', dataIndex: 'hit_count', width: 120 },
  { title: '命中率', dataIndex: 'hit_rate', width: 120 },
]

async function fetchRuleHits() {
  ruleHitsLoading.value = true
  try {
    const { data } = await apiClient.get('/admin/stats/rule-hits', { params: getDateParams() })
    ruleHitsTotalCount.value = data.total_moderation_count
    ruleHitsData.value = data.rules
  } catch {
    message.error('加载规则命中率失败')
  } finally {
    ruleHitsLoading.value = false
  }
}

// ---- Cost Stats ----
const costData = ref<CostDataPoint[]>([])
const costLoading = ref(false)
const costTotal = ref(0)

const costColumns = [
  { title: '时间段', dataIndex: 'period', width: 180 },
  { title: '模型ID', dataIndex: 'model_id', width: 200 },
  { title: '调用次数', dataIndex: 'call_count', width: 120 },
  { title: '估算成本', dataIndex: 'estimated_cost', width: 140 },
]

async function fetchCost() {
  costLoading.value = true
  try {
    const { data } = await apiClient.get('/admin/stats/cost', { params: getDateParams() })
    costTotal.value = data.total_cost
    costData.value = data.data.map((item: CostDataPoint, idx: number) => ({
      ...item,
      _key: `${item.period}-${item.model_id}-${idx}`,
    }))
  } catch {
    message.error('加载成本统计失败')
  } finally {
    costLoading.value = false
  }
}

// ---- Text Label Distribution ----
const textLabelData = ref<LabelDistributionItem[]>([])
const textLabelLoading = ref(false)
const textLabelTotal = ref(0)

const textLabelColumns = [
  { title: '标签', dataIndex: 'label', width: 160 },
  { title: '显示名称', dataIndex: 'display_name', width: 200 },
  { title: '数量', dataIndex: 'count', width: 120, sorter: (a: LabelDistributionItem, b: LabelDistributionItem) => a.count - b.count, defaultSortOrder: 'descend' as const },
]

async function fetchTextLabels() {
  textLabelLoading.value = true
  try {
    const { data } = await apiClient.get('/admin/stats/text-labels', { params: getDateParams() })
    textLabelData.value = data.items
    textLabelTotal.value = data.total
  } catch {
    message.error('加载文案标签分布失败')
  } finally {
    textLabelLoading.value = false
  }
}

// ---- Image Label Distribution ----
const imageLabelData = ref<LabelDistributionItem[]>([])
const imageLabelLoading = ref(false)
const imageLabelTotal = ref(0)

const imageLabelColumns = [
  { title: '标签', dataIndex: 'label', width: 160 },
  { title: '显示名称', dataIndex: 'display_name', width: 200 },
  { title: '数量', dataIndex: 'count', width: 120, sorter: (a: LabelDistributionItem, b: LabelDistributionItem) => a.count - b.count, defaultSortOrder: 'descend' as const },
]

async function fetchImageLabels() {
  imageLabelLoading.value = true
  try {
    const { data } = await apiClient.get('/admin/stats/image-labels', { params: getDateParams() })
    imageLabelData.value = data.items
    imageLabelTotal.value = data.total
  } catch {
    message.error('加载图片标签分布失败')
  } finally {
    imageLabelLoading.value = false
  }
}

// ---- Language Distribution ----
const languageData = ref<LanguageDistributionItem[]>([])
const languageLoading = ref(false)
const languageTotal = ref(0)

const languageColumns = [
  { title: '语言', dataIndex: 'language', width: 120 },
  { title: '数量', dataIndex: 'count', width: 120, sorter: (a: LanguageDistributionItem, b: LanguageDistributionItem) => a.count - b.count, defaultSortOrder: 'descend' as const },
]

async function fetchLanguages() {
  languageLoading.value = true
  try {
    const { data } = await apiClient.get('/admin/stats/languages', { params: getDateParams() })
    languageData.value = data.items
    languageTotal.value = data.total
  } catch {
    message.error('加载语言分布失败')
  } finally {
    languageLoading.value = false
  }
}

// ---- Init ----
onMounted(() => {
  fetchVolume()
  fetchRuleHits()
  fetchCost()
  fetchTextLabels()
  fetchImageLabels()
  fetchLanguages()
})
</script>
