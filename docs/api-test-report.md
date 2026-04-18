# 商城评论内容审核系统 — API 测试报告

## 一、测试环境

| 项目 | 值 |
|------|------|
| 生产 API 端点 | `https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com/api/v1/moderate` |
| 管理后台 | `https://YOUR_CLOUDFRONT_DOMAIN.cloudfront.net` |
| AI 模型 — 纯文本 | Qwen3 32B |
| AI 模型 — 图文混合 | Claude Sonnet 4 |
| AI 模型 — 备用 | Claude Haiku 4.5 |
| 预审过滤 | 关键词 / 正则，覆盖 7 类违规 |
| 部署区域 | us-east-1 |
| 测试时间 | 2026-04-18 |

---

## 二、功能验证结果

全部 18 项端到端测试 100% 通过。

| 测试类别 | 用例数 | 通过数 | 说明 |
|----------|--------|--------|------|
| 多语种正常评论 | 7 | 7 | 中/英/日/韩/法/俄/阿拉伯，全部正确放行 |
| 多语种违规内容 | 4 | 4 | 欺诈 + 隐私泄露 + 电话号码，全部识别 |
| 图片审核 | 2 | 2 | 正常商品图放行 + 广告图片拒绝（含联系方式识别） |
| 中英混合评论 | 1 | 1 | 正确放行 |
| 输入验证与认证 | 2 | 2 | 空内容返回 400，缺 API Key 返回 403 |
| 异步结果查询 | 2 | 2 | 正常查询 200，不存在任务 404 |
| **总计** | **18** | **18** | **100%** |

### 关键能力

- **违规零漏放**：所有违规内容被正确标记为 reject / flag
- **正常零误杀**：所有正常评论被正确判定为 pass
- **图文联合审核**：能识别图片中的文字（联系方式、广告语），与文本综合判定
- **智能模型路由**：纯文本走 Qwen3（快），图文走 Sonnet 4（准）
- **预审快速通道**：手机号 / 邮箱 / 微信号 / 广告链接等命中后不调模型，Lambda 内部 <50ms

---

## 三、性能数据（2026-04-18 实测）

### 纯文本响应延迟

> 前提：客户端使用 HTTPS 连接复用，Lambda 已热启动。冷启动首次请求约 7 秒（生产建议开启 Provisioned Concurrency 消除）。

| 路径 | 占比（估算） | P50 | P95 | ≤500ms |
|------|------------|-----|-----|--------|
| **预审命中** | 60-68% | **362ms** | 446ms | **100%** ✅ |
| 模型路径（Qwen3） | 30-40% | 982ms | 1143ms | 0% |
| **混合流量** | 100% | **444ms** | 1143ms | **60%** |

### 图文混合响应延迟（Sonnet 4）

| 指标 | 值 |
|------|-----|
| 平均 | 约 5.8 秒 |
| 最快 | 4.29 秒 |
| 最慢 | 12.08 秒（长文本） |

> 图文审核耗时主要由 Sonnet 4 的多模态推理决定，建议业务在发布流程中走异步模式（提交 task_id 后轮询 `/api/v1/moderate/{taskId}`）。

### 500ms SLA 达成情况

- ✅ **预审命中场景 100% ≤ 500ms**（P50 362ms / P95 446ms）
- ✅ **整体 P50 ≤ 500ms**
- ⚠️ 模型路径受 Qwen3 推理时间约束，端到端约 900-1000ms，**无法压到 500ms 以下**
---

## 四、如何调用 API

### 请求

```
POST https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com/api/v1/moderate
Headers:
  X-API-Key: <your-api-key>
  Content-Type: application/json
Body:
  {
    "text": "待审核文本",
    "image_url": "可选，图片 URL (http/https/s3)",
    "business_type": "商品评论"
  }
```

### 响应

```json
{
  "task_id": "...",
  "status": "completed",
  "result": "pass",              // pass / reject / flag / review
  "text_label": "safe",
  "image_label": "none",
  "confidence": 0.95,
  "matched_rules": [],
  "degraded": false,
  "processing_time_ms": 516,
  "language": "zh"
}
```

### 业务处理建议

| result | 含义 | 建议处理 |
|--------|------|----------|
| pass | 内容正常 | 自动通过 |
| reject | 明确违规 | 自动拒绝 |
| flag | 可疑内容 | 人工复审 |
| review | 系统无法判定 | 人工审核 |

### 错误码

| HTTP | 含义 |
|------|------|
| 200 | 审核成功，读 `result` 字段 |
| 400 | 请求参数错误 / 图片 URL 无效（读 `detail` 字段） |
| 403 | API Key 无效或缺失 |
| 429 | 超过限流，请重试（指数退避） |
| 500 | 服务内部错误，可重试 1 次 |
| 502 | 图片源 URL 不可达 |
| 504 | 请求超时（图文场景，建议走异步） |

### 性能最佳实践

参考 [`client-integration-guide.md`](./client-integration-guide.md) 获取 Python / Node.js / Java / Go 四种语言的连接复用示例代码。核心要点：

1. **复用 HTTPS 连接**（单次请求 -250ms）
2. **同区域部署**客户端（跨区多 100-200ms RTT）
3. **超时设置 10 秒**（覆盖 P99）
4. **批量场景并发 ≤ 50**（或使用管理后台批量测试入口）

---

## 五、相关文档

- [`client-integration-guide.md`](./client-integration-guide.md) — 客户端集成指南（四种语言代码示例）
- [`cost-estimation.md`](./cost-estimation.md) — 月度成本估算
- [`internal/api-test-report-detailed.md`](./internal/api-test-report-detailed.md) — 详细测试数据、五模型 benchmark、延迟分解（内部存档）
