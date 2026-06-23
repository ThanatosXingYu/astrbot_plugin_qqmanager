# astrbot_plugin_qqmanager

AstrBot QQ 群管理插件。

本项目面向 OneBot v11 / `aiocqhttp` 平台，提供常用 QQ 群管理、入群审核、自动风控和可视化配置面板。

## 功能

- 基础群管：禁言、解禁、踢人、拉黑。
- 消息管理：撤回消息。
- 风控：禁词检测、内置禁词、自定义禁词、刷屏检测、宵禁。
- 入群管理：进群白词/黑词、等级门槛、尝试次数、黑名单、进群欢迎、进群禁言、退群通知、退群拉黑、主人 QQ 私信通知、批准/驳回申请。
- 群工具：群友信息。
- 配置：支持 `_conf_schema.json` 配置和 `pages/settings` 前端配置面板。

## 安装与依赖

把本仓库放到 AstrBot 的插件目录：

```bash
AstrBot/data/plugins/astrbot_plugin_qqmanager
```

AstrBot 会根据 `requirements.txt` 安装依赖：

```text
aiocqhttp
aiosqlite
apscheduler
```

## 使用

发送 `/群管帮助` 查看命令说明。

常用命令示例：

```text
/禁言 600 @群友
/解禁 @群友
/踢 @群友
/撤回
/设置禁词 +词1 -词2
/刷屏禁言 300
/进群审核 开
/群管配置
```

## 配置

在 AstrBot 插件详情页打开插件 Page，可进入 `settings` 配置面板。

配置面板支持：

- 默认群模板。
- 按群独立配置。
- 群列表同步和机器人群身份展示。
- 指令权限分级管理。

持久化数据会写入 AstrBot 插件数据目录：

```text
data/plugin_data/astrbot_plugin_qqmanager/
```
