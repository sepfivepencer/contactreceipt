# How to 将 ROS 2 bag 或 MCAP 记录接入 ContactReceipt

本指南说明如何把团队已有的记录导出为 ContactReceipt 中立 JSON。`0.1.0` 不直接解析 bag 或 MCAP；导出器属于你的仿真/机器人适配层。

## 前置条件

- 已安装 ContactReceipt；
- 你有权使用的 ROS 2 bag、MCAP 或模拟器日志；
- 你知道哪些 topic 分别表示阶段、动作、接触、力和力矩；
- 所有力单位已换算为 N，力矩单位已换算为 N·m，时间已换算为非负纳秒。

## 1. 只记录验收所需 topic

ROS 2 官方教程展示了用 `ros2 bag record` 记录 topic，再用 `ros2 bag info` 和 `ros2 bag play` 检查记录。选择阶段、接触传感器、六维力/力矩和任务检查点 topic，不要把密钥、个人信息或无关相机流放入公开材料。

记录文件本身保持不变。先计算原始工件的 SHA-256：

```bash
python - <<'PY'
import hashlib
from pathlib import Path

source = Path("recording.mcap")
digest = hashlib.sha256()
with source.open("rb") as stream:
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
print(digest.hexdigest())
PY
```

若 rosbag2 输出一个目录，请先用团队可复现的归档流程生成单个工件，再对那个工件计算哈希。ContactReceipt 不规定归档格式，但同一团队必须固定文件顺序、元数据和压缩参数。

## 2. 建立稳定映射

导出器应把上游字段映射为下表，而不是把原始消息整个塞进事件：

| 上游语义 | ContactReceipt 字段 | 约束 |
|---|---|---|
| MCAP `log_time` 或 ROS 记录时钟 | `t_ns` | 非负、列表内单调不减 |
| 导出后的列表位置 | `seq` | 从 0 连续递增 |
| 阶段状态 | `kind=phase_enter/phase_exit`、`phase` | 阶段名必须在策略中声明 |
| 控制意图已发出 | `kind=action` | 仅记录事实，不嵌入可执行命令 |
| 接触分类 | `kind=contact`、`contact_state` | `none/touch/stable/slip/lost` |
| 六维传感器 | `force_n`、`torque_nm` | 两个三元素有限数值数组 |
| 完成性判据 | `kind=checkpoint` | 对应策略的 `required_kinds` |
| 证据关联 | `evidence_refs` | 只放清单中的受限 ID |

MCAP 将带时间戳的发布/订阅消息保存在 Schema、Channel 和 Message 等记录中。建议以 Channel topic 选择消息，以 Message `log_time` 排序；相同时间戳用原记录位置稳定排序。不要以字典遍历顺序作为并列规则。

## 3. 写出中立轨迹

顶层示例：

```json
{
  "schema_version": "1.0",
  "run_id": "sim_trial_042",
  "environment": "simulation",
  "source_format": "mcap",
  "source_artifact_sha256": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
  "events": []
}
```

把映射后的事件填入 `events`。对于 `rosbag2` 或 `mcap`，`source_artifact_sha256` 缺失会形成 `SOURCE_DIGEST_MISSING` 违规。它把收据与原始工件关联，但 ContactReceipt 不读取或验证那个工件。

## 4. 建立仿真到实机证据清单

按团队流程生成证据文件并分别计算 SHA-256。清单可以包含：

- `robot_description`：机器人、末端执行器和传感器版本；
- `controller_config`：控制器参数快照；
- `environment_snapshot`：仿真场景或工作站配置；
- `sensor_sync`、`calibration`：时间同步和标定结果；
- `safety_review`：人工批准的实机安全检查；
- `software_bill`：依赖和镜像清单；
- `replay_log`：可用于团队内部复核的运行记录。

证据项的 `applies_to` 决定它可以支持 `simulation`、`hardware` 或两者。策略中的 `evidence_requirements` 决定当前环境至少需要多少项。

## 5. 从团队安全规范配置包络

不要从示例阈值推导实机参数。请由设备负责人依据机械臂、夹爪、工件、传感器量程、风险评估和官方赛题确定每阶段限制，然后填写：

- `force_abs_max_n`、`torque_abs_max_nm`：每轴绝对值上限；
- `force_norm_max_n`、`torque_norm_max_nm`：三轴欧氏范数上限；
- `allowed_contact_states`：该阶段允许出现的接触分类；
- `require_wrench_on_contact`：接触时是否必须同时提供力和力矩样本。

ContactReceipt 只判断记录是否越界，不会阻停硬件，不能替代机器人自身的安全控制器、急停或人工监督。

## 6. 签发并复核收据

```bash
contactreceipt validate \
  --trace exported-trace.json \
  --policy assembly-policy.json \
  --evidence evidence-manifest.json \
  --output trial-042.receipt.json
```

确认退出码、`verdict`、所有 `violations`、`evidence_checklist` 和三个输入指纹。把原始记录、导出器版本、三份 JSON 和收据作为一个只读审核包保存。

保存或传输后可独立核对内容寻址哈希：

```bash
contactreceipt verify --receipt trial-042.receipt.json
```

这能发现收据内容被改动，但不是数字签名，也不证明记录来源或官方验收状态。

## 验证

在另一台机器上用相同版本重新运行，并比较文件：

```bash
cmp trial-042.receipt.json trial-042.recheck.receipt.json
```

无差异才说明中立输入和验证算法完全相同。

## 故障排除

- `SOURCE_DIGEST_MISSING`：为 rosbag2/MCAP 原始工件提供小写 64 位 SHA-256。
- `TIME_REVERSED`：按纳秒时间和原记录位置做稳定排序。
- `SEQUENCE_GAP`：导出完成后重建 `seq=0..N-1`，不要复用 topic 内部计数器。
- `EVIDENCE_REF_WRONG_ENVIRONMENT`：修正清单的 `applies_to`，不要把仿真证据冒充实机证据。
- `refusing to overwrite output`：保留原收据，使用新的输出文件名。

字段全集见 [参考文档](reference.md)，设计取舍见 [解释文档](explanation.md)。
