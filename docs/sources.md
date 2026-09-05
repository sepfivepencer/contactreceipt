# 一手资料、赛事范围与检索记录

检索日期：2026-09-05。规则会变化，报名与提交前必须重新核对官网和具体赛项页面。

## CICC/TCEI 官方专站：不对应当前精密装配赛项

- [2026 TCEI“启元杯”无人系统具身智能算法挑战赛专站](https://tcei.c2.org.cn/competition/intro)
- [轮式人形机器人精密装配场景应用挑战赛详情](https://tcei.c2.org.cn/competition/track/wheeled-humanoid-assembly)
- [赛事规则入口](https://tcei.c2.org.cn/competition/tracks)
- [赛事通告入口](https://tcei.c2.org.cn/competition/notice)

概览页把该方向简称为“工业精密装配赛”，但 2026-09-05 读取到的详情页把任务定义为模拟战场中的武器装备抢修与模块换装。详情要求统一使用指定版本的 Alpha Platform，开发大模型驱动的无人抢修车控制算法，并在无人工干预下运行；评分还包含大模型决策和指定多模态模型识别。ContactReceipt 是只读验证器，既不是该控制算法，也不应被包装成该赛项候选。

章程要求参赛作品原创，侵权会导致取消资格和追回奖项；管理规则要求仿真阶段使用官方指定环境、实体阶段使用认证硬件，禁止网络攻击或系统侵入，线下还须签署安全承诺并遵守机器人操作防护。上述条款只用于解释为什么不能把本仓库冒充官方适配或参赛成绩。

ContactReceipt 只为普通工业装配、电力巡检等民用方向提供通用验收基础。它不注册、不参加也不实现上述军用赛项，不接入其 Alpha Platform，不处理官方数据，不提交控制代码，也不在官方设备上运行。

## ROS 2 与 rosbag2

- [ROS 2 Kilted：Recording and playing back data](https://docs.ros.org/en/kilted/Tutorials/Beginner-CLI-Tools/Recording-And-Playing-Back-Data/Recording-And-Playing-Back-Data.html)
- [rosbag2 官方仓库说明](https://github.com/ros2/rosbag2/blob/rolling/README.md)

ROS 2 教程说明 `ros2 bag` 可记录 topic 数据并回放；rosbag2 仓库是 ROS 2 记录系统的一手实现资料。ContactReceipt 没有复制其存储格式，也不声称自己是 rosbag2 验证器。

## MCAP

- [MCAP Format Specification](https://mcap.dev/spec)
- [MCAP 官方仓库的 Python ROS 2 support](https://github.com/foxglove/mcap/tree/main/python/mcap-ros2-support)

MCAP 规范将其定义为保存带时间戳发布/订阅消息的模块化容器，并定义 Schema、Channel、Message、Chunk、索引和校验等记录。ContactReceipt 只规定导出后的中立事件映射；`0.1.1` 不读取 MCAP 二进制文件。

## 名称检索

- [GitHub 仓库名搜索：contactreceipt](https://github.com/search?q=contactreceipt&type=repositories)
- [PyPI 精确项目页：contactreceipt](https://pypi.org/project/contactreceipt/)

截至检索日，GitHub 仓库名搜索计数为 0，PyPI 精确项目页返回 404。这不构成商标检索或法律意见，也不能证明“绝对独创”。README 只主张本仓库中可直接核验的功能组合。
