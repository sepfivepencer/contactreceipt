# ContactReceipt（接触凭证）

ContactReceipt 把民用机器人装配过程的中立 JSON 事件流，转换为可重复、可解释、内容寻址的验证收据。它检查装配阶段、前置条件、接触状态、三轴力/力矩安全包络和仿真到实机证据清单，但不控制机器人，也不执行输入中的命令。

> 状态：`0.1.0-alpha` 是赛前公开原型。它没有接入 CICC 官方仿真器，没有使用官方数据，也没有通过官方评分或实机验证。

## 30 秒体验

需要 Python 3.10 或更高版本；运行时没有第三方依赖。

```bash
python -m pip install -e .
contactreceipt validate \
  --trace examples/trace-pass.json \
  --policy examples/policy.json \
  --evidence examples/evidence.json \
  --output receipt.json
```

成功时命令返回 `0`，违规时仍会写出收据并返回 `1`，输入或输出错误返回 `2`。输出采用规范化 JSON；同一有效输入会产生字节级相同的收据和 `receipt_id`。

复核一张已保存收据的内容完整性：

```bash
contactreceipt verify --receipt receipt.json
```

`verify` 只重算并核对 `receipt_id`，不把收据冒充官方签名，也不替代完整 JSON Schema 校验。

查看一个可复现的失败：

```bash
contactreceipt validate \
  --trace examples/trace-fail.json \
  --policy examples/policy.json \
  --evidence examples/evidence.json \
  --output failed-receipt.json
```

## 为什么有价值

- 控制算法通常只告诉你“任务失败”，ContactReceipt 给出稳定的违规码、JSON Pointer 路径、事件序号和最小失败前缀哈希。
- 仿真与实机材料往往分散，证据清单把标定、控制器配置、环境快照、回放日志和安全复核绑定到同一运行。
- 评测层与 Gazebo、Isaac Sim、ROS 2 bag、MCAP 解耦。上游只需映射到中立事件，不必把控制栈交给本工具。
- 输出不含当前时间，所有输入先规范化再哈希，因此收据可以在 CI、答辩机和复核机上逐字节比较。

## 安全边界

ContactReceipt 是只读验证器，不是机器人控制器。它默认离线，不联网，不加载插件，不反序列化 Python 对象，不运行 shell，也不读取证据项所指向的文件。输出事务逐级拒绝符号链接并持有同一个父目录 `dirfd`，在可用性检查、同目录临时创建和独占硬链接发布之间核对目录身份；现有文件、最终符号链接或父目录替换竞态都会失败关闭。输出父路径不能含 `..`。

本项目只面向工业装配、电力巡检等民用验证。项目不包含反无人机、武器、打击、对抗规划或军用控制功能。

## 文档

- [教程：从事件到第一张收据](docs/tutorial.md)
- [操作指南：接入 ROS 2 bag 或 MCAP 导出](docs/how-to.md)
- [参考：JSON 合约、CLI 与违规码](docs/reference.md)
- [设计解释：为什么使用确定性证据收据](docs/explanation.md)
- [一手资料与竞赛边界](docs/sources.md)

所有文档均可在两次点击内从本页到达。

## 开发验证

```bash
uv sync --extra dev
uv run pytest --cov=contactreceipt --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv build
```

## 名称与创新边界

截至 2026-09-05，GitHub 仓库名搜索 `contactreceipt` 返回 0，PyPI 精确包名返回 404。这只说明检索时未发现同名公开包，不构成商标结论，也不证明“绝对独创”。本项目可核验的新组合是：阶段先决条件、接触/力矩包络、sim-to-real 证据清单和最小失败前缀，被统一进一张确定性内容寻址收据。

## 许可证与 AI 使用

代码采用 [Apache-2.0](LICENSE) 许可证。AI 辅助范围和人工复核要求见 [AI_USAGE.md](AI_USAGE.md)。
