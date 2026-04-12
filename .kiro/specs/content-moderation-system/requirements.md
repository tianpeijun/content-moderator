# 需求文档

## 简介

商城评论内容审核系统，用于自动审核用户提交的评论内容（文本和图片）。系统通过动态可配置的审核规则驱动 AI 模型（Amazon Bedrock，支持 Claude、Amazon Nova 等多种模型）进行内容审核，支持规则管理、批量测试、审核日志查询等功能。系统每日处理约 2000 条评论，部署于 AWS 云平台。

## 术语表

- **Moderation_API**: 内容审核 API 服务，接收评论内容并返回审核结果
- **Rule_Engine**: 动态规则引擎，负责加载、管理审核规则并组装最终提示词
- **Admin_Console**: 管理后台，提供规则管理、审核日志、批量测试等管理功能
- **AI_Model**: Amazon Bedrock 上的 AI 模型（支持 Claude Sonnet/Haiku、Amazon Nova 等），执行实际的内容审核判断
- **Rule**: 审核规则，包含名称、类型、提示词模板、变量配置、触发动作、优先级和启用状态
- **Prompt_Template**: 提示词模板，支持 {{variable}} 变量替换的文本模板
- **Test_Suite**: 批量测试集，Excel 格式的测试数据集合
- **Moderation_Task**: 审核任务，一次内容审核的完整生命周期记录
- **Moderation_Result**: 审核结果，包含 pass（通过）、reject（拒绝）、review（人工复审）、flag（标记）四种状态
- **Text_Label**: 文案分类标签，标识文本内容的违规类型。取值范围：safe（正常/安全内容→通过）、spam（垃圾广告/引流/推广→拒绝）、toxic（辱骂/人身攻击/脏话→拒绝）、hate_speech（仇恨/歧视/种族主义→拒绝）、privacy_leak（泄露个人隐私信息→拒绝）、political（政治敏感内容→拒绝）、self_harm（自残/自杀暗示→拒绝+预警）、illegal_trade（违法交易暗示→拒绝）、misleading（虚假宣传/误导性信息→拒绝）
- **Image_Label**: 图片分类标签，标识图片内容的违规类型。取值范围：无（无图片或安全图片）、pornography（涉黄内容→拒绝）、gambling（涉赌内容→拒绝）、drugs（涉毒内容→拒绝）、violence（暴力/血腥内容→拒绝）、terrorism（恐怖主义符号→拒绝）、qr_code_spam（二维码引流→拒绝）、contact_info（图片水印联系方式→拒绝）、ad_overlay（广告覆盖图→拒绝）、minor_exploitation（未成年人保护相关→拒绝+上报）
- **Confusion_Matrix**: 混淆矩阵，包含 TP（真正例）、FP（假正例）、TN（真负例）、FN（假负例）的统计
- **Label_Definition**: 标签定义记录，包含 label_key（唯一标识）、label_type（text/image）、display_name（中文说明）、action（处置动作）、enabled（启用状态）、sort_order（排序序号）
- **Language_Code**: 语言代码，ISO 639-1 格式（如 en、zh、fr、ja 等），用于标识审核内容的语言

## 需求

### 需求 1：单条内容审核

**用户故事：** 作为后端开发，我希望通过 API 提交单条评论内容进行审核，以便集成到商城评论发布流程中。

#### 验收标准

1. WHEN 客户端发送 POST 请求到 /api/v1/moderate 并携带评论文本，THE Moderation_API SHALL 加载当前启用的 Rule 集合，通过 Rule_Engine 组装最终提示词，调用 AI_Model 执行审核，并返回包含审核结果（pass/reject/review/flag）、Text_Label、Image_Label、命中规则列表和置信度的 JSON 响应
2. WHEN 客户端发送 POST 请求到 /api/v1/moderate 并携带评论文本和图片 URL，THE Moderation_API SHALL 同时对文本和图片执行审核，并返回包含 Text_Label 和 Image_Label 的综合审核结果
3. WHEN 客户端发送 POST 请求到 /api/v1/moderate 并仅携带图片 URL，THE Moderation_API SHALL 仅对图片执行审核，并返回包含 Image_Label 的审核结果
7. WHEN 图片 URL 为公网链接时，THE Moderation_API SHALL 直接通过 HTTP 获取图片内容；WHEN 图片 URL 为 S3 路径（s3:// 前缀）时，THE Moderation_API SHALL 通过 AWS SDK 从 S3 获取图片内容
4. IF 请求缺少必要字段（文本和图片 URL 均为空），THEN THE Moderation_API SHALL 返回 HTTP 400 错误码和描述性错误信息
5. IF AI_Model 调用失败或超时，THEN THE Moderation_API SHALL 根据模型配置的降级策略处理请求，并在响应中标注降级处理标记
6. WHEN 请求未携带有效的 API Key，THE Moderation_API SHALL 返回 HTTP 401 错误码

### 需求 2：异步审核结果查询

**用户故事：** 作为后端开发，我希望能够查询异步审核任务的结果，以便在审核耗时较长时获取最终结果。

#### 验收标准

1. WHEN 客户端发送 GET 请求到 /api/v1/moderate/{taskId}，THE Moderation_API SHALL 返回该 Moderation_Task 的当前状态（pending/processing/completed/failed）和审核结果
2. IF 提供的 taskId 不存在，THEN THE Moderation_API SHALL 返回 HTTP 404 错误码和描述性错误信息
3. WHEN Moderation_Task 状态为 completed，THE Moderation_API SHALL 在响应中包含完整的审核结果、命中规则列表和置信度

### 需求 3：动态规则管理

**用户故事：** 作为产品经理，我希望能够动态管理审核规则，以便灵活调整审核策略而无需修改代码。

#### 验收标准

1. THE Admin_Console SHALL 提供规则的创建、读取、更新和删除操作界面
2. WHEN 创建或编辑 Rule 时，THE Admin_Console SHALL 要求填写规则名称、类型（文本/图片/两者）、适用业务类型、提示词模板、变量配置、触发动作（reject/review/flag）、优先级和启用状态
3. WHEN 编辑 Prompt_Template 时，THE Admin_Console SHALL 支持 {{variable}} 格式的变量占位符，并提供变量配置界面用于定义变量值（如竞品列表、关键词列表）
4. WHEN 管理员启用或禁用 Rule 时，THE Rule_Engine SHALL 在后续审核请求中立即使用更新后的规则集合
5. WHEN 管理员调整 Rule 优先级时，THE Rule_Engine SHALL 按照更新后的优先级顺序组装提示词
6. WHEN Rule 被修改时，THE Admin_Console SHALL 保存该 Rule 的版本历史记录，包含修改时间、修改人和修改内容

### 需求 4：提示词组装与预览

**用户故事：** 作为产品经理，我希望能够预览最终组装的提示词，以便验证规则组合的效果。

#### 验收标准

1. WHEN 管理员选择一组 Rule 组合时，THE Admin_Console SHALL 实时展示由基础模板和各启用规则的提示词片段组装而成的最终提示词
2. WHEN 管理员在提示词预览界面输入测试内容时，THE Admin_Console SHALL 调用 AI_Model 执行审核并展示审核结果
3. THE Rule_Engine SHALL 按照"基础模板 + 各启用规则提示词片段（按优先级排序）"的方式组装最终提示词

### 需求 5：审核日志管理

**用户故事：** 作为产品经理，我希望能够查看和筛选审核日志，以便追踪审核效果和排查问题。

#### 验收标准

1. THE Admin_Console SHALL 提供审核日志列表页面，支持按时间范围、审核结果、业务类型和命中规则进行筛选
2. WHEN 管理员点击某条审核日志时，THE Admin_Console SHALL 展示该条审核的原始内容（文本和/或图片）、最终组装的提示词和 AI_Model 的完整响应
3. WHEN 管理员点击导出按钮时，THE Admin_Console SHALL 将当前筛选条件下的审核日志导出为文件
4. WHEN 每次审核完成时，THE Moderation_API SHALL 将审核日志（包含原始内容、最终提示词、模型响应、审核结果、命中规则、耗时）写入 PostgreSQL

### 需求 6：批量测试

**用户故事：** 作为产品经理，我希望能够上传 Excel 测试集进行批量测试，以便验证审核规则的准确性和效果。

#### 验收标准

1. WHEN 管理员上传 .xlsx 格式的 Test_Suite 文件时，THE Admin_Console SHALL 解析文件并验证格式，要求包含序号、内容文本、图片URL、期望结果（pass/reject/review/flag）、业务类型、备注字段
2. IF 上传的 Test_Suite 文件格式不正确或缺少必要字段，THEN THE Admin_Console SHALL 显示具体的格式错误信息
3. WHEN 管理员选择规则组合并启动批量测试时，THE Admin_Console SHALL 通过 SQS 队列异步执行测试，并在界面上实时显示测试进度（已完成数/总数）
4. WHEN 批量测试完成时，THE Admin_Console SHALL 生成测试报告，包含准确率、召回率、F1 分数、Confusion_Matrix（TP/FP/TN/FN）、错误案例列表（预期结果 vs 实际结果）和各规则命中分布
5. WHEN 管理员点击导出报告按钮时，THE Admin_Console SHALL 将测试报告导出为 .xlsx 格式的 Excel 文件
6. THE Admin_Console SHALL 保存历史测试记录，并支持不同测试记录之间的结果对比
7. THE Admin_Console SHALL 支持包含 1000 条以上数据的 Test_Suite 批量测试

### 需求 7：模型配置管理

**用户故事：** 作为产品经理，我希望能够配置和切换 AI 模型，以便优化审核效果和成本。

#### 验收标准

1. THE Admin_Console SHALL 提供模型选择界面，支持选择 Amazon Bedrock 上可用的模型（包括但不限于 Claude Sonnet、Claude Haiku、Amazon Nova 等），以便根据性价比灵活选择
2. THE Admin_Console SHALL 提供模型参数调整界面，支持配置温度（temperature）、最大输出长度（max_tokens）等参数
3. WHEN 管理员配置降级策略时，THE Admin_Console SHALL 支持设置主模型失败后的备用模型（可选择更低成本的模型作为降级方案）和默认审核结果
4. WHEN 模型配置变更时，THE Rule_Engine SHALL 在后续审核请求中立即使用更新后的模型配置
5. THE Admin_Console SHALL 在模型选择界面展示各模型的单次调用参考成本，辅助管理员进行性价比决策

### 需求 8：数据统计

**用户故事：** 作为产品经理，我希望能够查看审核数据统计，以便了解系统运行状况和审核效果。

#### 验收标准

1. THE Admin_Console SHALL 展示审核量趋势图表，支持按天、周、月维度查看
2. THE Admin_Console SHALL 展示各 Rule 的命中率统计
3. THE Admin_Console SHALL 展示 AI_Model 调用成本统计，支持按时间范围查看

### 需求 9：规则变更实时生效

**用户故事：** 作为后端开发，我希望规则变更能够实时生效，以便审核策略调整后立即应用到新的审核请求。

#### 验收标准

1. WHEN Rule 被创建、修改、启用或禁用时，THE Rule_Engine SHALL 在后续审核请求中立即使用更新后的规则集合（直接从 PostgreSQL 加载最新规则）

### 需求 10：用户认证与授权

**用户故事：** 作为后端开发，我希望系统具备安全的认证机制，以便保护审核 API 和管理后台的访问安全。

#### 验收标准

1. THE Moderation_API SHALL 通过 API Key 验证所有审核接口的请求身份
2. THE Admin_Console SHALL 通过 Amazon Cognito 进行用户登录认证
3. IF 用户未登录或登录会话过期，THEN THE Admin_Console SHALL 重定向用户到登录页面

### 需求 11：系统可观测性

**用户故事：** 作为后端开发，我希望系统具备完善的监控和追踪能力，以便快速定位和排查问题。

#### 验收标准

1. THE Moderation_API SHALL 将所有请求日志和错误日志发送到 Amazon CloudWatch
2. THE Moderation_API SHALL 集成 AWS X-Ray 进行分布式链路追踪，覆盖从 API 请求到 AI_Model 调用的完整链路
3. WHEN AI_Model 调用延迟超过配置的阈值时，THE Moderation_API SHALL 在 CloudWatch 中记录告警级别的日志

### 需求 12：提示词模板解析与格式化

**用户故事：** 作为后端开发，我希望提示词模板能够正确解析和格式化，以便生成准确的最终提示词。

#### 验收标准

1. WHEN Rule_Engine 处理 Prompt_Template 时，THE Rule_Engine SHALL 将模板中所有 {{variable}} 占位符替换为对应的变量值
2. IF Prompt_Template 中包含未定义的变量占位符，THEN THE Rule_Engine SHALL 记录警告日志并将该占位符替换为空字符串
3. FOR ALL 有效的 Prompt_Template，经过变量替换后再提取变量占位符，SHALL 不包含任何 {{variable}} 格式的占位符（往返一致性）
4. THE Rule_Engine SHALL 按照 Rule 优先级从高到低的顺序拼接各规则的提示词片段，生成最终提示词

### 需求 13：标签分类系统

**用户故事：** 作为产品经理，我希望审核结果包含具体的违规类型标签（Text_Label 和 Image_Label），以便精确了解内容违规原因并执行对应的处置动作。

#### 验收标准

1. WHEN AI_Model 返回审核结果时，THE Moderation_API SHALL 在响应中包含 text_label 字段（取值范围：safe、spam、toxic、hate_speech、privacy_leak、political、self_harm、illegal_trade、misleading）和 image_label 字段（取值范围：无、pornography、gambling、drugs、violence、terrorism、qr_code_spam、contact_info、ad_overlay、minor_exploitation）
2. WHEN text_label 为 safe 且 image_label 为"无"时，THE Moderation_API SHALL 将审核结果映射为 pass；WHEN text_label 或 image_label 为其他任意违规标签时，THE Moderation_API SHALL 将审核结果映射为 reject
3. WHEN text_label 为 self_harm 时，THE Moderation_API SHALL 在审核结果中附加预警标记；WHEN image_label 为 minor_exploitation 时，THE Moderation_API SHALL 在审核结果中附加上报标记
4. THE Rule_Engine SHALL 在组装最终提示词时包含标签分类指令，要求 AI_Model 在响应中输出 text_label 和 image_label 字段
5. WHEN 管理员查看审核日志时，THE Admin_Console SHALL 在日志列表和详情中展示 Text_Label 和 Image_Label
6. WHEN 批量测试执行时，THE Admin_Console SHALL 对比实际标签与期望标签，并在测试报告中包含标签准确率指标

### 需求 14：动态标签配置

**用户故事：** 作为产品经理，我希望能够通过管理后台动态管理标签定义（Text_Label 和 Image_Label），以便灵活调整标签体系和处置动作而无需修改代码。

#### 验收标准

1. THE Admin_Console SHALL 提供标签管理页面，支持对标签定义的创建、编辑、启用/禁用和删除操作
2. WHEN 创建或编辑标签定义时，THE Admin_Console SHALL 要求填写标签键名（label_key，唯一标识如 spam）、标签类型（label_type：text 或 image）、显示名称（display_name，如"垃圾广告"）、处置动作（action：pass/reject/reject_warn/reject_report）、启用状态（enabled）和排序序号（sort_order）
3. WHEN Rule_Engine 组装最终提示词时，THE Rule_Engine SHALL 从数据库动态加载所有启用状态的标签定义，并将标签列表包含在 AI_Model 的提示词指令中
4. WHEN 管理员修改标签定义后，THE Rule_Engine SHALL 在后续审核请求中立即使用更新后的标签集合
5. WHEN 系统首次部署时，THE Admin_Console SHALL 自动初始化默认标签数据（9 个文案标签和 9 个图片标签及"无"标签），与现有标签体系保持一致

### 需求 15：增强数据统计

**用户故事：** 作为产品经理，我希望在数据统计页面查看更多维度的统计信息（文案标签分布、图片标签分布、语言分布），以便全面了解审核内容的特征和趋势。

#### 验收标准

1. THE Admin_Console SHALL 在数据统计页面展示文案标签分布图表，统计各 Text_Label 的审核命中数量
2. THE Admin_Console SHALL 在数据统计页面展示图片标签分布图表，统计各 Image_Label 的审核命中数量
3. THE Admin_Console SHALL 在数据统计页面展示语言分布图表，统计各语言（如 en、zh、fr 等）的审核数量
4. WHEN 管理员选择日期范围时，THE Admin_Console SHALL 按所选日期范围过滤所有分布图表的数据
5. WHEN 每次审核完成时，THE Moderation_API SHALL 检测评论内容的语言并将语言代码存储到审核日志的 language 字段中
