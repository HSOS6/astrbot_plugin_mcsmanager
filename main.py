import asyncio
import time
from typing import Dict, Any, List, Tuple, Optional, Set
import httpx
import json 
import datetime 
import re
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

class InstanceCooldownManager:
    """实例操作冷却时间管理"""
    def __init__(self):
        self.cooldowns: Dict[str, float] = {}

    def check_cooldown(self, instance_id: str) -> bool:
        """检查实例是否在冷却中（10秒冷却）"""
        last_time = self.cooldowns.get(instance_id, 0)
        return time.time() - last_time < 10

    def set_cooldown(self, instance_id: str):
        """设置实例冷却时间"""
        self.cooldowns[instance_id] = time.time()

def format_uptime_seconds(seconds: float) -> str:
    """将秒数转换为 天/小时/分钟 的可读格式"""
    if seconds is None or seconds <= 0:
        return "未知"
    seconds = int(seconds)
    # 1. 转换为分钟和剩余秒数
    minutes, seconds = divmod(seconds, 60)
    # 2. 转换为小时和剩余分钟
    hours, minutes = divmod(minutes, 60)
    # 3. 转换为天和剩余小时
    days, hours = divmod(hours, 24)

    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    
    # 如果不足一分钟，则显示秒
    if not parts:
        return f"{seconds}秒"
    
    # 限制只显示最长的两个单位，避免结果太长
    return "".join(parts[:2]) if len(parts) > 1 else "".join(parts)


@register("MCSManager", "星见雅（HSOS6）", "MCSManager服务器管理插件", "2.0.26.08WNMCNXM")
class MCSMPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.cooldown_manager = InstanceCooldownManager()
        self.http_client = httpx.AsyncClient(timeout=30.0)
        # 缓存实例数据，用于名称/编号/UUID查找
        self.instance_data: Dict[str, Any] = {
            "instances": [], # 实例列表 [{'index': str, 'name': str, 'daemon_id': str, 'uuid': str, 'status': int}, ...]
            "name_to_id": {}, # 仅存储唯一名称 -> (daemon_id, uuid) 映射
            "uuid_to_id": {}, # UUID -> (daemon_id, uuid) 映射
            "ambiguous_names": set(), # 存储所有重名实例的名称
        }
        logger.info("MCSM插件(v10)初始化完成喵~出现问题及时提issue！")

    async def terminate(self):
        """插件卸载时关闭HTTP客户端"""
        await self.http_client.aclose()
        logger.info("MCSM插件已卸载")

    def _extract_user_id(self, raw_id: str) -> str:
        """
        从 CQ 码、自定义 At 格式或纯字符串中提取用户 ID
        """
        raw_id = raw_id.strip()
        
        # 1. 匹配标准 QQ-CQ 码格式: [CQ:at,qq=ID]
        match = re.search(r'\[CQ:at,qq=(\d+)\]', raw_id)
        if match:
            return match.group(1)

        # 2. 匹配 AstrBot 自定义 At 格式: [At:ID]
        match = re.search(r'\[At:(\d+)\]', raw_id)
        if match:
            return match.group(1)

        # 3. 匹配 QQ/群聊 @ 格式: @Name(ID) 或其他包含 ID 在括号内的格式
        match = re.search(r'\((\d+)\)', raw_id)
        if match:
            return match.group(1)
        
        # 4. 如果是纯数字 ID
        if raw_id.isdigit():
            return raw_id
            
        # 否则原样返回
        return raw_id

    async def make_mcsm_request(self, endpoint: str, method: str = "GET", params: dict = None, data: dict = None) -> dict:
        """发送请求到MCSManager API"""
        base_url = self.config['mcsm_url'].rstrip('/')
        
        if not endpoint.startswith('/api/'):
            url = f"{base_url}/api{endpoint}"
        else:
            url = f"{base_url}{endpoint}"
        
        query_params = {"apikey": self.config["api_key"]}
        if params:
            query_params.update(params)

        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Requested-With": "XMLHttpRequest"
        }

        try:
            if method.upper() == "GET":
                response = await self.http_client.get(url, params=query_params, headers=headers)
            elif method.upper() == "POST":
                response = await self.http_client.post(url, params=query_params, json=data, headers=headers)
            elif method.upper() == "PUT":
                response = await self.http_client.put(url, params=query_params, json=data, headers=headers)
            elif method.upper() == "DELETE":
                response = await self.http_client.delete(url, params=query_params, json=data, headers=headers)
            else:
                return {"status": 400, "error": "不支持的请求方法"}

            if response.status_code != 200:
                try:
                    # 尝试解析错误信息
                    return response.json()
                except:
                    # 如果不是JSON，返回文本信息
                    return {"status": response.status_code, "error": f"HTTP Error {response.status_code}: {response.text[:100]}..."}

            try:
                return response.json()
            except Exception as json_e:
                return {"status": 500, "error": f"JSON解析失败: {str(json_e)}"}

        except httpx.ConnectTimeout as e:
            return {"status": 504, "error": "连接超时 (ConnectTimeout)"}
        except httpx.ReadTimeout as e:
            return {"status": 504, "error": "读取超时 (ReadTimeout)"}
        except Exception as e:
            logger.error(f"MCSM API请求失败: {str(e)}")
            return {"status": 500, "error": str(e)}

    def is_admin_or_authorized(self, event: AstrMessageEvent) -> bool:
        """检查用户权限"""
        if event.is_admin():
            return True
        return str(event.get_sender_id()) in self.config.get("authorized_users", [])

    def _get_instance_by_identifier(self, identifier: str) -> Optional[Tuple[str, str]]:
        """
        通过实例名、索引或 UUID 查找对应的 (daemonId, instanceUuid)。
        """
        identifier = identifier.strip()
        
        # 1. 尝试通过索引查找 (数字)
        if identifier.isdigit():
            index = int(identifier)
            instances = self.instance_data.get("instances", [])
            # 索引是 1-based, 列表是 0-based
            if 0 < index <= len(instances):
                instance_data = instances[index - 1]
                return instance_data['daemon_id'], instance_data['uuid']
        
        # 2. 尝试通过名称或 UUID 查找 (字符串)
        
        # 检查是否是重名实例，如果是，则不允许通过名称操作
        if identifier in self.instance_data.get("ambiguous_names", set()):
            logger.warning(f"用户尝试通过重名实例名称操作: {identifier}。已拒绝。")
            return None

        if identifier in self.instance_data["name_to_id"]:
            return self.instance_data["name_to_id"][identifier]
        
        if identifier in self.instance_data["uuid_to_id"]:
            return self.instance_data["uuid_to_id"][identifier]

        return None

    # ==================== 通用辅助方法喵 ====================

    def _norm_path(self, target: str) -> str:
        """规范化文件路径：统一转为相对实例根目录的路径喵（守护进程不允许以 / 开头，会导致路径叠加）"""
        target = (target or "").strip()
        if target in ("", ".", "/"):
            return ""
        # 去掉开头的正反斜杠喵
        return target.lstrip("/\\").strip()

    async def _refresh_instance_cache(self) -> Tuple[bool, str]:
        """
        刷新实例缓存：拉取所有节点的实例，构建 名称/编号/UUID 映射喵
        返回 (是否成功, 错误信息)
        """
        overview_resp = await self.make_mcsm_request("/overview")

        nodes: List[Dict[str, Any]] = []
        if overview_resp.get("status") == 200:
            nodes = overview_resp.get("data", {}).get("remote", [])

        if not nodes:
            return False, f"无法从 /overview 获取节点信息。API 响应: {overview_resp.get('error', '未知错误')}"

        all_instances: List[Dict[str, Any]] = []
        node_details: Dict[str, Dict[str, str]] = {}

        # 1. 收集所有节点下的实例喵
        for node in nodes:
            node_uuid = node.get("uuid")
            node_name = node.get("remarks") or node.get("ip") or "Unnamed Node"
            node_details[node_uuid] = {"name": node_name}

            instances_resp = await self.make_mcsm_request(
                "/service/remote_service_instances",
                params={"daemonId": node_uuid, "page": 1, "page_size": 100}
            )
            if instances_resp.get("status") != 200:
                continue

            data_block = instances_resp.get("data", {})
            # 兼容 API 返回数据结构不一致的情况喵
            instances = data_block.get("data", []) if isinstance(data_block, dict) else data_block

            for instance in instances:
                inst_name = instance.get("config", {}).get("nickname") or "未命名"
                inst_uuid = instance.get("instanceUuid")
                status_code = instance.get("status")
                if status_code is None and "info" in instance:
                    status_code = instance["info"].get("status")
                all_instances.append({
                    "name": inst_name,
                    "uuid": inst_uuid,
                    "daemon_id": node_uuid,
                    "status": status_code,
                })

        # 2. 按名称 A-Z 排序喵
        all_instances.sort(key=lambda x: x['name'])

        # 3. 预处理找出重名实例喵
        name_counts: Dict[str, int] = {}
        for instance in all_instances:
            name_counts[instance['name']] = name_counts.get(instance['name'], 0) + 1
        ambiguous_names: Set[str] = {name for name, count in name_counts.items() if count > 1}

        # 4. 重建缓存喵
        self.instance_data["instances"] = []
        self.instance_data["name_to_id"] = {}
        self.instance_data["uuid_to_id"] = {}
        self.instance_data["ambiguous_names"] = ambiguous_names
        self.instance_data["node_details"] = node_details

        for idx, instance in enumerate(all_instances, start=1):
            self.instance_data["instances"].append({
                "index": str(idx),
                "name": instance['name'],
                "uuid": instance['uuid'],
                "daemon_id": instance['daemon_id'],
                "status": instance['status']
            })
            self.instance_data["uuid_to_id"][instance['uuid']] = (instance['daemon_id'], instance['uuid'])
            # 只有唯一名称才加入映射，重名的不加喵
            if instance['name'] not in ambiguous_names:
                self.instance_data["name_to_id"][instance['name']] = (instance['daemon_id'], instance['uuid'])

        return True, ""

    async def _resolve_instance(self, identifier: str) -> Optional[Tuple[str, str, str]]:
        """
        解析实例标识符(名称/编号/UUID) -> (daemonId, uuid, 实例名)喵
        当缓存为空时会自动刷新一次缓存
        """
        ids = self._get_instance_by_identifier(identifier)
        if not ids and not self.instance_data.get("instances"):
            # 缓存是空的，先刷新一次再找喵
            ok, _ = await self._refresh_instance_cache()
            if ok:
                ids = self._get_instance_by_identifier(identifier)
        if not ids:
            return None

        daemon_id, instance_id = ids
        # 查一下友好名称喵
        name = identifier
        for data in self.instance_data.get("instances", []):
            if data['uuid'] == instance_id:
                name = data['name']
                break
        return daemon_id, instance_id, name

    async def _instance_action(self, endpoint: str, identifier: str, action_label: str):
        """
        统一的实例操作封装喵（open/stop/restart/kill 共用一套流程）
        endpoint 形如 /protected_instance/restart
        """
        ids = await self._resolve_instance(identifier)
        if not ids:
            if identifier in self.instance_data.get("ambiguous_names", set()):
                yield f"❌ {action_label}失败: 实例名称 '{identifier}' 重复。请使用 编号/UUID 进行操作。"
            else:
                yield f"❌ 找不到实例: {identifier}。请确认名称/编号/UUID正确，并先运行 /mcsm list 更新列表。"
            return

        daemon_id, instance_id, instance_name = ids

        if self.cooldown_manager.check_cooldown(instance_id):
            yield "⏳ 操作太快了，请稍后再试"
            return

        yield f"⏳ 正在对 {instance_name} 执行{action_label}..."

        resp = await self.make_mcsm_request(
            endpoint, method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )

        if resp.get("status") != 200:
            err = resp.get("data") or resp.get("error") or "未知错误"
            yield f"❌ {action_label}失败: [{resp.get('status', '???')}] {err}"
            return

        self.cooldown_manager.set_cooldown(instance_id)
        yield f"✅ {instance_name} {action_label}命令已发送"

    def _err_text(self, resp: dict) -> str:
        """从 API 响应里提取错误信息的小工具喵"""
        return str(resp.get("data") or resp.get("error") or "未知错误")

    @filter.command("mcsm help")
    async def mcsm_main(self, event: AstrMessageEvent):
        """显示帮助信息"""
        if not self.is_admin_or_authorized(event):
            # 无权限只返回一个基本的提示
            yield event.plain_result("❌ 权限不足。请联系管理员获取授权。")
            return
            
        help_text = """
🛠️ MCSM面板 管理指令：
/mcsm help - 显示此帮助
/mcsm status - 面板状态概览
/mcsm list - 节点实例列表 (按名称A-Z排序，提供编号)
/mcsm node - 节点详细信息列表

> 实例操作 (支持 名称/编号/UUID) ---
/mcsm start [实例] - 启动实例
/mcsm stop [实例] - 停止实例
/mcsm restart [实例] - 重启实例
/mcsm kill [实例] - 强制结束进程
/mcsm info [实例] - 实例详情 (人数/CPU/内存)
/mcsm update [实例] - 执行更新命令
/mcsm cmd [实例] [命令] - 发送命令
/mcsm log [实例] - 查看最近日志

> 批量操作 (仅管理员) ---
/mcsm startall - 启动全部实例
/mcsm stopall - 停止全部实例
/mcsm restartall - 重启全部实例

> 文件管理 (路径相对实例根目录) ---
/mcsm ls [实例] [路径] - 列出文件
/mcsm cat [实例] [文件] - 查看文件内容
/mcsm write [实例] [文件] [内容] - 写入文件
/mcsm mkdir [实例] [路径] - 新建文件夹
/mcsm rm [实例] [路径...] - 删除文件
/mcsm cp [实例] [源] [目标] - 复制
/mcsm mv [实例] [源] [目标] - 移动/重命名
/mcsm zip [实例] [目标.zip] [源...] - 压缩
/mcsm unzip [实例] [压缩包] [目录] - 解压

> 用户管理 (仅管理员) ---
/mcsm userlist - 面板用户列表
/mcsm useradd [用户名] [密码] [权限] - 创建用户
/mcsm userdel [用户ID] 确认 - 删除用户

> 节点管理 (仅管理员) ---
/mcsm reconnect [节点] - 重连节点

> 危险操作 (仅管理员) ---
/mcsm del [实例] 确认 - 删除实例

> 权限管理 (仅管理员)
/mcsm op - 授权用户
/mcsm deop - 取消用户授权
"""
        yield event.plain_result(help_text)

    @filter.command("mcsm op", permission_type=filter.PermissionType.ADMIN)
    async def mcsm_auth(self, event: AstrMessageEvent, user_id: str):
        """授权用户"""
        # 提取用户 ID
        user_id = self._extract_user_id(user_id) 
        
        if not user_id.isdigit():
            yield event.plain_result(f"❌ 授权失败: 请提供有效的用户ID或正确的 @提及格式，当前输入: {user_id}")
            return

        authorized_users = self.config.get("authorized_users", [])
        if user_id in authorized_users:
            yield event.plain_result(f"用户 {user_id} 已在授权列表中")
            return

        authorized_users.append(user_id)
        self.config["authorized_users"] = authorized_users
        
        try:
            self.context.save_config()
            yield event.plain_result(f"✅ 已授权用户 {user_id}")
        except AttributeError:
             yield event.plain_result(f"✅ 授权成功！用户 {user_id} 已添加到配置 ")
        except Exception as e:
             yield event.plain_result(f"❌ 授权失败 (保存配置异常): {str(e)}")

    @filter.command("mcsm deop", permission_type=filter.PermissionType.ADMIN)
    async def mcsm_unauth(self, event: AstrMessageEvent, user_id: str):
        """取消用户授权"""
        # 提取用户 ID
        user_id = self._extract_user_id(user_id)

        if not user_id.isdigit():
            yield event.plain_result(f"❌ 取消授权失败: 请提供有效的用户ID或正确的 @提及格式，当前输入: {user_id}")
            return

        authorized_users = self.config.get("authorized_users", [])
        if user_id not in authorized_users:
            yield event.plain_result(f"用户 {user_id} 未获得授权")
            return

        authorized_users.remove(user_id)
        self.config["authorized_users"] = authorized_users
        
        try:
            self.context.save_config()
            yield event.plain_result(f"✅ 已取消用户 {user_id} 的授权")
        except AttributeError:
             yield event.plain_result(f"✅ 用户 {user_id} 已从配置移除。")
        except Exception as e:
             yield event.plain_result(f"❌ 取消授权失败 (保存配置异常): {str(e)}")

    @filter.command("mcsm list")
    async def mcsm_list(self, event: AstrMessageEvent):
        """查看实例列表"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        yield event.plain_result("正在获取节点和实例数据，请稍候...")

        ok, err = await self._refresh_instance_cache()
        if not ok:
            yield event.plain_result(f"⚠️ {err}")
            return

        node_details = self.instance_data.get("node_details", {})
        ambiguous_names = self.instance_data.get("ambiguous_names", set())

        # v10 状态码: -1:未知, 0:停止, 1:停止中, 2:启动中, 3:运行中喵
        status_map = {3: "🟢", 0: "🔴", 1: "🟠", 2: "🟡", -1: "⚪"}

        result = "🖥️ MCSM 实例列表:\n"
        current_index = 0
        last_daemon_id = None

        for instance in self.instance_data.get("instances", []):
            current_index += 1
            daemon_id = instance['daemon_id']

            # 打印节点分隔符喵
            if daemon_id != last_daemon_id:
                node_name = node_details.get(daemon_id, {}).get("name", "未知节点")
                result += f"\n📂 节点: {node_name}\nDaemon ID: {daemon_id}\n"
                last_daemon_id = daemon_id

            status_icon = status_map.get(instance['status'], "⚪")
            ambiguity_tag = " (⚠️重名)" if instance['name'] in ambiguous_names else ""
            result += f"[{current_index}] {status_icon} {instance['name']}{ambiguity_tag}\n"

        if current_index == 0:
            result += "\n(此面板下暂无实例)\n"

        result += "\n💡 提示: 使用 /mcsm start [名称/编号] 即可操作。"
        if ambiguous_names:
            result += "\n\n⚠️ 注意: 标记 '⚠️重名' 的实例，请使用编号/UUID 进行操作。"

        yield event.plain_result(result)

    @filter.command("mcsm start")
    async def mcsm_start(self, event: AstrMessageEvent, identifier: str):
        """启动实例 (支持名称/编号/UUID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        async for msg in self._instance_action("/protected_instance/open", identifier, "启动"):
            yield event.plain_result(msg)

    @filter.command("mcsm stop")
    async def mcsm_stop(self, event: AstrMessageEvent, identifier: str):
        """停止实例 (支持名称/编号/UUID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        async for msg in self._instance_action("/protected_instance/stop", identifier, "停止"):
            yield event.plain_result(msg)

    @filter.command("mcsm restart")
    async def mcsm_restart(self, event: AstrMessageEvent, identifier: str):
        """重启实例 (支持名称/编号/UUID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        async for msg in self._instance_action("/protected_instance/restart", identifier, "重启"):
            yield event.plain_result(msg)

    @filter.command("mcsm kill")
    async def mcsm_kill(self, event: AstrMessageEvent, identifier: str):
        """强制结束实例进程 (支持名称/编号/UUID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        async for msg in self._instance_action("/protected_instance/kill", identifier, "强制结束"):
            yield event.plain_result(msg)

    @filter.command("mcsm update")
    async def mcsm_update(self, event: AstrMessageEvent, identifier: str):
        """执行实例配置中的更新命令 (支持名称/编号/UUID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}。请先运行 /mcsm list 更新列表。")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/protected_instance/asynchronous",
            method="POST",
            params={"uuid": instance_id, "daemonId": daemon_id, "task_name": "update"}
        )

        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 更新任务提交失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"✅ {instance_name} 更新任务已提交，正在后台执行")

    @filter.command("mcsm info")
    async def mcsm_info(self, event: AstrMessageEvent, identifier: str):
        """查看实例详情 (在线人数/CPU/内存/配置)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}。请先运行 /mcsm list 更新列表。")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/instance", method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 获取详情失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        detail = resp.get("data", {}) or {}
        config = detail.get("config", {}) or {}
        info = detail.get("info", {}) or {}
        process_info = detail.get("processInfo", {}) or {}

        # v10 状态码喵
        status_map = {3: "🟢 运行中", 0: "🔴 已停止", 1: "🟠 停止中", 2: "🟡 启动中", -1: "⚪ 忙碌"}
        lines = [f"📦 实例详情: {instance_name}", f"- 状态: {status_map.get(detail.get('status'), '未知')}"]
        lines.append(f"- 实例类型: {config.get('type', '未知')}")

        # 在线人数（仅部分实例类型支持，-1 表示不支持喵）
        current = info.get("currentPlayers", -1)
        maximum = info.get("maxPlayers", -1)
        if isinstance(current, (int, float)) and current >= 0:
            max_str = str(int(maximum)) if isinstance(maximum, (int, float)) and maximum >= 0 else "?"
            lines.append(f"- 在线人数: {int(current)} / {max_str}")

        version = info.get("version")
        if version:
            lines.append(f"- 版本: {version}")

        started = detail.get("started")
        if isinstance(started, (int, float)):
            lines.append(f"- 累计启动次数: {int(started)}")

        # 进程资源占用（运行中才有数据喵）
        cpu = process_info.get("cpu")
        if isinstance(cpu, (int, float)) and cpu > 0:
            lines.append(f"- 进程 CPU: {cpu:.1f}%")
        mem = process_info.get("memory")
        if isinstance(mem, (int, float)) and mem > 0:
            if mem >= 1024 * 1024:
                lines.append(f"- 进程内存: {mem / 1024 / 1024:.1f} MB")
            else:
                lines.append(f"- 进程内存: {mem:.1f} KB")
        elapsed = process_info.get("elapsed")
        if isinstance(elapsed, (int, float)) and elapsed > 0:
            lines.append(f"- 已运行: {format_uptime_seconds(elapsed)}")

        # 时间信息喵（毫秒时间戳）
        def fmt_ts(ts):
            if not isinstance(ts, (int, float)) or ts <= 0:
                return None
            try:
                return datetime.datetime.fromtimestamp(ts / 1000.0).strftime("%Y-%m-%d %H:%M")
            except Exception:
                return None

        last_dt = fmt_ts(config.get("lastDatetime"))
        if last_dt:
            lines.append(f"- 最近启动: {last_dt}")
        end_dt = fmt_ts(config.get("endTime"))
        lines.append(f"- 到期时间: {end_dt or '永不过期'}")

        start_cmd = config.get("startCommand")
        if start_cmd:
            cmd_display = start_cmd if len(start_cmd) <= 90 else start_cmd[:90] + "..."
            lines.append(f"- 启动命令: {cmd_display}")

        yield event.plain_result("\n".join(lines))

    # ==================== 批量操作命令喵 ====================

    async def _batch_operation(self, operation: str, label: str):
        """批量操作全部实例喵 (operation: open/stop/restart/kill，走 multi_* 接口)"""
        if not self.instance_data.get("instances"):
            ok, err = await self._refresh_instance_cache()
            if not ok:
                yield f"❌ 获取实例列表失败: {err}"
                return

        instances = self.instance_data.get("instances", [])
        if not instances:
            yield "⚠️ 面板下没有任何实例"
            return

        payload = [{"instanceUuid": i["uuid"], "daemonId": i["daemon_id"]} for i in instances]

        yield f"⏳ 正在批量{label} {len(payload)} 个实例..."

        resp = await self.make_mcsm_request(
            f"/instance/multi_{operation}", method="POST", data=payload
        )
        if resp.get("status") != 200:
            yield f"❌ 批量{label}失败: [{resp.get('status', '???')}] {self._err_text(resp)}"
            return

        yield f"✅ 批量{label}命令已发送 (共 {len(payload)} 个实例)"

    @filter.command("mcsm startall")
    async def mcsm_startall(self, event: AstrMessageEvent):
        """启动全部实例 (仅管理员)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return
        async for msg in self._batch_operation("open", "启动"):
            yield event.plain_result(msg)

    @filter.command("mcsm stopall")
    async def mcsm_stopall(self, event: AstrMessageEvent):
        """停止全部实例 (仅管理员)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return
        async for msg in self._batch_operation("stop", "停止"):
            yield event.plain_result(msg)

    @filter.command("mcsm restartall")
    async def mcsm_restartall(self, event: AstrMessageEvent):
        """重启全部实例 (仅管理员)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return
        async for msg in self._batch_operation("restart", "重启"):
            yield event.plain_result(msg)

    @filter.command("mcsm del")
    async def mcsm_del(self, event: AstrMessageEvent, identifier: str, confirm: str = ""):
        """删除实例 (仅管理员，需要二次确认)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return

        if confirm.strip() not in ("确认", "confirm", "确认删除"):
            yield event.plain_result(
                f"⚠️ 删除实例是不可逆操作！\n如确认要删除实例 [{identifier}]，请执行:\n/mcsm del {identifier} 确认\n(实例文件不会被删除)"
            )
            return

        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}。请先运行 /mcsm list 更新列表。")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/instance", method="DELETE",
            params={"daemonId": daemon_id},
            data={"uuids": [instance_id], "deleteFile": False}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 删除失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        # 顺手刷新缓存，保持编号一致喵
        await self._refresh_instance_cache()
        yield event.plain_result(f"✅ 实例 {instance_name} 已删除 (文件保留)")

    @filter.command("mcsm cmd")
    async def mcsm_cmd(self, event: AstrMessageEvent, identifier: str):
        """发送命令 (支持名称/编号/UUID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        raw_msg = event.message_str.strip()
        parts = raw_msg.split(maxsplit=3)
        
        if len(parts) < 4:
            yield event.plain_result("⚠️ 参数不足。用法: /mcsm cmd [名称/编号] [命令内容]")
            return
        
        # parts[0]=mcsm(或带前缀), parts[1]=cmd, parts[2]=identifier, parts[3]=命令内容
        full_command = parts[3].strip()

        # 解析实例标识（缓存为空会自动刷新喵）
        ids = await self._resolve_instance(identifier)
        if not ids:
            if identifier in self.instance_data.get("ambiguous_names", set()):
                 yield event.plain_result(f"❌ 发送失败: 实例名称 '{identifier}' 重复。请使用 /mcsm list 中的 编号/UUID 进行操作。")
            else:
                 yield event.plain_result(f"❌ 找不到实例: {identifier}。请确认名称、编号/UUID 正确，并先运行 /mcsm list 更新列表。")
            return

        daemon_id, instance_id, instance_name = ids

        yield event.plain_result(f"📢 正在向 {instance_name} 发送命令: {full_command}")

        cmd_resp = await self.make_mcsm_request(
            "/protected_instance/command",
            method="GET",
            params={
                "uuid": instance_id,
                "daemonId": daemon_id,
                "command": full_command
            }
        )

        if cmd_resp.get("status") != 200:
            err = cmd_resp.get("data") or cmd_resp.get("error") or "未知错误"
            status_code = cmd_resp.get("status", "???")
            yield event.plain_result(f"❌ 发送失败: [{status_code}] {err}")
            return

        await asyncio.sleep(1) 

        output_resp = await self.make_mcsm_request(
            "/protected_instance/outputlog",
            method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )

        output = "无返回数据"
        if output_resp.get("status") == 200:
            output_data = output_resp.get("data")
            if output_data and isinstance(output_data, str):
                output = output_data or "无最新日志"
        
        if isinstance(output, str) and len(output) > 500:
            output = "..." + output[-500:]

        yield event.plain_result(f"✅ 命令已发送\n📝 最近日志:\n{output}")

    @filter.command("mcsm log")
    async def mcsm_log(self, event: AstrMessageEvent, identifier: str):
        """查看最近日志 (支持名称/编号/UUID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        ids = await self._resolve_instance(identifier)
        if not ids:
            if identifier in self.instance_data.get("ambiguous_names", set()):
                 yield event.plain_result(f"❌ 获取失败: 实例名称 '{identifier}' 重复。请使用 编号/UUID。")
            else:
                 yield event.plain_result(f"❌ 找不到实例: {identifier}。")
            return

        daemon_id, instance_id, instance_name = ids

        log_size = self.config.get("log_size")

        yield event.plain_result(f"📄 正在获取 {instance_name} 的最近 {log_size} 条日志...")

        output_resp = await self.make_mcsm_request(
            "/protected_instance/outputlog",
            method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )

        if output_resp.get("status") != 200:
            err = output_resp.get("error") or "未知错误"
            yield event.plain_result(f"❌ 获取日志失败: {err}")
            return

        log_data = output_resp.get("data", "")
        if not log_data:
            yield event.plain_result("📝 该实例当前没有最新日志。")
            return

        # 处理日志行数
        lines = log_data.strip().split('\n')
        if len(lines) > log_size:
            lines = lines[-log_size:]
        
        formatted_log = "\n".join(lines)
        
        # 长度防爆（可自行调整）
        if len(formatted_log) > 15000:
            formatted_log = "..." + formatted_log[-15000:]

        yield event.plain_result(f"📝 最近日志 ({len(lines)} 条):\n{formatted_log}")

    # ==================== 文件管理命令喵 ====================

    def _parse_file_args(self, event: AstrMessageEvent, maxsplit: int) -> List[str]:
        """
        手动解析消息参数喵（用于路径/内容带空格的场景）
        唤醒前缀已被框架剥离，message_str 形如 "mcsm write 1 file.txt 内容..."
        返回的列表 parts[0]="mcsm", parts[1]=子命令, parts[2]起才是真正参数
        """
        raw_msg = event.message_str.strip()
        parts = raw_msg.split(maxsplit=maxsplit)
        return [p.strip() for p in parts if p]

    @filter.command("mcsm ls")
    async def mcsm_ls(self, event: AstrMessageEvent, identifier: str, target: str = "."):
        """列出实例目录下的文件 (路径相对实例根目录)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return
        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        path = self._norm_path(target)
        display_path = path if path else "(根目录)"

        resp = await self.make_mcsm_request(
            "/files/list", method="GET",
            params={
                "daemonId": daemon_id, "uuid": instance_id,
                "target": path, "page": 0, "page_size": 50
            }
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 获取文件列表失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        data = resp.get("data", {}) or {}
        items = data.get("items", [])
        if not items:
            yield event.plain_result(f"📂 {instance_name} - {display_path}\n(空目录)")
            return

        lines = [f"📂 {instance_name} - {display_path} (共 {data.get('total', len(items))} 项，显示前 {len(items)} 项)"]
        for item in items:
            name = item.get("name", "?")
            if item.get("type") == 1 or item.get("dir"):
                lines.append(f"📁 {name}")
            else:
                size = item.get("size", 0)
                size_str = f"{size / 1024:.1f}KB" if isinstance(size, (int, float)) and size >= 1024 else f"{size}B"
                lines.append(f"📄 {name} ({size_str})")

        yield event.plain_result("\n".join(lines))

    @filter.command("mcsm cat")
    async def mcsm_cat(self, event: AstrMessageEvent, identifier: str, target: str):
        """查看实例中的文本文件内容"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return
        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        path = self._norm_path(target)
        resp = await self.make_mcsm_request(
            "/files/", method="PUT",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"target": path}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 读取失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        content = resp.get("data")
        if content is None:
            yield event.plain_result(f"📄 {path}: (空文件)")
            return

        text = str(content)
        if len(text) > 4000:
            text = text[:4000] + "\n... (内容过长已截断)"
        yield event.plain_result(f"📄 {instance_name}/{path}:\n{text}")

    @filter.command("mcsm write")
    async def mcsm_write(self, event: AstrMessageEvent, identifier: str):
        """写入/覆盖实例中的文本文件"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        # /mcsm write [实例] [路径] [内容...]  内容可以带空格喵
        parts = self._parse_file_args(event, 4)
        if len(parts) < 5:
            yield event.plain_result("⚠️ 参数不足。用法: /mcsm write [实例] [文件路径] [内容]")
            return
        identifier, path, text = parts[2], parts[3], parts[4]

        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/", method="PUT",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"target": self._norm_path(path), "text": text}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 写入失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"✅ 已写入 {instance_name}/{self._norm_path(path)} ({len(text)} 字符)")

    @filter.command("mcsm mkdir")
    async def mcsm_mkdir(self, event: AstrMessageEvent, identifier: str, target: str):
        """在实例中新建文件夹"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return
        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        path = self._norm_path(target)
        resp = await self.make_mcsm_request(
            "/files/mkdir", method="POST",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"target": path}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 创建失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"✅ 已创建文件夹 {instance_name}/{path}")

    @filter.command("mcsm rm")
    async def mcsm_rm(self, event: AstrMessageEvent, identifier: str):
        """删除实例中的文件/文件夹 (可批量，谨慎使用)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return

        # /mcsm rm [实例] [路径1] [路径2]...  路径按空格分割喵
        parts = self._parse_file_args(event, -1)
        if len(parts) < 4:
            yield event.plain_result("⚠️ 参数不足。用法: /mcsm rm [实例] [路径1] [路径2]...")
            return
        identifier = parts[2]
        targets = [self._norm_path(t) for t in parts[3:] if t]

        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/", method="DELETE",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"targets": targets}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 删除失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"🗑️ 已删除 {instance_name} 中的 {len(targets)} 个文件/文件夹")

    @filter.command("mcsm cp")
    async def mcsm_cp(self, event: AstrMessageEvent, identifier: str, source: str, dest: str):
        """复制实例中的文件/文件夹"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return
        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/copy", method="POST",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"targets": [[self._norm_path(source), self._norm_path(dest)]]}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 复制失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"✅ 已复制 {source} -> {dest}")

    @filter.command("mcsm mv")
    async def mcsm_mv(self, event: AstrMessageEvent, identifier: str, source: str, dest: str):
        """移动/重命名实例中的文件"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return
        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/move", method="PUT",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"targets": [[self._norm_path(source), self._norm_path(dest)]]}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 移动失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"✅ 已移动 {source} -> {dest}")

    @filter.command("mcsm zip")
    async def mcsm_zip(self, event: AstrMessageEvent, identifier: str):
        """将实例中的文件/文件夹压缩为 zip"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        # /mcsm zip [实例] [目标.zip] [源1] [源2]...  源路径按空格分割喵
        parts = self._parse_file_args(event, -1)
        if len(parts) < 5:
            yield event.plain_result("⚠️ 参数不足。用法: /mcsm zip [实例] [目标.zip] [源路径...]")
            return
        identifier, dest = parts[2], parts[3]
        targets = [self._norm_path(t) for t in parts[4:] if t]

        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/compress", method="POST",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"type": 1, "code": "utf-8", "source": self._norm_path(dest), "targets": targets}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 压缩失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"📦 压缩任务已提交: {dest} (后台异步执行，可用 /mcsm ls 查看)")

    @filter.command("mcsm unzip")
    async def mcsm_unzip(self, event: AstrMessageEvent, identifier: str, source: str, dest: str = "."):
        """解压实例中的 zip 压缩包"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return
        ids = await self._resolve_instance(identifier)
        if not ids:
            yield event.plain_result(f"❌ 找不到实例: {identifier}")
            return
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/compress", method="POST",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"type": 2, "code": "utf-8", "source": self._norm_path(source), "targets": self._norm_path(dest)}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 解压失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"📦 解压任务已提交: {source} -> {dest} (后台异步执行)")

    @filter.command("mcsm status")
    async def mcsm_status(self, event: AstrMessageEvent):
        """查看面板状态"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        def format_memory_gb(bytes_value):
            if not isinstance(bytes_value, (int, float)) or bytes_value <= 0:
                return "0.00 GB"
            gb = bytes_value / (1024 * 1024 * 1024)
            return f"{gb:.2f} GB"
        
        overview_resp = await self.make_mcsm_request("/overview")
        if overview_resp.get("status") != 200:
            err_msg = overview_resp.get('error', '未知连接错误，请检查配置')
            yield event.plain_result(f"❌ 获取状态失败: {err_msg}")
            return

        data = overview_resp.get("data", {})
        
        r_count = data.get("remoteCount", {})
        r_avail = r_count.get('available', 0) if isinstance(r_count, dict) else 0
        r_total = r_count.get('total', 0) if isinstance(r_count, dict) else 0

        total_instances = 0
        running_instances = 0
        
        mcsm_version = data.get("version", "未知版本")
        
        # --- 1. 提取并格式化根层级的 time 字段 (数据时间点)
        panel_timestamp_ms = overview_resp.get("time")
        panel_time_formatted = "未知时间"
        if panel_timestamp_ms and isinstance(panel_timestamp_ms, (int, float)):
            try:
                dt_object = datetime.datetime.fromtimestamp(panel_timestamp_ms / 1000.0)
                panel_time_formatted = dt_object.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                panel_time_formatted = "时间戳错误"

        os_system_uptime = data.get("system", {}).get("uptime")
        os_uptime_formatted = format_uptime_seconds(os_system_uptime)
        
        logger.info(f"OS/Server raw uptime (from panel system): {os_system_uptime} seconds")


        status_text = (
            f"📊 MCSM v{mcsm_version} 状态概览:\n"
            f"  - 数据时间: {panel_time_formatted}\n"
            "----------------------\n"
        )

        if "remote" in data:
            for i, node in enumerate(data["remote"]):
                node_sys = node.get("system", {})
                inst_info = node.get("instance", {})

                total_instances += inst_info.get("total", 0)
                running_instances += inst_info.get("running", 0)

                node_name = node.get("remarks") or node.get("hostname") or f"Unnamed Node ({i+1})"
                node_version = node.get("version", "未知")

                os_version = node_sys.get("version") or node_sys.get("release") or "未知"

                # CPU 占用喵
                node_cpu_percent = f"{(node_sys.get('cpuUsage', 0) * 100):.2f}%"

                # 内存占用喵
                mem_total_bytes = node_sys.get("totalmem", 0)
                mem_usage_ratio = node_sys.get("memUsage", 0)
                mem_used_bytes = mem_total_bytes * mem_usage_ratio
                mem_free_bytes = node_sys.get("freemem", 0)

                mem_used_formatted = format_memory_gb(mem_used_bytes)
                mem_total_formatted = format_memory_gb(mem_total_bytes)
                mem_free_formatted = format_memory_gb(mem_free_bytes)

                inst_running = inst_info.get("running", 0)
                inst_total = inst_info.get("total", 0)

                # 负载均值喵（仅 Linux 有数据）
                loadavg = node_sys.get("loadavg")
                load_str = ""
                if isinstance(loadavg, list) and len(loadavg) == 3:
                    load_str = f"- 负载 (1/5/15分): {loadavg[0]:.2f} / {loadavg[1]:.2f} / {loadavg[2]:.2f}\n"

                node_ip = node.get("ip", "")
                node_port = node.get("port", "")
                addr_str = f"- 地址: {node_ip}:{node_port}\n" if node_ip else ""

                status_text += (
                    f"🖥️ 节点: {node_name}\n"
                    f"- 状态: {'🟢 在线' if node.get('available') else '🔴 离线'}\n"
                    f"- 节点版本: {node_version}\n"
                    f"- OS 版本: {os_version}\n"
                    f"{addr_str}"
                    f"- CPU 占用: {node_cpu_percent}\n"
                    f"- 内存占用: {mem_used_formatted} / {mem_total_formatted} (剩余 {mem_free_formatted})\n"
                    f"{load_str}"
                    f"- 实例数量: {inst_running} 运行中 / {inst_total} 总数\n"
                    "----------------------\n"
                )

        # 面板自身资源占用喵
        panel_process = data.get("process", {}) or {}
        panel_mem = format_memory_gb(panel_process.get("memory", 0))
        record = data.get("record", {}) or {}

        status_text += (
            f"- 面板在线时间: {os_uptime_formatted}\n"
            f"- 面板内存占用: {panel_mem}\n"
            f"- 登录记录: 成功 {record.get('logined', 0)} 次 | 失败 {record.get('loginFailed', 0)} 次 | 非法访问 {record.get('illegalAccess', 0)} 次\n"
            f"总节点状态: {r_avail} 在线 / {r_total} 总数\n"
            f"实例运行状态: {running_instances} / {total_instances}\n"
            f"提示: 使用 /mcsm list 查看实例 / /mcsm node 查看节点详情"
        )

        yield event.plain_result(status_text)

    # ==================== 节点管理命令喵 ====================

    async def _get_node_list(self) -> Tuple[bool, List[Dict[str, Any]], str]:
        """从 /overview 拉取节点列表喵，返回 (成功?, 节点列表, 错误信息)"""
        resp = await self.make_mcsm_request("/overview")
        if resp.get("status") != 200:
            return False, [], self._err_text(resp)
        return True, resp.get("data", {}).get("remote", []) or [], ""

    @filter.command("mcsm node")
    async def mcsm_node(self, event: AstrMessageEvent):
        """查看节点详细信息列表 (含 Daemon ID)"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        ok, nodes, err = await self._get_node_list()
        if not ok:
            yield event.plain_result(f"❌ 获取节点信息失败: {err}")
            return

        if not nodes:
            yield event.plain_result("⚠️ 面板下没有任何节点")
            return

        def fmt_gb(bytes_value):
            if not isinstance(bytes_value, (int, float)) or bytes_value <= 0:
                return "0GB"
            return f"{bytes_value / (1024 * 1024 * 1024):.1f}GB"

        lines = [f"🖥️ 节点列表 (共 {len(nodes)} 个):"]
        for i, node in enumerate(nodes, start=1):
            sys_info = node.get("system", {}) or {}
            loadavg = sys_info.get("loadavg")
            load_str = ""
            if isinstance(loadavg, list) and len(loadavg) == 3:
                load_str = f" | 负载 {loadavg[0]:.2f}"
            uptime_str = format_uptime_seconds(sys_info.get("uptime"))
            lines.append(
                f"\n[{i}] {'🟢' if node.get('available') else '🔴'} {node.get('remarks') or node.get('ip') or '未命名'}\n"
                f"- Daemon ID: {node.get('uuid', '未知')}\n"
                f"- 地址: {node.get('ip', '?')}:{node.get('port', '?')}\n"
                f"- 系统: {sys_info.get('type', '?')} {sys_info.get('release', '')}\n"
                f"- CPU: {(sys_info.get('cpuUsage', 0) or 0) * 100:.1f}%{load_str}\n"
                f"- 内存: 已用 {fmt_gb((sys_info.get('totalmem', 0) or 0) * (sys_info.get('memUsage', 0) or 0))} / 总 {fmt_gb(sys_info.get('totalmem', 0))}\n"
                f"- 运行时长: {uptime_str} | 守护进程版本: {node.get('version', '?')}"
            )

        yield event.plain_result("\n".join(lines))

    @filter.command("mcsm reconnect")
    async def mcsm_reconnect(self, event: AstrMessageEvent, node_identifier: str):
        """重连指定节点 (支持节点名称/Daemon ID/编号)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return

        ok, nodes, err = await self._get_node_list()
        if not ok:
            yield event.plain_result(f"❌ 获取节点信息失败: {err}")
            return

        # 解析节点标识：编号 / Daemon ID / 名称喵
        target_uuid = None
        node_name = node_identifier
        if node_identifier.isdigit():
            idx = int(node_identifier)
            if 0 < idx <= len(nodes):
                target_uuid = nodes[idx - 1].get("uuid")
                node_name = nodes[idx - 1].get("remarks") or nodes[idx - 1].get("ip") or target_uuid
        if not target_uuid:
            for node in nodes:
                if node.get("uuid") == node_identifier:
                    target_uuid = node.get("uuid")
                    node_name = node.get("remarks") or node.get("ip") or target_uuid
                    break
        if not target_uuid:
            for node in nodes:
                if node.get("remarks") == node_identifier or node.get("ip") == node_identifier:
                    target_uuid = node.get("uuid")
                    node_name = node.get("remarks") or node.get("ip")
                    break
        if not target_uuid:
            yield event.plain_result(f"❌ 找不到节点: {node_identifier}。可用 /mcsm node 查看节点列表。")
            return

        resp = await self.make_mcsm_request(
            "/service/link_remote_service", method="GET",
            params={"uuid": target_uuid}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 重连失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"✅ 节点 {node_name} 重连指令已发送")

    # ==================== 面板用户管理命令喵 ====================

    @filter.command("mcsm userlist")
    async def mcsm_userlist(self, event: AstrMessageEvent):
        """查看面板用户列表 (仅管理员)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return

        resp = await self.make_mcsm_request(
            "/auth/search", method="GET",
            params={"page": 1, "page_size": 30}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 获取用户列表失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        data = resp.get("data", {}) or {}
        users = data.get("data", []) or []
        total = data.get("total", len(users))

        if not users:
            yield event.plain_result("⚠️ 面板下没有任何用户")
            return

        role_map = {1: "用户", 10: "管理员", -1: "封禁"}
        lines = [f"👥 面板用户列表 (共 {total} 人，显示前 {len(users)} 人):"]
        for i, user in enumerate(users, start=1):
            permission = user.get("permission", 1)
            role = role_map.get(permission, str(permission))
            inst_count = len(user.get("instances", []) or [])
            login_time = user.get("loginTime") or "从未登录"
            lines.append(
                f"\n[{i}] {user.get('userName', '?')} ({role})\n"
                f"- UUID: {user.get('uuid', '?')}\n"
                f"- 拥有实例: {inst_count} 个 | 最近登录: {login_time}"
            )

        yield event.plain_result("\n".join(lines))

    @filter.command("mcsm useradd")
    async def mcsm_useradd(self, event: AstrMessageEvent, username: str, password: str, permission: str = "1"):
        """创建面板用户 (仅管理员，权限: 1=用户 10=管理员)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return

        perm = permission.strip()
        if perm not in ("1", "10"):
            yield event.plain_result("⚠️ 权限参数无效，只能是 1(普通用户) 或 10(管理员)")
            return

        resp = await self.make_mcsm_request(
            "/auth", method="POST",
            data={"username": username, "password": password, "permission": int(perm)}
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 创建用户失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        new_uuid = (resp.get("data") or {}).get("uuid", "?") if isinstance(resp.get("data"), dict) else "?"
        yield event.plain_result(f"✅ 用户 {username} 创建成功\nUUID: {new_uuid}")

    @filter.command("mcsm userdel")
    async def mcsm_userdel(self, event: AstrMessageEvent, user_id: str, confirm: str = ""):
        """删除面板用户 (仅管理员，需要二次确认)"""
        if not event.is_admin():
            yield event.plain_result("❌ 此操作仅限管理员")
            return

        if confirm.strip() not in ("确认", "confirm", "确认删除"):
            yield event.plain_result(
                f"⚠️ 删除用户是不可逆操作！\n如确认要删除用户 [{user_id}]，请执行:\n/mcsm userdel {user_id} 确认"
            )
            return

        resp = await self.make_mcsm_request(
            "/auth", method="DELETE",
            data=[user_id.strip()]
        )
        if resp.get("status") != 200:
            yield event.plain_result(f"❌ 删除用户失败: [{resp.get('status', '???')}] {self._err_text(resp)}")
            return

        yield event.plain_result(f"✅ 用户 {user_id} 已删除")

    # ==================== LLM 工具喵 (自然语言调用) ====================

    @filter.llm_tool(name="mcsm_overview")
    async def tool_overview(self, event: AstrMessageEvent) -> str:
        """获取 MCSManager 面板的全局概览信息，包括面板版本、各节点的 CPU/内存占用、节点在线状态、实例运行数量等。"""
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        resp = await self.make_mcsm_request("/overview")
        if resp.get("status") != 200:
            return f"获取失败: {self._err_text(resp)}"
        data = resp.get("data", {})
        # 精简概览信息，方便 AI 阅读喵
        remotes = []
        for node in data.get("remote", []) or []:
            sys_info = node.get("system", {}) or {}
            remotes.append({
                "节点名": node.get("remarks") or node.get("ip"),
                "在线": node.get("available"),
                "CPU占用%": round((sys_info.get("cpuUsage", 0) or 0) * 100, 2),
                "内存占用%": round((sys_info.get("memUsage", 0) or 0) * 100, 2),
                "运行实例": (node.get("instance", {}) or {}).get("running", 0),
                "总实例": (node.get("instance", {}) or {}).get("total", 0),
            })
        summary = {
            "面板版本": data.get("version"),
            "节点数": f"{(data.get('remoteCount', {}) or {}).get('available', 0)}/{(data.get('remoteCount', {}) or {}).get('total', 0)} 在线",
            "节点详情": remotes,
        }
        return json.dumps(summary, ensure_ascii=False)

    @filter.llm_tool(name="mcsm_list_instances")
    async def tool_list_instances(self, event: AstrMessageEvent) -> str:
        """获取 MCSManager 面板下所有服务器的实例列表，包括每个实例的名称、运行状态(运行中/已停止等)、所属节点。无需参数。"""
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        ok, err = await self._refresh_instance_cache()
        if not ok:
            return f"获取实例列表失败: {err}"
        status_map = {3: "运行中", 0: "已停止", 1: "停止中", 2: "启动中", -1: "忙碌"}
        instances = [
            {"编号": i["index"], "名称": i["name"], "状态": status_map.get(i["status"], "未知"), "UUID": i["uuid"]}
            for i in self.instance_data.get("instances", [])
        ]
        return json.dumps(instances, ensure_ascii=False)

    @filter.llm_tool(name="mcsm_instance_info")
    async def tool_instance_info(self, event: AstrMessageEvent, instance: str) -> str:
        """获取指定实例的详细信息，包括运行状态、在线人数、版本、CPU/内存占用、启动次数、启动命令等。
        Args:
            instance(string): 实例名称、编号或 UUID
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        ids = await self._resolve_instance(instance)
        if not ids:
            return f"找不到实例: {instance}。请先用 mcsm_list_instances 查看实例列表"
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/instance", method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )
        if resp.get("status") != 200:
            return f"获取详情失败: {self._err_text(resp)}"

        detail = resp.get("data", {}) or {}
        config = detail.get("config", {}) or {}
        info = detail.get("info", {}) or {}
        process_info = detail.get("processInfo", {}) or {}
        status_map = {3: "运行中", 0: "已停止", 1: "停止中", 2: "启动中", -1: "忙碌"}
        result = {
            "名称": instance_name,
            "状态": status_map.get(detail.get("status"), "未知"),
            "类型": config.get("type"),
            "在线人数": info.get("currentPlayers") if isinstance(info.get("currentPlayers"), (int, float)) and info.get("currentPlayers") >= 0 else "不支持",
            "最大人数": info.get("maxPlayers") if isinstance(info.get("maxPlayers"), (int, float)) and info.get("maxPlayers") >= 0 else None,
            "版本": info.get("version") or None,
            "累计启动次数": detail.get("started"),
            "进程CPU%": process_info.get("cpu"),
            "进程内存": process_info.get("memory"),
            "启动命令": config.get("startCommand"),
        }
        return json.dumps({k: v for k, v in result.items() if v is not None}, ensure_ascii=False)

    @filter.llm_tool(name="mcsm_start_instance")
    async def tool_start_instance(self, event: AstrMessageEvent, instance: str) -> str:
        """启动指定的服务器实例。
        Args:
            instance(string): 实例名称、编号或 UUID
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        last = ""
        async for msg in self._instance_action("/protected_instance/open", instance, "启动"):
            last = msg
        return last

    @filter.llm_tool(name="mcsm_stop_instance")
    async def tool_stop_instance(self, event: AstrMessageEvent, instance: str) -> str:
        """停止指定的服务器实例。
        Args:
            instance(string): 实例名称、编号或 UUID
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        last = ""
        async for msg in self._instance_action("/protected_instance/stop", instance, "停止"):
            last = msg
        return last

    @filter.llm_tool(name="mcsm_restart_instance")
    async def tool_restart_instance(self, event: AstrMessageEvent, instance: str) -> str:
        """重启指定的服务器实例。
        Args:
            instance(string): 实例名称、编号或 UUID
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        last = ""
        async for msg in self._instance_action("/protected_instance/restart", instance, "重启"):
            last = msg
        return last

    @filter.llm_tool(name="mcsm_send_command")
    async def tool_send_command(self, event: AstrMessageEvent, instance: str, command: str) -> str:
        """向运行中的服务器实例控制台发送一条命令，并返回执行后的最新日志。
        Args:
            instance(string): 实例名称、编号或 UUID
            command(string): 要发送到服务器控制台的命令，例如 "say hello" 或 "list"
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        ids = await self._resolve_instance(instance)
        if not ids:
            return f"找不到实例: {instance}。请先用 mcsm_list_instances 查看实例列表"
        daemon_id, instance_id, instance_name = ids

        cmd_resp = await self.make_mcsm_request(
            "/protected_instance/command", method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id, "command": command}
        )
        if cmd_resp.get("status") != 200:
            return f"命令发送失败: {self._err_text(cmd_resp)}"

        # 稍等一下让服务器处理命令喵
        await asyncio.sleep(1)
        output_resp = await self.make_mcsm_request(
            "/protected_instance/outputlog", method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )
        output = ""
        if output_resp.get("status") == 200 and isinstance(output_resp.get("data"), str):
            output = output_resp.get("data") or ""
        if len(output) > 800:
            output = "..." + output[-800:]
        return f"命令已发送。最近日志:\n{output or '(无)'}"

    @filter.llm_tool(name="mcsm_get_log")
    async def tool_get_log(self, event: AstrMessageEvent, instance: str, lines: int = 20) -> str:
        """获取指定实例最近的输出日志。
        Args:
            instance(string): 实例名称、编号或 UUID
            lines(int): 返回的日志行数，默认 20
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        ids = await self._resolve_instance(instance)
        if not ids:
            return f"找不到实例: {instance}。请先用 mcsm_list_instances 查看实例列表"
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/protected_instance/outputlog", method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )
        if resp.get("status") != 200:
            return f"获取日志失败: {self._err_text(resp)}"

        log_data = resp.get("data", "") or ""
        if not log_data:
            return "该实例当前没有日志"
        log_lines = log_data.strip().split("\n")
        try:
            lines = max(1, min(int(lines), 100))
        except (ValueError, TypeError):
            lines = 20
        result = "\n".join(log_lines[-lines:])
        if len(result) > 6000:
            result = "..." + result[-6000:]
        return f"最近 {lines} 行日志:\n{result}"

    @filter.llm_tool(name="mcsm_file_list")
    async def tool_file_list(self, event: AstrMessageEvent, instance: str, path: str = "") -> str:
        """列出指定实例目录下的文件和文件夹。
        Args:
            instance(string): 实例名称、编号或 UUID
            path(string): 相对实例根目录的路径，如 "plugins"，留空表示根目录。不要以 / 开头
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        ids = await self._resolve_instance(instance)
        if not ids:
            return f"找不到实例: {instance}。请先用 mcsm_list_instances 查看实例列表"
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/list", method="GET",
            params={"daemonId": daemon_id, "uuid": instance_id,
                    "target": self._norm_path(path), "page": 0, "page_size": 50}
        )
        if resp.get("status") != 200:
            return f"获取文件列表失败: {self._err_text(resp)}"

        data = resp.get("data", {}) or {}
        items = data.get("items", []) or []
        files = [
            {"名称": i.get("name"), "类型": "文件夹" if (i.get("type") == 1 or i.get("dir")) else "文件", "大小": i.get("size")}
            for i in items
        ]
        return json.dumps({"路径": path or "根目录", "文件": files}, ensure_ascii=False)

    @filter.llm_tool(name="mcsm_read_file")
    async def tool_read_file(self, event: AstrMessageEvent, instance: str, path: str) -> str:
        """读取指定实例中的文本文件内容，例如 server.properties 配置文件。
        Args:
            instance(string): 实例名称、编号或 UUID
            path(string): 相对实例根目录的文件路径，如 "server.properties"
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        ids = await self._resolve_instance(instance)
        if not ids:
            return f"找不到实例: {instance}。请先用 mcsm_list_instances 查看实例列表"
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/", method="PUT",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"target": self._norm_path(path)}
        )
        if resp.get("status") != 200:
            return f"读取失败: {self._err_text(resp)}"
        content = resp.get("data")
        text = str(content) if content is not None else "(空文件)"
        if len(text) > 6000:
            text = text[:6000] + "\n...(内容过长已截断)"
        return text

    @filter.llm_tool(name="mcsm_write_file")
    async def tool_write_file(self, event: AstrMessageEvent, instance: str, path: str, text: str) -> str:
        """向指定实例的文本文件写入内容（会覆盖原内容），例如修改配置文件。
        Args:
            instance(string): 实例名称、编号或 UUID
            path(string): 相对实例根目录的文件路径
            text(string): 要写入的完整文本内容
        """
        if not self.is_admin_or_authorized(event):
            return "权限不足"
        ids = await self._resolve_instance(instance)
        if not ids:
            return f"找不到实例: {instance}。请先用 mcsm_list_instances 查看实例列表"
        daemon_id, instance_id, instance_name = ids

        resp = await self.make_mcsm_request(
            "/files/", method="PUT",
            params={"daemonId": daemon_id, "uuid": instance_id},
            data={"target": self._norm_path(path), "text": text}
        )
        if resp.get("status") != 200:
            return f"写入失败: {self._err_text(resp)}"
        return f"已成功写入 {path}"
