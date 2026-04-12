<template>
  <div>
    <a-row :gutter="24">
      <!-- Left panel: Rule selector + test inputs -->
      <a-col :span="10">
        <a-card title="规则选择与测试内容" :bordered="false">
          <a-form layout="vertical">
            <a-form-item label="选择规则">
              <a-select
                v-model:value="selectedRuleIds"
                mode="multiple"
                placeholder="请选择要组合的规则"
                style="width: 100%"
                :loading="rulesLoading"
                optionFilterProp="label"
                @change="onInputChange"
              >
                <a-select-option
                  v-for="rule in rules"
                  :key="rule.id"
                  :value="rule.id"
                  :label="rule.name"
                >
                  {{ rule.name }}
                  <a-tag :color="actionColor(rule.action)" style="margin-left: 8px">{{ rule.action }}</a-tag>
                  <span style="color: #999; margin-left: 4px">P{{ rule.priority }}</span>
                </a-select-option>
              </a-select>
            </a-form-item>

            <a-form-item label="测试文本">
              <a-textarea
                v-model:value="testText"
                placeholder="请输入要审核的评论文本"
                :rows="4"
                @change="onInputChange"
              />
            </a-form-item>

            <a-form-item label="图片 URL">
              <a-input
                v-model:value="testImageUrl"
                placeholder="图片 URL 或 S3 路径（可选）"
                @change="onInputChange"
              />
            </a-form-item>

            <a-form-item>
              <a-button
                type="primary"
                :loading="testing"
                :disabled="selectedRuleIds.length === 0 || (!testText && !testImageUrl)"
                @click="runTest"
              >
                执行测试
              </a-button>
            </a-form-item>
          </a-form>

          <!-- Test result card -->
          <a-card v-if="testResult" title="测试结果" size="small" style="margin-top: 16px">
            <a-descriptions :column="1" size="small" bordered>
              <a-descriptions-item label="审核结果">
                <a-tag :color="resultColor(testResult.result)">{{ testResult.result }}</a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="置信度">
                {{ testResult.confidence != null ? (testResult.confidence * 100).toFixed(1) + '%' : '-' }}
              </a-descriptions-item>
              <a-descriptions-item label="命中规则">
                <template v-if="testResult.matched_rules && testResult.matched_rules.length">
                  <a-tag v-for="mr in testResult.matched_rules" :key="mr.rule_id" color="orange">
                    {{ mr.rule_name }} ({{ mr.action }})
                  </a-tag>
                </template>
                <span v-else>无</span>
              </a-descriptions-item>
              <a-descriptions-item label="降级处理">
                <a-tag :color="testResult.degraded ? 'red' : 'green'">
                  {{ testResult.degraded ? '是' : '否' }}
                </a-tag>
              </a-descriptions-item>
              <a-descriptions-item label="处理耗时">
                {{ testResult.processing_time_ms != null ? testResult.processing_time_ms + ' ms' : '-' }}
              </a-descriptions-item>
            </a-descriptions>
          </a-card>
        </a-card>
      </a-col>

      <!-- Right panel: Prompt preview -->
      <a-col :span="14">
        <a-card title="最终提示词预览" :bordered="false">
          <a-spin :spinning="previewLoading">
            <div v-if="previewPrompt" class="prompt-preview">
              <pre style="white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.6; max-height: 600px; overflow: auto; background: #fafafa; padding: 16px; border-radius: 6px">{{ previewPrompt }}</pre>
            </div>
            <a-empty v-else description="请选择规则以预览最终提示词" />
          </a-spin>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import apiClient from '../api/client'

// ---- Types ----
interface RuleOption {
  id: string
  name: string
  action: string
  priority: number
}

interface MatchedRule {
  rule_id: string
  rule_name: string
  action: string
}

interface TestResultData {
  task_id: string
  status: string
  result: string | null
  confidence: number | null
  matched_rules: MatchedRule[]
  degraded: boolean
  processing_time_ms: number | null
}

// ---- State ----
const rules = ref<RuleOption[]>([])
const rulesLoading = ref(false)
const selectedRuleIds = ref<string[]>([])
const testText = ref('')
const testImageUrl = ref('')
const previewPrompt = ref('')
const previewLoading = ref(false)
const testing = ref(false)
const testResult = ref<TestResultData | null>(null)

let previewTimer: ReturnType<typeof setTimeout> | null = null

// ---- Helpers ----
function actionColor(action: string) {
  return { reject: 'red', review: 'orange', flag: 'blue' }[action] || 'default'
}

function resultColor(result: string | null) {
  if (!result) return 'default'
  return { pass: 'green', reject: 'red', review: 'orange', flag: 'blue' }[result] || 'default'
}

// ---- Load rules ----
async function fetchRules() {
  rulesLoading.value = true
  try {
    const { data } = await apiClient.get('/admin/rules', { params: { enabled: true } })
    rules.value = data.map((r: Record<string, unknown>) => ({
      id: r.id as string,
      name: r.name as string,
      action: r.action as string,
      priority: r.priority as number,
    }))
  } catch {
    message.error('加载规则列表失败')
  } finally {
    rulesLoading.value = false
  }
}

// ---- Preview prompt (debounced) ----
function onInputChange() {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(fetchPreview, 500)
}

async function fetchPreview() {
  if (selectedRuleIds.value.length === 0) {
    previewPrompt.value = ''
    return
  }
  previewLoading.value = true
  try {
    const { data } = await apiClient.post('/admin/prompt/preview', {
      rule_ids: selectedRuleIds.value,
      text: testText.value || null,
      image_url: testImageUrl.value || null,
    })
    previewPrompt.value = data.prompt
  } catch {
    message.error('预览提示词失败')
  } finally {
    previewLoading.value = false
  }
}

// ---- Run test ----
async function runTest() {
  testing.value = true
  testResult.value = null
  try {
    const { data } = await apiClient.post('/admin/prompt/test', {
      rule_ids: selectedRuleIds.value,
      text: testText.value || null,
      image_url: testImageUrl.value || null,
    })
    testResult.value = data
    message.success('测试完成')
  } catch {
    message.error('测试执行失败')
  } finally {
    testing.value = false
  }
}

// ---- Init ----
onMounted(() => {
  fetchRules()
})
</script>
