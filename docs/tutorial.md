# 从装配事件到第一张验证收据

你将用仓库自带的轴孔装配示例生成一张通过收据，再制造一次超力违规并定位到具体事件。完成后，你会理解轨迹、策略、证据和收据四个对象怎样连接。

## 你需要准备

- Python 3.10 或更高版本；
- 已克隆的 ContactReceipt 仓库；
- Linux、macOS 或其他支持 Python `dir_fd` 文件操作的平台。

## 第 1 步：安装本地包

在仓库根目录创建虚拟环境并安装：

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install .
```

确认 CLI 可用：

```bash
contactreceipt --version
```

输出应为 `contactreceipt 0.1.0`。

## 第 2 步：签发一张通过收据

```bash
contactreceipt validate \
  --trace examples/trace-pass.json \
  --policy examples/policy.json \
  --evidence examples/evidence.json \
  --output receipt-pass.json
```

你会立即看到一行 JSON 摘要，其中 `"verdict": "pass"` 且 `"violations": 0`。完整收据保存在 `receipt-pass.json`。

## 第 3 步：读懂四个输入与输出

- `trace-pass.json` 是按 `seq` 和单调纳秒时钟排序的事件流；
- `policy.json` 声明 `approach → mate → verify` 阶段、前置条件和每阶段安全包络；
- `evidence.json` 只保存证据元数据及 SHA-256，不把证据文件嵌入收据；
- `receipt-pass.json` 保存三个输入指纹、阶段摘要、证据清单和最终判定。

用 Python 查看收据标识：

```bash
python -c 'import json; print(json.load(open("receipt-pass.json"))["receipt_id"])'
```

## 第 4 步：复现一个接触失败

仓库还提供了超出力包络且没有完成终止阶段的失败轨迹：

```bash
contactreceipt validate \
  --trace examples/trace-fail.json \
  --policy examples/policy.json \
  --evidence examples/evidence.json \
  --output receipt-fail.json
```

命令返回码是 `1`，但收据仍会安全写入。查看第一项违规和失败前缀：

```bash
python - <<'PY'
import json

with open("receipt-fail.json", encoding="utf-8") as stream:
    receipt = json.load(stream)
print(receipt["violations"][0])
print(receipt["failure_replay"])
PY
```

`path` 指向违规字段，`event_seq` 指向事件，`prefix_sha256` 指纹覆盖从开头到首次失败位置的最小列表前缀。

## 第 5 步：验证确定性

输出文件不能被覆盖，所以换一个文件名再次运行通过示例：

```bash
contactreceipt validate \
  --trace examples/trace-pass.json \
  --policy examples/policy.json \
  --evidence examples/evidence.json \
  --output receipt-pass-2.json \
  --quiet
cmp receipt-pass.json receipt-pass-2.json
```

`cmp` 没有输出且返回 `0`，说明两次收据字节完全一致。

## 你完成了什么

你已经把一次民用装配运行转换为可复核的内容寻址收据，并用最小失败前缀定位了违规。下一步可阅读 [How to 接入 ROS 2 bag 或 MCAP](how-to.md)，再查阅完整的 [JSON 与 CLI 参考](reference.md)。
