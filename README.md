# 飞控QMS系统（Feikong QMS）

零第三方依赖的质量管理系统（QMS）：Python 标准库 `http.server + sqlite3` 单进程运行，原生 HTML/CSS/JS 前端，17 个功能页面，96 条 REST 路由。

## 功能全景

- **检验全类型**：来料 IQC / 过程 IPQC（首件、巡检）/ 成品 FQC / 出货 OQC，检验单七态状态机 + 六道闸口（致命缺陷 Ac=0 一票否决）
- **AQL 抽样引擎**：ISO 2859-1 批量→字码→样本量/Ac/Re 自动查表
- **不合格品 NCR**：五态闭环（评审→处置→验证），让步接收不良率上限闸口，不合格判定自动开单
- **纠正预防 CAPA**：8D 七步推进（D1 组队 → D8 关闭），每步闸口强制校验
- **SPC 过程能力**：x̄-R 控制图、Cp/Cpk、判异点标记
- **质量分析**：缺陷帕累托（含加权口径）、FPY、月度趋势
- **供应商质量**：月度评分（质量50/交付30/响应20）、IRR、PPM 排行
- **质量成本 COQ**：PAF 四类（预防/鉴定/内损/外损）核算
- **集成三通道**：API Key（fck_ 前缀）、Webhook（HMAC-SHA256，15 事件）、增量同步游标
- **平台能力**：多通道令牌、Idempotency-Key 幂等、240/min 限流、OpenAPI 3.0、审计日志

## 快速开始

```bash
python backend/server.py
# 打开 http://127.0.0.1:8024  账号 admin / qms@2026
```

环境变量：`FEIKONG_PORT`（默认 8024）、`FEIKONG_DB`（数据库路径）、`PORT`（容器模式，绑 0.0.0.0）。

## 测试

```bash
python scripts/run_tests.py          # 三层门禁：单元 39 + 接口 24 + E2E 9
python tools/smoke_api.py            # 全链路冒烟 41 检查点
python tools/ui_check.py             # 17 页 UI 巡检
python tools/build_demo.py           # 构建离线单文件 DEMO
```

## 目录结构

```
backend/   db.py（26表）· qms.py（纯函数内核）· seed.py（确定性演示数据）· server.py（96路由）
frontend/  app.js + inspect/quality/mdm/report.js + style.css（原生 JS，hash 路由）
tools/     冒烟/UI巡检/DEMO构建/文档构建/知识库上传/GitHub推送
tests/     单元 + 接口 + 端到端（pytest + Playwright）
docs/      建设方案 · 接口契约 · 测试报告 · 操作手册（md + docx）
deploy/    build_package.py 部署打包
demo/      feikong-qms-demo.html 离线演示（210 KB 单文件）
```

## 文档

- [建设方案](docs/feikong-design.md)
- [REST 接口契约](docs/api.md)
- [测试报告](docs/test-report.md)
- [操作手册](docs/user-guide.md)
- 在线 OpenAPI：`GET /api/openapi.json`

---
飞控精密制造（苏州）有限公司 · 质量信息化项目组 ｜ V1.0 ｜ 2026-10
