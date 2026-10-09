# v26.10.3 更新日志

## 安全修复

- `mcsm_locate` 增加独立权限等级配置 `locate_permission_level`：`0`=所有用户，`1`=管理员或授权用户，`2`=仅管理员，默认 `1`。
- 修复 `allow_arbitrary_llm_commands` 开启时绕过危险命令黑名单的问题；`stop`、`op`、`ban`、`reload` 等危险根命令仍然硬拦截。
- 移除默认白名单中的 `locate`，直接 locate 必须使用带玩家中心的 `mcsm_locate` 工具。
- 白名单持久化失败时恢复内存中的旧值，避免配置面板状态与实际保存状态不一致。

## 白名单配置

- `llm_command_allowlist` 继续支持 AstrBot 配置面板直接编辑。
- 保留原有安全预设：`list`、`seed`、`time`、`weather`、`difficulty`、`spark healthreport`。
- 管理员仍可使用 `/mcsm addcmdwhitelist`、`/mcsm delcmdwhitelist`、`/mcsm listcmdwhitelist` 动态维护白名单。

## 验证

- Python 编译检查通过。
- 配置 JSON 解析与默认值检查通过。
- 安全策略和工具契约回归测试通过。
