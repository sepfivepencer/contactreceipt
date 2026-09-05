# 一手资料、赛事范围与检索记录

检索日期：2026-09-05。规则会变化，报名与提交前必须重新核对官网和具体赛项页面。

## CICC/TCEI 官方专站

- [2026 TCEI“启元杯”无人系统具身智能算法挑战赛专站](https://tcei.c2.org.cn/competition/intro)
- [赛事规则入口](https://tcei.c2.org.cn/competition/tracks)
- [赛事通告入口](https://tcei.c2.org.cn/competition/notice)

本次从官网公开页面复核到的范围：官网列有轮式人形机器人方向的“工业精密装配赛”；总体采用线上仿真预赛与线下实体决赛；当前报名区间显示为 2026-04-16 至 2026-09-30；章程页面写明全日制学生团队 2–10 人、指导教师 1–2 人，并要求原创；平台规范提到官方指定仿真器和实体赛认证硬件。

ContactReceipt 只为工业装配、电力巡检等民用方向提供通用赛前验收基础。它没有注册参赛、没有接入官方仿真包、没有获得官方数据、没有提交代码，也没有在官方设备上运行。官网同时出现的打击或其他军用赛项不在本项目范围内。

## ROS 2 与 rosbag2

- [ROS 2 Kilted：Recording and playing back data](https://docs.ros.org/en/kilted/Tutorials/Beginner-CLI-Tools/Recording-And-Playing-Back-Data/Recording-And-Playing-Back-Data.html)
- [rosbag2 官方仓库说明](https://github.com/ros2/rosbag2/blob/rolling/README.md)

ROS 2 教程说明 `ros2 bag` 可记录 topic 数据并回放；rosbag2 仓库是 ROS 2 记录系统的一手实现资料。ContactReceipt 没有复制其存储格式，也不声称自己是 rosbag2 验证器。

## MCAP

- [MCAP Format Specification](https://mcap.dev/spec)
- [MCAP 官方仓库的 Python ROS 2 support](https://github.com/foxglove/mcap/tree/main/python/mcap-ros2-support)

MCAP 规范将其定义为保存带时间戳发布/订阅消息的模块化容器，并定义 Schema、Channel、Message、Chunk、索引和校验等记录。ContactReceipt 只规定导出后的中立事件映射；`0.1.0` 不读取 MCAP 二进制文件。

## 名称检索

- [GitHub 仓库名搜索：contactreceipt](https://github.com/search?q=contactreceipt&type=repositories)
- [PyPI 精确项目页：contactreceipt](https://pypi.org/project/contactreceipt/)

截至检索日，GitHub 仓库名搜索计数为 0，PyPI 精确项目页返回 404。这不构成商标检索或法律意见，也不能证明“绝对独创”。README 只主张本仓库中可直接核验的功能组合。
