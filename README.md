# astrbot_plugin_mcsmanager

<div align="center">

_✨ AstrBot 一个可以管理mcsm的小插件 ✨_

适用于MCSM v10以上版本

</div>

> 您的支持是我的最大动力，点个star不迷路！有问题欢迎提issue！

## 介绍
主要功能:
- 通过指令开/关/重启实例、强制结束进程、查看实例详情（在线人数/CPU/内存）
- 通过mcsm cmd指令操作实例
- 查看mcsm节点状态（内存，cpu占用，负载，地址）与节点详细信息
- 查看实例列表、批量启动/停止/重启全部实例
- 查看实例最近日志
- 实例文件管理（列出/查看/写入/删除/新建文件夹/复制/移动/压缩/解压）
- 面板用户管理（列表/创建/删除）
- 节点重连、删除实例（危险操作，需二次确认）
- 支持 LLM 工具调用：开启 AstrBot 的工具调用后，可直接用自然语言让 AI 帮你管理服务器喵

## 📦 安装
### 方式一：从插件市场安装
此插件已登录astrbot插件市场
你可以通过搜索关键词：mcsm 找到本插件
### 方式二：手动安装
```bash
# 克隆仓库到插件目录
cd /path/to/AstrBot/data/plugins
git clone https://github.com/HSOS6/astrbot_plugin_mcsmanager.git

# 重启 AstrBot
```
或者从[此页面](https://github.com/HSOS6/astrbot_plugin_mcsmanager/archive/refs/heads/main.zip)下载，通过从文件安装此插件

## 使用说明
### 注意：插件重启/重载后首次使用实例命令时会自动拉取实例列表（也可手动 mcsm list 刷新编号）喵
本插件仅适用于MCSMv10以上版本
### 插件配置：
<img width="1866" height="893" alt="image" src="https://github.com/user-attachments/assets/a79bdc26-c081-4994-9d62-5656d6493cce" />
所有可选框均为必填配置！
`llm_command_allowlist` 是 LLM 可执行命令白名单，默认预设为：`list`、`seed`、`time`、`locate`、`weather`、`difficulty`、`spark healthreport`。可直接在 AstrBot 插件配置面板中增加或删除条目。

管理员也可以通过聊天指令动态维护白名单（修改后会持久化到插件配置）：
- `/mcsm addcmdwhitelist [命令]` - 添加命令根或完整命令，例如 `/mcsm addcmdwhitelist spark healthreport` 允许LLM自行调用 spark healthreport
- `/mcsm delcmdwhitelist [命令]` - 移除一条命令
- `/mcsm listcmdwhitelist` - 查看当前白名单
白名单指令仅允许管理员调用。高危命令（如 `stop`、`op`、`ban`、`reload` 等）仍会被安全策略拒绝；建议不要开启 `allow_arbitrary_llm_commands` 来替代精细白名单。

MCSManager 面板地址 (mcsm_url)需要填mcsmWeb地址（默认为23333）
APIkey需要从
<img width="1867" height="895" alt="屏幕截图 2025-11-17 175417" src="https://github.com/user-attachments/assets/786c3495-efad-4938-8506-ddf3f23296fb" />
<img width="1867" height="890" alt="image" src="https://github.com/user-attachments/assets/f64221b9-fe76-476b-ab09-438ff14d1d47" />
获取

### 指令介绍
所有实例操作均支持 名称/编号/UUID 三种标识（编号来自 mcsm list）喵

**基础**
- 显示帮助信息 mcsm help
- 查看面板状态 mcsm status （含节点CPU/内存/负载、登录记录）
- 查看实例列表 mcsm list
- 查看节点详细信息 mcsm node

**实例操作**
- 启动实例 mcsm start [实例]
- 停止实例 mcsm stop [实例]
- 重启实例 mcsm restart [实例]
- 强制结束进程 mcsm kill [实例]
- 实例详情 mcsm info [实例] （在线人数/CPU/内存/启动次数）
- 执行更新命令 mcsm update [实例]
- 发送命令 mcsm cmd [实例] [命令]
- 查看最近日志 mcsm log [实例]

**批量操作（仅管理员）**
- 启动全部实例 mcsm startall
- 停止全部实例 mcsm stopall
- 重启全部实例 mcsm restartall

**文件管理（路径相对实例根目录）**
- 列出文件 mcsm ls [实例] [路径]
- 查看文件内容 mcsm cat [实例] [文件]
- 写入文件 mcsm write [实例] [文件] [内容]
- 新建文件夹 mcsm mkdir [实例] [路径]
- 删除文件 mcsm rm [实例] [路径...] （仅管理员）
- 复制文件 mcsm cp [实例] [源] [目标]
- 移动/重命名 mcsm mv [实例] [源] [目标]
- 压缩 mcsm zip [实例] [目标.zip] [源...]
- 解压 mcsm unzip [实例] [压缩包] [目录]

**用户管理（仅管理员）**
- 面板用户列表 mcsm userlist
- 创建面板用户 mcsm useradd [用户名] [密码] [权限1/10]
- 删除面板用户 mcsm userdel [用户ID] 确认

**节点管理（仅管理员）**
- 重连节点 mcsm reconnect [节点名称/Daemon ID/编号]

**危险操作（仅管理员，需二次确认）**
- 删除实例 mcsm del [实例] 确认

**权限管理（仅管理员）**
- 授权用户 mcsm op
- 取消用户授权 mcsm deop
- 添加 LLM 命令白名单 mcsm addcmdwhitelist [命令]（仅管理员）
- 移除 LLM 命令白名单 mcsm delcmdwhitelist [命令]（仅管理员）
- 查看 LLM 命令白名单 mcsm listcmdwhitelist（仅管理员）
- 注：白名单为精确到具体命令则放行整个组，如白名单添加spark，则会放行整个 spark 命令组

### LLM 工具调用
配置好 LLM 并启用函数调用后，AI 可以自动使用以下工具（无需指令，直接说人话即可）：
面板概览 / 实例列表 / 实例详情 / 启动 / 停止 / 重启 / 发送命令 / 获取日志 / 文件列表 / 读文件 / 写文件

例如直接说："帮我看看生存服的在线人数" 或 "重启一下模组服" 

## 🔗 相关链接

- [AstrBot 官方文档](https://astrbot.app)
- [AstrBot GitHub](https://github.com/Soulter/AstrBot)
- 更新部分代码来自[xinghanxu/astrbot_for_mcsmanager](https://github.com/xinghanxu666/xinghanxu_astrbot_for_mcsmanager)
- [MCSManager](https://docs.mcsmanager.com/)

---

## 更新日志
### 26.10.2：LLM 命令白名单配置化
- 新增 AstrBot 配置项 `llm_command_allowlist`，为LLM 可执行命令白名单。
- 新增管理员指令 `mcsm addcmdwhitelist`、`mcsm delcmdwhitelist`、`mcsm listcmdwhitelist`，支持持久化维护白名单。
- 原有 LLM 安全命令白名单迁移为配置项 `llm_command_allowlist`。
- AstrBot 配置面板也可以直接增加、删除白名单条目。

### 26.10.1：创建mcsm_locate工具，标准化的以玩家为中心的locate方法
- 新增公开的 `mcsm_locate` LLM 工具：以指定玩家为中心locate（需要提供玩家名）
- 支持 `structure`、`biome`、`poi` 三类定位。

### 26.08：功能大扩充喵！
- 新增实例命令：restart（重启）/ kill（强制结束）/ info（实例详情，含在线人数）/ update（执行更新命令）
- 新增批量操作：startall / stopall / restartall（仅管理员）
- 新增文件管理命令组：ls / cat / write / mkdir / rm / cp / mv / zip / unzip
- 新增面板用户管理：userlist / useradd / userdel
- 新增节点管理：node（节点详情）/ reconnect（重连节点）
- 新增危险操作：del（删除实例，需二次确认）
- status 命令增强：负载均值、剩余内存、节点地址、面板登录记录
- 新增 LLM 工具调用：11 个 mcsm_* 工具，支持自然语言管理服务器
- 代码重构：实例缓存统一管理，实例操作命令支持自动刷新缓存
### 12.18：修复cmd命令空格不识别问题，新增mcsm log命令
- 问题介绍：如/mcsm cmd id text1 text2只发送text1
- 新增命令：读取条数可以在插件配置自定义
### 12.15：修复了大部分问题，更新了很多东西
之前说想改又忘记了
已修复的主要问题：
1. 授权问题（？）
2. cmd命令出错
3. 以及大大小小的bug
