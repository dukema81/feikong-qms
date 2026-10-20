# 飞控QMS系统建设方案

**版本**：V1.0 ｜ **编制**：飞控精密制造（苏州）有限公司 · 质量信息化项目组 ｜ **状态**：评审通过 · 放行实施

---

## 1. 项目概述

飞控QMS系统（Feikong QMS）是面向离散制造企业的质量管理系统，覆盖 **来料检验（IQC）→ 过程检验（IPQC）→ 成品检验（FQC）→ 出货检验（OQC）→ 不合格品处置（NCR）→ 纠正预防（CAPA/8D）** 的质量业务全闭环，配套 AQL 抽样引擎、SPC 过程能力监控、供应商质量评价、质量成本（COQ）核算与开放集成通道。

系统采用 **零第三方依赖** 架构（Python 标准库 http.server + SQLite WAL），单进程即可运行，与飞鹰CRM、飞驰MES、飞传WMS 同属「企业管理系统」产品族，共享同一技术底座与集成规范。

## 2. 建设目标

| 目标 | 度量口径 | 目标值 |
| --- | --- | --- |
| 检验业务线上化 | IQC/IPQC/FQC/OQC 四类单据电子化 | 100% |
| 来料批次合格率 IRR | 合格批次 / 受检批次（月） | ≥ 95% |
| 不良 PPM | 不良数 / 受检数 × 10⁶ | ≤ 3000 |
| NCR 按期闭环率 | 时限内关闭 / 全部关闭 | ≥ 95% |
| CAPA 推进规范率 | 8D 七道闸口强制校验 | 100% |
| 过程能力 | 关键特性 Cpk | ≥ 1.33 |
| 质量成本可视 | PAF 四类月度核算 | 月度出表 |

## 3. 业务蓝图

### 3.1 检验类型与环节

| 类型 | 环节 | 触发 | 检验方式 |
| --- | --- | --- | --- |
| IQC | 来料 | 采购到货 | AQL 抽样（ISO 2859-1 一般水平 II） |
| IPQC | 过程 | 首件/巡检/完工 | 首件全项 + 按间隔巡检 |
| FQC | 成品 | 工单完工入库前 | 抽样或全检（可配置） |
| OQC | 出货 | 订单发运前 | 开箱抽样 + 随机文件齐套 |

### 3.2 检验单七态状态机与闸口

```
待检验 →(开始检验)→ 检验中 →(提交判定)→ 待判定 →(判定)→ 已判定 →(放行)→ 已放行 →(关闭)→ 已关闭
                                                        └→(不合格转NCR, 关闭)→ 已关闭
任意未放行状态 →(取消)→ 已取消
```

| 闸口 | 校验内容 |
| --- | --- |
| 开始检验 | 批量必须已登记 |
| 提交判定 | 检验项目全部录入结果（OK/NG）；有不良须登记缺陷代码 |
| 判定 | 结论合法；**致命缺陷（A类）判合格一票否决**；判合格须检验员签署；判不合格须有不良数 |
| 放行 | 仅合格单可放行 |
| 关闭 | 不合格单须已生成 NCR |

### 3.3 NCR 五态与 CAPA 八步

- **NCR**：待评审 →（评审意见+处置方式）→ 已评审 →（责任人+时限）→ 处置中 →（处置结果）→ 待验证 →（验证人+验证记录）→ 已关闭。让步接收须过 **不良率 ≤ 3%（可配置）** 闸口。
- **CAPA（8D）**：D1 组建小组 → D2 问题描述（≥20字）→ D3 围堵措施 → D4 根因分析（≥10字，5Why）→ D5 纠正措施/任务 → D6 实施验证 → D7 预防再发 → D8 总结关闭。每步一道闸口，未满足不可推进。

## 4. 总体架构

```
┌──────────────────────────────────────────────┐
│ 前端（原生 HTML/CSS/JS，17 页，hash 路由）      │
├──────────────────────────────────────────────┤
│ 服务层 server.py（96 条 REST 路由）            │
│  认证/鉴权 · 幂等 · 限流 · Webhook 投递 · OpenAPI │
├──────────────────────────────────────────────┤
│ 业务内核 qms.py（纯函数，无 I/O）               │
│  状态机/闸口 · AQL 抽样 · SPC/Cpk · 帕累托      │
│  FPY/PPM · 供应商评分 · COQ · 权限矩阵          │
├──────────────────────────────────────────────┤
│ 数据层 db.py（SQLite WAL，26 张表）             │
└──────────────────────────────────────────────┘
```

## 5. 核心规则与算法

| 规则 | 口径 |
| --- | --- |
| AQL 抽样 | ISO 2859-1 批量→字码（A~R）→样本量；按 AQL 档位给出 Ac/Re；致命 Ac=0 |
| 缺陷加权 | 加权指数 = 致命×10 + 严重×5 + 轻微×1 |
| SPC 控制限 | x̄-R 图（n=5）：A₂=0.577，D₄=2.114；判异 = 超出 UCL/LCL |
| 过程能力 | Cp=(USL−LSL)/6σ；Cpk=min(Cpu,Cpl)；等级 优≥1.67 / 良≥1.33 / 中≥1.0 |
| FPY | 各阶段直通率 RTY 连乘 |
| PPM | 不良数 / 受检数 × 10⁶ |
| 供应商评分 | 质量50% + 交付30% + 响应20%；A≥90 B≥80 C≥70 D<70 |
| COQ | PAF 分类：预防 / 鉴定 / 内部损失 / 外部损失，失败成本占比监控 |
| 时限监控 | NCR 7 天 / CAPA 30 天默认时限，逾期自动亮红 |

## 6. 角色与权限（11 权限 × 8 角色）

| 角色 | 关键权限 |
| --- | --- |
| admin 系统管理员 | 全部 11 项 |
| quality_mgr 质量经理 | 检验执行 + NCR/CAPA + 供应商 + COQ |
| qa_engineer 质量工程师 | 检验执行 + NCR/CAPA |
| inspector 检验员 | 三类检验执行（无 NCR/CAPA 管理权） |
| process_engineer 工艺工程师 | IPQC + CAPA |
| purchaser 采购员 | 供应商档案 |
| supplier_qa SQE | IQC + NCR |
| viewer 访客 | 只读驾驶舱 |

## 7. 业务规则（12 条，可配置）

aql_default=1.0、first_article_required=1、ipqc_interval=120、fqc_full_check=0、ncr_due_days=7、capa_due_days=30、concession_max=0.03、critical_block=1、spc_rule=western_electric、cpk_target=1.33、supplier_grade_a=90、on_close_rate=0.95。

## 8. 数据模型（26 张表）

users / suppliers / materials / plans / plan_items / defects / inspections / inspection_items / ncrs / capas / capa_tasks / scorings / coq / spc_series / qdocs / api_keys / webhooks / webhook_logs / field_maps / events / idem_keys / logs / settings / seq 等。

## 9. 集成设计（三通道）

1. **API Key**：`fck_` 前缀，SHA-256 落库，read/write 范围，`X-Qms-Key` 头携带。
2. **Webhook**：15 种事件（inspection.created/stage/closed、ncr.*、capa.*、material.*、qdoc.released、key.created、rule.updated、test.ping），HMAC-SHA256(secret, ts+"."+body) 签名，60/120 秒退避重试。
3. **增量同步**：`GET /api/sync/changes?since={cursor}`，单次 ≤500 条。

幂等：`Idempotency-Key` 头重放；限流：写接口 240 次/分钟。

## 10. 前端设计（17 页）

质量驾驶舱 / IQC / IPQC / 成品出货检验 / NCR / CAPA / 检验方案 / 缺陷代码 / SPC / 质量分析 / 供应商质量 / 质量成本 / 质量文件 / 报表中心 / 集成中心 / 系统设置 / 操作日志。

## 11. 非功能设计

- 安全：SHA-256 密码、令牌多通道携带（Bearer / X-Qms-Token / Cookie / 查询串）、SQL 全参数化、HTML 全量转义。
- 性能：单机 200 并发线程池、WAL 读写并发、全表索引。
- 可靠性：请求级连接兜底回收（防锁表）、Webhook 失败退避、审计日志全量落库。

## 12. 实施计划与验收

六阶段：环境部署 → 主数据与方案导入 → 检验上线（IQC→IPQC→FQC）→ NCR/CAPA 闭环 → 集成对接 → 运行优化。验收对照第 2 节目标表；交付物：本方案、接口契约、测试报告、操作手册、DEMO、部署包与源码仓库。
