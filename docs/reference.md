# JSON 合约、CLI 与违规码参考

本页描述 ContactReceipt `0.1.1` 的公开接口。运行时解析器是 trace、policy 与 evidence 的最终约束；`schema` 子命令只把 Draft 2020-12 JSON Schema 写入新文件，便于编辑器提示、收据结构检查和上游预检，它不接收或验证实例文件。

## CLI

### `contactreceipt validate`

```text
contactreceipt validate --trace PATH --policy PATH --evidence PATH --output PATH [--quiet]
```

| 参数 | 必填 | 含义 |
|---|---:|---|
| `--trace PATH` | 是 | 最大 8 MiB 的 UTF-8 中立轨迹 JSON |
| `--policy PATH` | 是 | 最大 8 MiB 的装配策略 JSON |
| `--evidence PATH` | 是 | 最大 8 MiB 的证据清单 JSON |
| `--output PATH` | 是 | 必须尚不存在；父目录必须存在、不得含 `..` 或符号链接组件 |
| `--quiet` | 否 | 不打印一行摘要，收据内容不变 |

输出上限为 16 MiB，文件权限为 `0600`。CLI 拒绝覆盖普通文件或符号链接。

退出码：`0` 表示通过；`1` 表示已生成含违规的失败收据；`2` 表示输入、解析或安全写入错误。

### `contactreceipt schema`

```text
contactreceipt schema {trace,policy,evidence,receipt} --output PATH [--quiet]
```

输出指定对象的 JSON Schema，并使用与收据相同的独占安全写入规则。

### `contactreceipt verify`

```text
contactreceipt verify --receipt PATH [--quiet]
```

删除内存副本中的 `receipt_id` 后重新规范化并计算 SHA-256，以常量时间比较结果。有效返回 `0`，哈希不匹配返回 `1`，读取或 JSON 错误返回 `2`；默认输出 `{"valid":true}` 或 `{"valid":false}`。它只验证内容寻址完整性，不验证完整 schema、来源真实性、数字签名或官方认可。

### 版本

```text
contactreceipt --version
```

## 通用标量约束

- `schema_version` 必须为字符串 `1.0`；
- ID 必须匹配 `^[A-Za-z][A-Za-z0-9_.:-]{0,63}$`；
- SHA-256 必须为 64 个小写十六进制字符；
- 力、力矩和包络数值不得是布尔值、NaN 或无穷，绝对值不得超过 `1e9`；整数时间与序号采用各字段列出的范围；
- 未声明字段、重复 JSON 键、重复 ID 和不支持的枚举都会作为输入错误拒绝，不签发收据。

## Trace

顶层字段：

| 字段 | 类型 | 约束 |
|---|---|---|
| `schema_version` | string | `1.0` |
| `run_id` | ID | 运行的非敏感标识 |
| `environment` | enum | `simulation` 或 `hardware` |
| `source_format` | enum | `neutral_json`、`rosbag2`、`mcap`、`other` |
| `source_artifact_sha256` | SHA-256，可选 | `rosbag2/mcap` 来源若缺失会产生违规 |
| `events` | array | 1..100,000 项 |

事件字段：

| 字段 | 类型 | 约束 |
|---|---|---|
| `seq` | integer | 0..99,999；审计要求等于列表位置 |
| `t_ns` | integer | 0..2^63-1；审计要求单调不减 |
| `kind` | enum | `phase_enter`、`phase_exit`、`contact`、`observation`、`action`、`checkpoint`、`fault` |
| `phase` | ID | 必须由策略声明 |
| `contact_state` | enum，可选 | `none`、`touch`、`stable`、`slip`、`lost`；仅接触事件可用 |
| `force_n` | number[3]，可选 | 三轴力，单位 N |
| `torque_nm` | number[3]，可选 | 三轴力矩，单位 N·m |
| `evidence_refs` | ID[]，可选 | 最多 64 个且不重复 |

## Policy

顶层字段：`assembly_id`、`initial_phase`、`terminal_phase`、`phases` 和 `evidence_requirements` 均必填。阶段数为 1..128。

`initial_phase` 不能有前置条件；`terminal_phase` 必须能从初始阶段沿 `allowed_next` 到达，且不能再允许下一阶段。所有阶段引用必须存在，前置条件图必须无环。

阶段对象：

| 字段 | 类型 | 含义 |
|---|---|---|
| `name` | ID | 唯一阶段名 |
| `requires` | ID[] | 进入前必须已完成的阶段 |
| `allowed_next` | ID[] | 本阶段完成后允许进入的阶段 |
| `required_kinds` | event-kind[] | 阶段退出前至少出现一次的事件类型 |
| `max_duration_ns` | integer，可选 | `phase_exit.t_ns - phase_enter.t_ns` 的最大值 |
| `envelope` | object | 本阶段接触与力/力矩限制 |

包络对象必须含 `allowed_contact_states` 和 `require_wrench_on_contact`，可选 `force_abs_max_n`、`force_norm_max_n`、`torque_abs_max_nm`、`torque_norm_max_nm`。所有限制必须大于零；实测值等于限制时通过。

证据要求对象含 `kind`、`environments` 和 `min_count`（1..100）。支持的 kind：`calibration`、`controller_config`、`dataset_provenance`、`environment_snapshot`、`replay_log`、`robot_description`、`safety_review`、`sensor_sync`、`software_bill`。

## Evidence manifest

顶层 `items` 最多 2,048 项。每项含唯一 `id`、证据 `kind`、`sha256` 和非空 `applies_to`；`source_uri` 是 1..512 个无控制字符的可选字符串。

解析器不访问 `source_uri`，也不打开或重新哈希证据文件。生成清单的人负责确保摘要对应合法原件。

## Receipt

| 字段 | 含义 |
|---|---|
| `tool` | 工具版本与审计算法标识 |
| `subject` | 运行、装配、环境和来源格式 |
| `input_fingerprints` | 规范化 trace、policy、evidence 的 SHA-256 |
| `verdict` | `pass` 或 `fail` |
| `counts` | 事件、完成阶段、已输出违规数量及是否截断 |
| `phase_summary` | 按策略顺序列出的阶段状态和时间 |
| `evidence_checklist` | 当前环境适用的证据要求及匹配 ID |
| `violations` | 稳定排序的违规列表 |
| `failure_replay` | 最早失败事件的列表索引、事件序号和最小列表前缀 SHA-256 |
| `receipt_id` | 对上述收据主体规范化后计算的 `sha256:<hex>` |

收据没有隐式当前时间。`receipt_id` 计算时不包含 `receipt_id` 自身。

## 违规码

| 代码 | 条件 |
|---|---|
| `SEQUENCE_GAP` | `seq` 不等于事件列表位置 |
| `TIME_REVERSED` | 时间早于前一事件 |
| `SOURCE_DIGEST_MISSING` | rosbag2/MCAP 没有原始工件摘要 |
| `PHASE_UNKNOWN` | 事件引用未声明阶段 |
| `INITIAL_PHASE_WRONG` | 首次进入的阶段不是初始阶段 |
| `PHASE_NESTED` | 活动阶段尚未退出又进入另一阶段 |
| `PHASE_REENTERED` | 再次进入已经进入过的阶段 |
| `PHASE_EXIT_WITHOUT_ENTER` | 没有活动阶段却退出 |
| `PHASE_EXIT_MISMATCH` | 退出阶段与活动阶段不同 |
| `EVENT_OUTSIDE_PHASE` | 非进入事件发生时没有活动阶段 |
| `EVENT_PHASE_MISMATCH` | 事件阶段与活动阶段不同 |
| `TRANSITION_FORBIDDEN` | 前一阶段不允许转到目标阶段 |
| `PRECONDITION_MISSING` | 目标阶段的依赖未完成 |
| `REQUIRED_EVENT_MISSING` | 退出前缺少必需事件类型 |
| `PHASE_DURATION_EXCEEDED` | 阶段持续时间超过上限 |
| `PHASE_UNCLOSED` | 轨迹结束时仍有活动阶段 |
| `TERMINAL_PHASE_INCOMPLETE` | 终止阶段未完成 |
| `CONTACT_STATE_MISSING` | 接触事件没有接触状态 |
| `CONTACT_STATE_UNEXPECTED` | 非接触事件带接触状态 |
| `CONTACT_STATE_FORBIDDEN` | 当前阶段不允许该接触状态 |
| `FORCE_SAMPLE_MISSING` | 策略要求的接触力样本缺失 |
| `TORQUE_SAMPLE_MISSING` | 策略要求的接触力矩样本缺失 |
| `FORCE_AXIS_EXCEEDED` / `TORQUE_AXIS_EXCEEDED` | 某轴绝对值超限 |
| `FORCE_NORM_EXCEEDED` / `TORQUE_NORM_EXCEEDED` | 三轴欧氏范数超限 |
| `EVIDENCE_REF_UNKNOWN` | 事件引用未知证据 ID |
| `EVIDENCE_REF_WRONG_ENVIRONMENT` | 证据不适用于当前环境 |
| `EVIDENCE_REQUIREMENT_MISSING` | 当前环境的证据数量不足 |

每项违规含 `code`、`severity=error`、JSON Pointer `path` 和固定格式 `message`；事件违规还含显式 `event_index`、原始 `event_seq` 和 `phase`。最小失败前缀按最小 `event_index` 选择，不受检查器执行顺序影响；`failure_replay.end_index` 明确给出截断位置。

单张收据最多输出 1,000 项违规；若还有违规，`counts.violations_truncated` 为 `true`。这限制了恶意或损坏轨迹造成的输出膨胀。

## Python API

包根公开五个函数：

```python
parse_trace(value: Any) -> Trace
parse_policy(value: Any) -> Policy
parse_evidence(value: Any) -> EvidenceManifest
audit(trace: Trace, policy: Policy, evidence: EvidenceManifest) -> dict[str, Any]
verify_receipt(value: Any) -> bool
```

解析函数在结构错误时抛出 `InputError`。`audit` 不做文件 I/O，不联网，不修改输入。`verify_receipt` 只核验内容哈希，完整结构约束见 `contactreceipt schema receipt` 的输出。

从零开始请看 [教程](tutorial.md)；接入记录请看 [操作指南](how-to.md)。
