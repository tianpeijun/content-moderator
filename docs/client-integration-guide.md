# 客户端集成与性能优化指南

本文档帮助客户端应用以最低延迟调用内容审核 API,以及排查常见问题。

## 推荐端点(HTTP API v2 — 延迟降低 50%)

```
POST https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com/api/v1/moderate
```

> 实测 P50 延迟 366ms,预审命中场景 100% ≤ 500ms。2026-04-18 新增。

## 兼容端点(REST API v1 — 保留向后兼容)

```
POST https://YOUR_REST_API_ID.execute-api.us-east-1.amazonaws.com/prod/api/v1/moderate
```

> 功能等价,但延迟约为 HTTP API 的 2 倍。现有客户端如果在用这个端点,建议迁移到 HTTP API v2。

两个端点使用同一个 Lambda 后端、同一个 API Key、完全相同的请求/响应格式,**迁移只需改 URL**。

## 请求格式

```
Headers:
  X-API-Key: <your-api-key>
  Content-Type: application/json
Body:
  {
    "text": "待审核文本",
    "image_url": "可选,图片 URL",
    "business_type": "商品评论"
  }
```

响应示例:
```json
{
  "task_id": "b08fcb36-...",
  "status": "completed",
  "result": "pass",
  "text_label": "safe",
  "image_label": "none",
  "confidence": 0.95,
  "matched_rules": [],
  "degraded": false,
  "processing_time_ms": 516,
  "language": "zh"
}
```

## 性能最佳实践

### 1. 必做:复用 HTTPS 连接

**最大收益:每次请求 -200 ~ -500ms**

每次建立新 HTTPS 连接会经历 DNS 解析(~10ms)+ TCP 握手(~100ms)+ TLS 握手(~300ms),合计 400ms+。
复用现有连接可完全跳过这部分。

### Python — requests.Session

```python
import requests

# ❌ 差:每次新建连接
def moderate_bad(text):
    resp = requests.post(
        "https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com/api/v1/moderate",
        headers={"X-API-Key": "xxx"},
        json={"text": text, "business_type": "商品评论"},
    )
    return resp.json()

# ✅ 好:Session 自动复用连接 + connection pool
_session = requests.Session()
_session.headers.update({"X-API-Key": "xxx", "Content-Type": "application/json"})
# 可选:显式配置连接池
from requests.adapters import HTTPAdapter
_session.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=50))

def moderate_good(text):
    resp = _session.post(
        "https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com/api/v1/moderate",
        json={"text": text, "business_type": "商品评论"},
        timeout=10,
    )
    return resp.json()
```

### Python — httpx (异步 / HTTP/2)

```python
import httpx

# 全局 client,应用生命周期内只创建一次
_client = httpx.AsyncClient(
    base_url="https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com",
    headers={"X-API-Key": "xxx"},
    http2=True,  # 需要 pip install 'httpx[http2]'
    limits=httpx.Limits(max_connections=50, max_keepalive_connections=20),
    timeout=10.0,
)

async def moderate(text: str) -> dict:
    resp = await _client.post("/api/v1/moderate", json={
        "text": text, "business_type": "商品评论",
    })
    return resp.json()

# 应用关闭时记得清理
async def shutdown():
    await _client.aclose()
```

### Node.js — 全局 Agent + keep-alive

```javascript
const https = require('https');
const axios = require('axios');

// 全局 agent 开启 keep-alive
const agent = new https.Agent({
  keepAlive: true,
  keepAliveMsecs: 30000,
  maxSockets: 50,
  maxFreeSockets: 10,
});

const client = axios.create({
  baseURL: "https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com",
  headers: { 'X-API-Key': 'xxx' },
  httpsAgent: agent,
  timeout: 10000,
});

async function moderate(text) {
  const { data } = await client.post('/api/v1/moderate', {
    text,
    business_type: '商品评论',
  });
  return data;
}
```

### Java — OkHttp 单例

```java
private static final OkHttpClient client = new OkHttpClient.Builder()
    .connectionPool(new ConnectionPool(10, 5, TimeUnit.MINUTES))
    .readTimeout(10, TimeUnit.SECONDS)
    .build();

public static ModerationResponse moderate(String text) throws IOException {
    RequestBody body = RequestBody.create(
        "{\"text\":\"" + escape(text) + "\",\"business_type\":\"商品评论\"}",
        MediaType.parse("application/json"));
    Request req = new Request.Builder()
        .url("https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com/api/v1/moderate")
        .header("X-API-Key", "xxx")
        .post(body)
        .build();
    try (Response resp = client.newCall(req).execute()) {
        return parse(resp.body().string());
    }
}
```

### Go — 全局 http.Client

```go
var httpClient = &http.Client{
    Transport: &http.Transport{
        MaxIdleConns:        100,
        MaxIdleConnsPerHost: 50,
        IdleConnTimeout:     90 * time.Second,
    },
    Timeout: 10 * time.Second,
}

func Moderate(text string) (*Response, error) {
    payload, _ := json.Marshal(map[string]string{
        "text": text, "business_type": "商品评论",
    })
    req, _ := http.NewRequest("POST",
        "https://YOUR_HTTP_API_ID.execute-api.us-east-1.amazonaws.com/api/v1/moderate",
        bytes.NewReader(payload))
    req.Header.Set("X-API-Key", "xxx")
    req.Header.Set("Content-Type", "application/json")
    resp, err := httpClient.Do(req)
    if err != nil { return nil, err }
    defer resp.Body.Close()
    var r Response
    json.NewDecoder(resp.Body).Decode(&r)
    return &r, nil
}
```

### 2. 推荐:同区域部署

- API 部署在 **us-east-1**
- 客户端应用部署在同区域可降低 **RTT 50-100ms**
- 跨区域调用需增加 **100-200ms**(亚太 → 美东 约 180ms)

### 3. 推荐:设置合理超时

- 平均响应时间:纯文本 **0.8-1.5s**,图文混合 **3-6s**
- 建议超时:**10 秒**(覆盖 P99)
- 超时重试:最多重试 1 次,加指数退避(1s, 2s)

### 4. 批量场景:并发控制

HTTP API v2 默认账号级限流 10,000 req/s(burst 5,000),实际受 Lambda 并发限制(默认 1,000)约束。批量场景建议:

- **并发数 ≤ 50**(避免 Lambda 瞬时并发打满)
- **串行处理** = QPS ~ 1 / 平均延迟(约 2-3 req/s per connection)
- **并发处理** = 用连接池,50 并发可达 50-100 req/s
- **批量测试** 请使用管理后台的"批量测试"页面(走 SQS 异步处理,不受单客户端限流约束)

## 预审命中场景

某些内容会触发预审过滤(关键词/正则命中),跳过 AI 模型调用:

- 响应中 `matched_rules[0].rule_id == "pre_filter"`
- **Lambda 内部延迟 <50ms**
- **HTTP API v2 端到端延迟 P50 362ms / P95 446ms**(复用连接)

当前预审覆盖:
- 隐私泄露:中国手机号 / 身份证 / 邮箱 / 国际电话 / 微信QQ社交ID / 日韩电话
- 违法交易:毒品 / 武器交易关键词(中英)
- 仇恨言论:常见歧视词(中英)
- 虚假宣传:FDA 伪认证 / 包治 / 快速减肥
- 辱骂:中英文常见脏话
- 垃圾广告:推广链接 / 扫码领券 / 加V等

## 延迟 SLA(实测数据,2026-04-18)

> **前提**:使用 HTTP API v2 端点 + 客户端复用 HTTPS 连接 + 同区域部署 + Lambda 已热启动

### 预审命中场景(约 60-68% 请求,取决于输入分布)

| 指标 | 值 |
|------|-----|
| P50 延迟 | **362ms** ✅ |
| P95 延迟 | 446ms |
| **≤ 500ms 达成率** | **100%** ✅ |

### 模型路径场景(约 30-40% 请求)

| 指标 | 值 |
|------|-----|
| P50 延迟 | 982ms |
| P95 延迟 | 1143ms |
| ≤ 1000ms 达成率 | 75% |
| ≤ 1500ms 达成率 | 100% |

### 综合(实际生产流量)

假设 65% 预审命中 + 35% 走模型:
- **加权 P50 ≈ 450ms**
- 加权 P95 ≈ 1100ms
- ≤ 500ms 达成率约 **65%**
- ≤ 1000ms 达成率约 **90%**

### 为什么 100% ≤500ms 不可达?

走 Qwen3 模型的请求至少需要:
- Qwen3 推理 + Bedrock 网络 ~600ms(硬下限)
- + Lambda + HTTP API + 客户端 RTT ~200-400ms
- = **最快 ~900ms**

无法通过架构优化压到 500ms 以下。只能:
1. 扩充预审规则让更多请求走快路径(目标命中率 80%+)
2. 加 Provisioned Concurrency 消除冷启动(不影响模型路径)
3. 换更快的模型 — 但 Nova Lite(80%)/ Nova 2 Lite(70%)准确率不满足要求

## 错误处理

| HTTP | 含义 | 客户端处理 |
|------|------|------|
| 200 | 审核成功 | 读取 `result` 字段决定业务动作 |
| 400 | 请求参数错误 / 图片 URL 无效 | 检查 `detail` 字段,修正请求 |
| 403 | API Key 无效 / 缺失 | 检查 `X-API-Key` header |
| 429 | 超过限流 | 指数退避重试 |
| 500 | 服务内部错误 | 重试 1 次,仍失败则告警 |
| 502 | 图片源不可达(外部 URL 返回 5xx 或超时) | 检查 image_url 是否可公开访问 |
| 504 | HTTP API Gateway 超时(> 29s) | 图片审核可能超时,考虑异步模式 |

## 降级响应

当所有 AI 模型都失败时,API 返回:

```json
{
  "result": "review",   // 默认人工审核
  "degraded": true,     // 降级标志
  "confidence": 0.0,
  ...
}
```

业务方应:
- 优先走人工审核队列
- 监控 `degraded=true` 的比例,超过阈值告警
