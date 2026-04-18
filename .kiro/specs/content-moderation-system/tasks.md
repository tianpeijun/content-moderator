# 实施计划：商城评论内容审核系统

## 概述

基于 Python FastAPI 后端 + Vue 3 前端 + AWS CDK 基础设施的内容审核系统实施计划。按照数据层 → 核心引擎 → API 层 → 前端 → 基础设施的顺序逐步构建，确保每一步都可验证。

## 任务

- [x] 1. 项目初始化与数据模型
  - [x] 1.1 初始化后端项目结构
    - 创建 Python 项目，配置 FastAPI、SQLAlchemy、Pydantic 依赖
    - 创建目录结构：`backend/app/{models,schemas,api,services,core}`
    - 配置 `pyproject.toml` 或 `requirements.txt`
    - _需求: 1.1, 1.2, 1.3_

  - [x] 1.2 创建 PostgreSQL 数据模型
    - 使用 SQLAlchemy 定义 rules、rule_versions、model_config、test_suites、test_records、moderation_logs 表模型
    - 创建数据库迁移脚本（Alembic）
    - 定义索引：idx_logs_result_created、idx_logs_business_type_created、idx_logs_task_id
    - _需求: 3.2, 5.4, 6.1_

  - [x] 1.3 创建 Pydantic 请求/响应 Schema
    - 定义审核请求 ModerationRequest（text、image_url、business_type、callback_url）
    - 定义审核响应 ModerationResponse（task_id、status、result、confidence、matched_rules、degraded、processing_time_ms）
    - 定义规则 CRUD Schema（RuleCreate、RuleUpdate、RuleResponse）
    - 定义测试集、测试记录、模型配置等 Schema
    - _需求: 1.1, 1.5, 3.2_

- [x] 2. 核心引擎实现
  - [x] 2.1 实现提示词模板解析器（RuleEngine.render_template）
    - 实现 {{variable}} 占位符替换逻辑
    - 未定义变量替换为空字符串并记录警告日志
    - _需求: 12.1, 12.2, 12.3_

  - [ ]* 2.2 编写提示词模板解析功能测试
    - **Property 6: 模板变量替换往返一致性** — 验证替换后不包含 {{...}} 占位符
    - **Validates: 需求 12.1, 12.3**

  - [x] 2.3 实现规则加载与提示词组装（RuleEngine.get_active_rules / assemble_prompt）
    - 从 PostgreSQL 加载启用规则，支持按 business_type 筛选
    - 按优先级从高到低（数值从小到大）排序拼接规则提示词片段
    - _需求: 3.4, 3.5, 4.3, 12.4_

  - [ ]* 2.4 编写规则加载与提示词组装功能测试
    - **Property 7: 规则提示词按优先级排序拼接** — 验证片段顺序与优先级一致
    - **Validates: 需求 12.4, 3.5, 4.3**

  - [x] 2.5 实现图片获取器（ImageFetcher）
    - 根据 URL 前缀路由：s3:// → AWS SDK，http(s):// → HTTP 请求
    - 其他前缀返回错误
    - _需求: 1.4_

  - [ ]* 2.6 编写图片获取器功能测试
    - **Property 1: 图片 URL 路由正确性** — 验证 s3://、http(s)://、无效前缀的路由行为
    - **Validates: 需求 1.4**

  - [x] 2.7 实现 AI 模型调用器（ModelInvoker）
    - 封装 Amazon Bedrock 调用（boto3 bedrock-runtime）
    - 实现 invoke_with_fallback：主模型失败 → 备用模型 → 默认结果
    - 失败/降级时标记 degraded=true
    - _需求: 1.6, 7.4_

  - [ ]* 2.8 编写模型调用器功能测试
    - 测试主模型成功、主模型失败降级到备用模型、全部失败返回默认结果
    - _需求: 1.6, 7.3_

- [x] 3. 检查点 — 核心引擎验证
  - 确保所有测试通过，如有疑问请向用户确认。

- [x] 4. 审核 API 实现
  - [x] 4.1 实现 API Key 认证中间件 
    - 从请求头提取 API Key 并验证
    - 无效或缺失返回 HTTP 401
    - _需求: 10.1, 1.7_

  - [x] 4.2 实现 POST /api/v1/moderate 端点
    - 输入验证：text 和 image_url 均为空时返回 400
    - 协调 RuleEngine → ImageFetcher → ModelInvoker 完成审核
    - 写入 moderation_logs 表
    - 返回审核结果 JSON
    - _需求: 1.1, 1.2, 1.3, 1.5, 5.4_

  - [ ]* 4.3 编写审核 API 输入验证功能测试
    - **Property 2: 审核请求输入验证** — 验证空内容拒绝、有效内容通过
    - **Validates: 需求 1.5**

  - [x] 4.4 实现 GET /api/v1/moderate/{taskId} 端点
    - 查询 moderation_logs 表返回任务状态和结果
    - taskId 不存在返回 404
    - _需求: 2.1, 2.2, 2.3_

- [x] 5. 管理后台 API 实现
  - [x] 5.1 实现 Cognito 认证中间件
    - 验证 Cognito JWT Token
    - Token 无效或过期返回 401
    - _需求: 10.2, 10.3_

  - [x] 5.2 实现规则 CRUD API
    - GET/POST/PUT/DELETE /api/admin/rules
    - 创建/更新时验证必填字段（name、type、prompt_template、action、priority）
    - 规则修改时自动保存版本历史到 rule_versions 表
    - GET /api/admin/rules/{id}/versions 查询版本历史
    - _需求: 3.1, 3.2, 3.3, 3.4, 3.6_

  - [ ]* 5.3 编写规则 CRUD 功能测试
    - **Property 3: 规则必填字段验证** — 验证缺少必填字段时拒绝请求
    - **Validates: 需求 3.2**

  - [x] 5.4 实现提示词预览与测试 API
    - POST /api/admin/prompt/preview — 组装并返回最终提示词
    - POST /api/admin/prompt/test — 调用 AI 模型执行测试审核
    - _需求: 4.1, 4.2_

  - [x] 5.5 实现审核日志 API
    - GET /api/admin/logs — 支持按时间范围、审核结果、业务类型、命中规则筛选，分页
    - GET /api/admin/logs/{id} — 日志详情（原始内容、最终提示词、模型响应）
    - POST /api/admin/logs/export — 导出日志文件
    - _需求: 5.1, 5.2, 5.3_

  - [x] 5.6 实现批量测试 API
    - POST /api/admin/test-suites/upload — 上传并解析 .xlsx 文件，验证格式
    - POST /api/admin/test-suites/{id}/run — 发送 SQS 消息启动批量测试
    - GET /api/admin/test-suites/{id}/progress — 查询测试进度
    - GET /api/admin/test-suites/{id}/report — 获取测试报告
    - POST /api/admin/test-suites/{id}/export — 导出测试报告为 .xlsx
    - GET /api/admin/test-records — 历史测试记录
    - POST /api/admin/test-records/compare — 测试记录对比
    - _需求: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [ ]* 5.7 编写批量测试格式验证功能测试
    - **Property 4: Excel 测试集格式验证** — 验证必要列和期望结果值合法性
    - **Validates: 需求 6.1, 6.2**

  - [x] 5.8 实现模型配置 API
    - GET/PUT /api/admin/model-config — 模型配置读取和更新
    - 支持主模型、备用模型、降级策略、参数配置
    - _需求: 7.1, 7.2, 7.3, 7.4, 7.5_

  - [x] 5.9 实现数据统计 API
    - GET /api/admin/stats/volume — 审核量趋势（按天/周/月）
    - GET /api/admin/stats/rule-hits — 规则命中率
    - GET /api/admin/stats/cost — 模型调用成本统计
    - _需求: 8.1, 8.2, 8.3_

- [x] 6. 批量测试 Worker 实现
  - [x] 6.1 实现 SQS 消费者（BatchTestWorker）
    - 从 SQS 接收批量测试任务消息
    - 逐条调用审核流程，更新 test_records 进度
    - 单条失败不影响整体，记录失败原因继续执行
    - _需求: 6.3, 6.7_

  - [x] 6.2 实现测试指标计算（calculate_metrics）
    - 计算混淆矩阵（TP/FP/TN/FN）、准确率、召回率、F1 分数
    - 生成错误案例列表和规则命中分布
    - _需求: 6.4_

  - [ ]* 6.3 编写测试指标计算功能测试
    - **Property 5: 测试指标计算数学正确性** — 验证 TP+FP+TN+FN=总数，准确率/召回率/F1 公式正确
    - **Validates: 需求 6.4**

- [x] 7. 检查点 — 后端 API 完整性验证
  - 确保所有测试通过，如有疑问请向用户确认。

- [x] 8. 前端管理后台实现
  - [x] 8.1 初始化 Vue 3 项目
    - 使用 Vite 创建 Vue 3 + TypeScript 项目
    - 安装 Ant Design Vue、axios、vue-router、pinia 
    - 配置路由、API 请求封装（axios 拦截器 + Cognito Token）
    - _需求: 10.2, 10.3_

  - [x] 8.2 实现规则管理页面
    - 规则列表（表格 + 筛选 + 分页）
    - 规则创建/编辑表单（名称、类型、业务类型、提示词模板编辑器、变量配置、动作、优先级、启用状态）
    - 规则版本历史查看
    - _需求: 3.1, 3.2, 3.3, 3.6_

  - [x] 8.3 实现提示词预览与测试页面
    - 规则组合选择器
    - 最终提示词实时预览展示
    - 在线测试：输入测试内容，调用 AI 返回审核结果
    - _需求: 4.1, 4.2_

  - [x] 8.4 实现审核日志页面
    - 日志列表（筛选：时间范围、审核结果、业务类型、命中规则 + 分页）
    - 日志详情抽屉（原始内容、提示词、模型响应）
    - 导出功能
    - _需求: 5.1, 5.2, 5.3_

  - [x] 8.5 实现批量测试页面
    - 上传 .xlsx 测试集（格式校验 + 错误提示）
    - 选择规则组合，启动测试
    - 实时进度展示（进度条 + 已完成数/总数）
    - 测试报告展示（准确率、召回率、F1、混淆矩阵、错误案例列表、规则命中分布）
    - 导出报告
    - _需求: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 8.6 实现测试记录与对比页面
    - 历史测试记录列表
    - 选择两条记录进行结果对比
    - _需求: 6.6_

  - [x] 8.7 实现模型配置页面
    - 模型选择（展示可用模型列表 + 参考成本）
    - 参数调整（temperature、max_tokens）
    - 降级策略配置（备用模型、默认审核结果）
    - _需求: 7.1, 7.2, 7.3, 7.5_

  - [x] 8.8 实现数据统计页面
    - 审核量趋势图表（按天/周/月切换）
    - 规则命中率统计图表
    - 模型调用成本统计图表
    - _需求: 8.1, 8.2, 8.3_

- [x] 9. 检查点 — 前端功能验证
  - 确保前端页面正常渲染，API 调用正确，如有疑问请向用户确认。

- [x] 10. AWS CDK 基础设施
  - [x] 10.1 初始化 CDK 项目
    - 创建 TypeScript CDK 项目
    - 定义 Stack 结构
    - _需求: 11.1_

  - [x] 10.2 定义数据层资源
    - RDS PostgreSQL 实例（VPC、安全组、参数组）
    - SQS 队列（批量测试队列 + 死信队列）
    - S3 存储桶（前端静态资源、测试集文件）
    - _需求: 6.1, 6.3_

  - [x] 10.3 定义计算层资源
    - Lambda 函数：审核 API、管理后台 API、批量测试 Worker
    - HTTP API Gateway v2：路由配置、Lambda Authorizer（X-API-Key 校验 + 5 min 缓存）、JWT Authorizer（Cognito）
    - SQS → Lambda 事件源映射
    - _需求: 10.1, 10.2_

  - [x] 10.4 定义前端部署资源
    - S3 + CloudFront 分发
    - CloudFront OAI 配置
    - _需求: 10.2_

  - [x] 10.5 定义认证与可观测性资源
    - Cognito User Pool 和 App Client
    - CloudWatch 日志组和告警
    - X-Ray 追踪配置
    - _需求: 10.2, 11.1, 11.2, 11.3_

- [x] 11. 集成与收尾
  - [x] 11.1 配置 Lambda 打包与部署脚本
    - 后端 Lambda 打包（依赖层或 Docker 镜像）
    - 前端构建产物上传 S3
    - _需求: 9.1_

  - [x] 11.2 端到端联调
    - 连接所有组件：HTTP API Gateway v2 → Lambda → RDS / Bedrock / SQS
    - 验证审核 API 完整流程
    - 验证管理后台完整流程
    - _需求: 1.1, 3.4, 9.1_

- [x] 12. 最终检查点 — 全部验证
  - 确保所有测试通过，如有疑问请向用户确认。

- [x] 13. 标签分类系统集成
  - [x] 13.1 后端 Schema 和模型更新（已完成）
    - ModerationResponse schema 添加 text_label 和 image_label 字段
    - ModerationLog 模型添加 text_label 和 image_label 列
    - ModelResponse dataclass 添加 text_label 和 image_label 字段
    - 审核 API 透传标签到响应和日志
    - Admin logs schema（LogListItem、LogDetail）添加标签字段
    - _需求: 13.1, 13.4_

  - [x] 13.2 前端审核日志页面展示标签
    - 日志列表表格增加 text_label 和 image_label 列
    - 日志详情抽屉展示标签信息
    - 日志筛选支持按标签类型过滤
    - _需求: 13.5_

  - [x] 13.3 前端批量测试页面展示标签
    - 测试报告中展示标签准确率指标
    - 错误案例列表展示期望标签 vs 实际标签
    - _需求: 13.6_

  - [x] 13.4 批量测试 Worker 标签对比
    - TestCase 数据类增加 expected_text_label 和 expected_image_label 字段
    - TestCaseResult 数据类增加 actual_text_label 和 actual_image_label 字段
    - _execute_single_case 方法对比标签结果
    - _需求: 13.6_

  - [x] 13.5 测试指标计算增加标签准确率
    - calculate_metrics 函数增加 text_label_accuracy 和 image_label_accuracy 指标
    - 测试报告中包含标签维度的混淆矩阵或分布统计
    - _需求: 13.6_

  - [x] 13.6 提示词模板更新
    - 确认 AI 模型提示词包含标签分类指令（scripts/update_rules_v2.py 已创建）
    - 验证模型响应正确输出 text_label 和 image_label 字段
    - _需求: 13.4_

  - [x] 13.7 数据库迁移脚本
    - 创建 Alembic 迁移脚本，为 moderation_logs 表添加 text_label 和 image_label 列
    - _需求: 13.1_

- [x] 14. 动态标签配置
  - [x] 14.1 创建 label_definitions 数据模型与迁移脚本
    - 使用 SQLAlchemy 定义 label_definitions 表模型（id、label_key、label_type、display_name、description、action、enabled、sort_order、created_at、updated_at）
    - 创建 Alembic 迁移脚本，包含表创建和默认标签种子数据（9 个 text 标签 + 10 个 image 标签）
    - 创建联合唯一索引 (label_key, label_type) 和查询索引 (label_type, enabled)
    - _需求: 14.2, 14.5_

  - [x] 14.2 创建标签定义 Pydantic Schema
    - 定义 LabelDefinitionCreate、LabelDefinitionUpdate、LabelDefinitionResponse Schema
    - 定义 LabelDefinitionList 分页响应 Schema
    - _需求: 14.1, 14.2_

  - [x] 14.3 实现标签定义 CRUD API
    - GET /api/admin/labels — 标签列表（支持按 label_type 和 enabled 筛选）
    - POST /api/admin/labels — 创建标签（验证 label_key + label_type 唯一性）
    - PUT /api/admin/labels/{id} — 更新标签
    - DELETE /api/admin/labels/{id} — 删除标签
    - _需求: 14.1, 14.2_

  - [x] 14.4 RuleEngine 动态加载标签并注入提示词
    - 实现 get_enabled_labels 方法从数据库加载启用标签
    - 修改 assemble_prompt 方法，动态生成标签分类指令片段替代硬编码标签列表
    - 确保标签变更后立即生效（每次请求从数据库加载）
    - _需求: 14.3, 14.4_

  - [ ]* 14.5 编写标签定义 CRUD 功能测试
    - **Property 8: 标签定义 CRUD 完整性** — 验证必填字段校验和唯一性约束
    - **Validates: 需求 14.1, 14.2**

  - [ ]* 14.6 编写动态标签注入提示词测试
    - **Property 9: 动态标签注入提示词一致性** — 验证提示词包含所有启用标签且不包含禁用标签
    - **Validates: 需求 14.3, 14.4**

  - [x] 14.7 前端标签管理页面
    - 新增 LabelsPage.vue 页面，路由 /admin/labels
    - 标签列表表格（按 label_type 分 Tab：文案标签 / 图片标签）
    - 创建/编辑标签弹窗表单（label_key、label_type、display_name、description、action 下拉选择、enabled 开关、sort_order）
    - 启用/禁用开关操作
    - 删除确认对话框
    - 配置路由和侧边栏导航
    - _需求: 14.1, 14.2_

- [x] 15. 增强数据统计
  - [x] 15.1 moderation_logs 表添加 language 字段
    - 更新 ModerationLog SQLAlchemy 模型添加 language 字段（VARCHAR 10）
    - 添加索引 idx_logs_language_created (language, created_at)
    - 更新 ModelResponse 和 ModerationResponse 添加 language 字段
    - AI 模型提示词中要求返回 language 字段（ISO 639-1 语言代码）
    - 审核 API 将模型返回的 language 存储到 moderation_logs
    - _需求: 15.5_

  - [x] 15.2 实现新增统计 API
    - GET /api/admin/stats/text-labels — 文案标签分布（支持 start_date、end_date 参数）
    - GET /api/admin/stats/image-labels — 图片标签分布（支持 start_date、end_date 参数）
    - GET /api/admin/stats/languages — 语言分布（支持 start_date、end_date 参数）
    - 更新 stats Schema 添加新的响应模型
    - _需求: 15.1, 15.2, 15.3, 15.4_

  - [x] 15.3 前端数据统计页面增强
    - StatsPage.vue 新增文案标签分布图表（饼图或柱状图）
    - StatsPage.vue 新增图片标签分布图表（饼图或柱状图）
    - StatsPage.vue 新增语言分布图表（饼图或柱状图）
    - 所有新增图表接入页面顶部的日期范围选择器
    - _需求: 15.1, 15.2, 15.3, 15.4_

- [x] 16. 智能模型路由
  - [x] 16.1 model_config 表增加 routing_type 字段
    - 为 model_config 表添加 routing_type 列（VARCHAR 20：text_only / multimodal / any）
    - 更新 ModelConfig SQLAlchemy 模型和 Pydantic Schema
    - 更新模型配置种子数据：Haiku 4.5 设为 text_only，Sonnet 4 设为 multimodal
    - _需求: 16.3_

  - [x] 16.2 审核 API 实现智能路由
    - 修改 _build_model_settings 函数，根据请求是否包含图片选择不同模型
    - 纯文本请求：优先使用 routing_type=text_only 的主模型
    - 图文混合请求：优先使用 routing_type=multimodal 的主模型
    - 如果对应类型没有配置主模型，回退到 routing_type=any 或任意主模型
    - _需求: 16.1, 16.2, 16.4_

  - [x] 16.3 前端模型配置页面增加路由类型
    - ModelConfigPage.vue 表格增加 routing_type 列
    - 编辑弹窗增加 routing_type 下拉选择（纯文本专用 / 图文混合专用 / 通用）
    - _需求: 16.3_

- [x] 17. 预审规则快速过滤
  - [x] 17.1 实现 PreFilterEngine
    - 创建 `backend/app/services/pre_filter.py`，定义 PreFilterRule / PreFilterResult dataclass
    - 编译 DEFAULT_RULES：至少 7 类违规（privacy_leak / spam / toxic / hate_speech / misleading / illegal_trade / 政治敏感）
    - 支持中文正则（手机号 / 身份证 / 邮箱 / 微信QQ / 国际电话 / 日韩电话）
    - 支持中英文辱骂词库 + 仇恨词库 + 虚假医疗宣传
    - _需求: 17.1, 17.5_

  - [x] 17.2 集成到审核 API
    - 在 moderate_content 函数开头调用 _pre_filter.scan(text)
    - 若命中（matched=True），跳过规则加载 / prompt 组装 / 模型调用，直接返回并写入 moderation_logs，model_id 字段标记为 "pre_filter"
    - Lambda 内部处理时间 <50ms
    - _需求: 17.1, 17.4_

- [x] 18. 低延迟 HTTP API 网关与性能 SLA
  - [x] 18.1 CDK 部署 HTTP API Gateway v2
    - 在 ModerationStack 中新增 HttpApi 资源（aws-cdk-lib/aws-apigatewayv2）
    - 配置 CORS 原生支持（allowOrigins / allowMethods / allowHeaders）
    - 创建 Lambda Authorizer 函数校验 X-API-Key，结果缓存 5 分钟
    - 路由 /api/v1/{proxy+} 接 moderationApi Lambda，走 Lambda Authorizer
    - 路由 /health 无需认证
    - _需求: 18.1, 18.5_

  - [x] 18.2 编写性能测试脚本
    - `scripts/test_rest_vs_http.py` — REST vs HTTP API A/B 对比（20 条用例）
    - `scripts/test_http_api_mixed.py` — 混合负载测试（预审 + 模型路径）
    - `scripts/test_prefilter_coverage.py` — 预审命中率 + 延迟
    - `scripts/test_connection_reuse.py` — 连接复用 A/B
    - _需求: 18.2, 18.3, 18.4_

  - [x] 18.3 客户端集成指南
    - 编写 `docs/client-integration-guide.md`
    - 覆盖 Python (requests/httpx)、Node.js (axios+keepalive)、Java (OkHttp)、Go (http.Client) 四种语言的连接复用示例
    - 文档中明确延迟 SLA 和达成条件
    - _需求: 18.6_

## 备注

- 标记 `*` 的任务为可选，可跳过以加速 MVP 交付
- 每个任务引用了对应的需求编号，确保可追溯性
- 检查点用于阶段性验证，确保增量交付质量
- 真实测试数据由客户后续提供，当前阶段使用模拟数据进行功能验证
