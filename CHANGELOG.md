# 更新日志

## 26.10 更新日志
### 新增 `mcsm_locate` LLM 工具
- 使用 Minecraft 玩家名作为执行中心，故调用本指令需要明确玩家用户名；
- 自动生成标准指令：
  ```text
  execute at <玩家名> run locate <类型> <namespace:id>
  ```
- 返回结构化执行状态、日志证据和坐标解析结果；
- 支持基础的中英文坐标结果解析；
- 无法确认结果时不会返回time out
- `mcsm_locate` 拥有独立权限等级配置 `locate_permission_level`。
### 重构 `mcsm_send_command`
- 增加命令长度限制，拦截控制字符；
- 任务返回结构化执行结果；
- 区分命令已接受、执行成功、执行失败和超时等状态
- `llm_command_allowlist` （LLM命令白名）支持 AstrBot 配置面板直接编辑。
- 管理员可使用 `/mcsm addcmdwhitelist`、`/mcsm delcmdwhitelist`、`/mcsm listcmdwhitelist` 动态维护白名单。
### 安全修复
- 修复 `allow_arbitrary_llm_commands` 开启时绕过危险命令黑名单的问题；危险根命令遵循硬拦截。
- 白名单持久化失败时恢复内存中的旧值，避免配置面板状态与实际保存状态不一致。
## 26.08：功能大扩充喵！
- 新增实例命令：restart（重启）/ kill（强制结束）/ info（实例详情，含在线人数）/ update（执行更新命令）
- 新增批量操作：startall / stopall / restartall（仅管理员）
- 新增文件管理命令组：ls / cat / write / mkdir / rm / cp / mv / zip / unzip
- 新增面板用户管理：userlist / useradd / userdel
- 新增节点管理：node（节点详情）/ reconnect（重连节点）
- 新增危险操作：del（删除实例，需二次确认）
- status 命令增强：负载均值、剩余内存、节点地址、面板登录记录
- 新增 LLM 工具调用：11 个 mcsm_* 工具，支持自然语言管理服务器
- 代码重构：实例缓存统一管理，实例操作命令支持自动刷新缓存
## 12.18：修复cmd命令空格不识别问题，新增mcsm log命令
- 问题介绍：如/mcsm cmd id text1 text2只发送text1
- 新增命令：读取条数可以在插件配置自定义
## 12.15：修复了大部分问题，更新了很多东西
之前说想改又忘记了
已修复的主要问题：
1. 授权问题（？）
2. cmd命令出错
3. 以及大大小小的bug
