# 飞控QMS系统 REST 接口契约

**版本**：V1.0 ｜ **用途**：与 ERP / MES / SRM / WMS 等系统对接 ｜ **在线契约**：`GET /api/openapi.json`

---

## 1. 通用约定

- Base URL：`http(s)://<host>:8024/api`，响应为 JSON 对象（无包裹），错误返回 `{"code": <http状态码>, "message": "..."}`。
- 状态码：200 成功；400 业务校验失败；401 未认证；403 权限不足；404 资源不存在；429 限流；500 服务器错误。
- 鉴权（会话）：登录后令牌支持 5 种携带方式——`Authorization: Bearer <token>`、`X-Qms-Token`、`X-Auth-Token`、Cookie `token=<token>`、查询串 `?token=`。
- 鉴权（机器）：`X-Qms-Key: fck_...`（API Key，read/write 范围）。
- 幂等：POST/PUT 携带 `Idempotency-Key` 头，重复请求返回首次响应。
- 限流：写接口 240 次/分钟/IP。

### Webhook 协议

请求头：`X-Qms-Event`（事件名）、`X-Qms-Timestamp`（Unix 秒）、`X-Qms-Signature`、`X-Qms-Delivery`。
验签（Python 示例）：

```python
import hmac, hashlib
sign = hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
assert hmac.compare_digest(sign, signature)
```

事件清单（15）：inspection.created / inspection.stage / inspection.closed / ncr.created / ncr.stage / ncr.closed / capa.created / capa.step / capa.closed / material.created / material.updated / qdoc.released / key.created / rule.updated / test.ping。

## 2. 认证（4）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | /api/auth/login | `{username, password}` → `{token, user}` |
| GET | /api/auth/me | 当前用户（含 perms）与版本 |
| POST | /api/auth/logout | 注销令牌 |
| PUT | /api/auth/password | `{oldPassword, newPassword}` 修改密码 |

## 3. 首屏（1）

- `GET /api/board` → `{kpi:{inspections,pending,iqcPassRate,ncrOpen,capaOpen,capaOverdue,coqMonth}, byType[], byStatus{}, pareto[], spc{cl,ucl,lcl,outliers,xbars}, todo{}}`

## 4. 主数据（9）

| 方法 | 路径 | 权限 | 说明 |
| --- | --- | --- | --- |
| GET | /api/materials?q= | board.view | 物料列表 |
| POST | /api/materials | mdm.edit | 新建 `{code,name,spec,unit,supplier,critical,keyCharacter}` |
| PUT | /api/materials/{code} | mdm.edit | 更新 |
| GET | /api/suppliers | board.view | 供应商列表 |
| POST | /api/suppliers | supplier.edit | 新建 |
| GET | /api/plans | board.view | 检验方案（含 items） |
| POST | /api/plans | mdm.edit | 新建方案 `{code,name,matCode,itype,aql,il,items[]}` |
| GET | /api/defects | board.view | 缺陷代码 |
| POST | /api/defects | mdm.edit | 新建缺陷 |

## 5. 检验（8+6）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/inspections?itype=&status=&q= | 单据列表（含 items/gates/plan） |
| GET | /api/inspections/{no} | 详情（planOptions 附带） |
| POST | /api/inspections | 新建 `{itype,matCode,supplier,orderNo,process,batchNo,lotSize,aql}`；自动匹配方案载入项目并按 AQL 查表抽样；返回 `{no,sampleSize,planCode}` |
| POST | /api/inspections/{no}/start | 开始检验（待检验→检验中） |
| POST | /api/inspections/{no}/record | 录入 `{records:[{seq,result:OK/NG,badQty,defectCode}]}`；返回 A/B/C 汇总 |
| POST | /api/inspections/{no}/stage | 推进 `{target,verdict?}`，target ∈ 待判定/已判定/已放行/已关闭/已取消；不合格自动开 NCR（返回 ncrNo） |
| GET | /api/inspections/{no} 的 plan 字段 | `{code,sampleSize,ac,re,criticalAc}` |

闸口错误示例（致命一票否决）：

```json
{"code": 400, "message": "存在致命缺陷（A类），不允许判定合格"}
```

## 6. NCR（5）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/ncrs?status=&q= | 列表（含 dueState/dispositions） |
| GET | /api/ncrs/{no} | 详情 |
| POST | /api/ncrs | 手工开立 `{matCode,batchNo,qty,badQty,severity,description}` |
| POST | /api/ncrs/{no}/stage | 推进 `{target, review?, disposition?, owner?, due?, doneDesc?, verified?, verifier?}` |

## 7. CAPA（4）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/capas | 列表（含 progress/nextStep/steps/stepNames） |
| GET | /api/capas/{no} | 详情（含 tasks） |
| POST | /api/capas | 发起 `{problem(≥8字),source,ncrNo?,leader?,members?}` |
| POST | /api/capas/{no}/step | 8D 推进 `{leader?,members?,description?,containment?,rootCause?,actions?,tasks?,effect?,prevention?}` |

## 8. 供应商质量（3）

- `GET /api/supplier/quality?month=` → 月度评分（IRR/PPM/三项得分/等级）
- `POST /api/supplier/score` → `{supplier,q,d,r}` 覆盖当月评分并回写供应商等级
- `GET /api/supplier/ppm` → 供应商不良 PPM 排行

## 9. SPC（3）

- `GET /api/spc/series?process=&char=` → 控制图点列 + limits + cpk
- `GET /api/spc/processes` → 受控特性清单
- `POST /api/spc/series` → 录入测量值 `{process,char,value,usl,lsl,target}`

## 10. 分析与成本（6）

- `GET /api/analysis/pareto?matCode=` → `{list[], weighted[]}`
- `GET /api/analysis/fpy` → 各阶段 RTY 与整机 FPY
- `GET /api/analysis/trend` → 月度合格率与 NCR 趋势
- `GET /api/coq?month=` / `POST /api/coq` / `GET /api/coq/trend`

## 11. 文件与报表（7）

- `GET/POST /api/qdocs`、`POST /api/qdocs/{code}/release`
- `GET /api/reports/kpi`
- `GET /api/reports/inspections.csv`、`/api/reports/ncrs.csv`、`/api/reports/defects.csv`（UTF-8 BOM，Content-Disposition 带飞控QMS品牌文件名）

## 12. 系统（6）

- `GET/PUT /api/settings`（PUT 需 settings.admin，`{items:[{code,value}]}`）
- `GET/POST /api/users`、`PUT /api/users/{username}`
- `GET /api/logs`

## 13. 集成中心（9）

- API Key：`GET/POST /api/integration/keys`、`DELETE /api/integration/keys/{id}`（创建返回明文一次）
- Webhook：`GET/POST /api/integration/webhooks`、`DELETE /{id}`、`POST /{id}/test`
- 映射：`GET/POST /api/integration/maps`、`GET /api/integration/lookup?system=&extId=`
- 增量同步：`GET /api/sync/changes?since={cursor}` → `{changes[], cursor}`（≤500 条）

## 14. 运维（3）

`GET /api/health`（免认证）、`GET /api/version`（免认证）、`GET /api/openapi.json`（免认证）。

## 15. 对接实施建议

1. 先创建只读 Key 拉取主数据对齐编码（物料/供应商）。
2. 检验结果推送使用 `inspection.stage` Webhook 订阅 + `Idempotency-Key` 防重。
3. ERP 采购到货 → 调 `POST /api/inspections` 开 IQC 单；MES 工单完工 → 开 FQC 单。
4. NCR/CAPA 状态同步用增量游标每 5 分钟兜底拉取。
5. 联调期用 `/api/integration/webhooks/{id}/test` 验证验签与退避。
