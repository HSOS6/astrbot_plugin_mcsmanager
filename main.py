import asyncio
import time
from typing import Dict, Any
import httpx
import json 
import datetime # 引入 datetime 库用于格式化时间戳
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


@register("MCSManager", "5060的3600马力", "MCSManager服务器管理插件Beta", "1.1.18.beta")
class MCSMPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.cooldown_manager = InstanceCooldownManager()
        self.http_client = httpx.AsyncClient(timeout=30.0)
        logger.info("MCSM插件(v10)初始化完成")

    async def terminate(self):
        """插件卸载时关闭HTTP客户端"""
        await self.http_client.aclose()
        logger.info("MCSM插件已卸载")

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
                    return response.json()
                except:
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

    @filter.command("mcsm-help")
    async def mcsm_main(self, event: AstrMessageEvent):
        """显示帮助信息"""
        if not self.is_admin_or_authorized(event):
            return
            
        help_text = """
🛠️ MCSM v10 管理面板：
/mcsm-status - 面板状态概览 (现在仅显示服务器/OS的真实运行时间)
/mcsm-list - 节点实例列表
/mcsm-start [daemonId] [uuid] - 启动实例
/mcsm-stop [daemonId] [uuid] - 停止实例
/mcsm-cmd [daemonId] [uuid] [command] - 发送命令
/mcsm-auth [user_id] - 授权用户
/mcsm-unauth [user_id] - 取消授权
"""
        yield event.plain_result(help_text)

    @filter.command("mcsm-auth", permission_type=filter.PermissionType.ADMIN)
    async def mcsm_auth(self, event: AstrMessageEvent, user_id: str):
        """授权用户"""
        authorized_users = self.config.get("authorized_users", [])
        if user_id in authorized_users:
            yield event.plain_result(f"用户 {user_id} 已在授权列表中")
            return

        authorized_users.append(user_id)
        self.config["authorized_users"] = authorized_users
        self.context.set_config(self.config)
        yield event.plain_result(f"已授权用户 {user_id}")

    @filter.command("mcsm-unauth", permission_type=filter.PermissionType.ADMIN)
    async def mcsm_unauth(self, event: AstrMessageEvent, user_id: str):
        """取消用户授权"""
        authorized_users = self.config.get("authorized_users", [])
        if user_id not in authorized_users:
            yield event.plain_result(f"用户 {user_id} 未获得授权")
            return

        authorized_users.remove(user_id)
        self.config["authorized_users"] = authorized_users
        self.context.set_config(self.config)
        yield event.plain_result(f"已取消用户 {user_id}")

    @filter.command("mcsm-list")
    async def mcsm_list(self, event: AstrMessageEvent):
        """查看实例列表"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        yield event.plain_result("正在获取节点和实例数据，请稍候...")

        overview_resp = await self.make_mcsm_request("/overview")
        
        nodes = []
        if overview_resp.get("status") == 200:
            nodes = overview_resp.get("data", {}).get("remote", [])
        
        if not nodes:
            yield event.plain_result(
                f"⚠️ 无法从 /overview 获取节点信息。API 响应: {overview_resp.get('error', '未知错误')}"
            )
            return

        result = "🖥️ MCSM 实例列表:\n"
        
        for node in nodes:
            node_uuid = node.get("uuid")
            node_name = node.get("remarks") or node.get("ip") or "Unnamed Node"
            
            # 兼容 v10 API，查询指定节点下的实例
            instances_resp = await self.make_mcsm_request(
                "/service/remote_service_instances",
                params={"daemonId": node_uuid, "page": 1, "page_size": 50}
            )

            if instances_resp.get("status") != 200:
                status_code = instances_resp.get('status', '???')
                error_detail = instances_resp.get('error', '未知API错误')
                
                if 'data' in instances_resp and isinstance(instances_resp['data'], str):
                    error_detail = instances_resp['data']

                result += f"\n❌ 节点 {node_name} (ID: {node_uuid}): 获取实例失败 (HTTP {status_code}: {error_detail})\n"
                continue

            data_block = instances_resp.get("data", {})
            # 兼容 API 返回数据结构不一致的情况
            instances = data_block.get("data", []) if isinstance(data_block, dict) else data_block

            if not instances:
                result += f"\n📭 节点 {node_name} (ID: {node_uuid}): 无实例\n"
                continue

            result += f"\n 节点: {node_name}\n"
            for instance in instances:
                # v10 状态码: -1:未知, 0:停止, 1:停止中, 2:启动中, 3:运行中
                status_code = instance.get("status")
                if status_code is None and "info" in instance:
                    status_code = instance["info"].get("status")
                
                status_map = {3: "🟢", 0: "🔴", 1: "🟠", 2: "🟡", -1: "⚪"}
                status_icon = status_map.get(status_code, "⚪")
                
                inst_name = instance.get("config", {}).get("nickname") or "未命名"
                inst_uuid = instance.get("instanceUuid")
                
                result += f"{status_icon} {inst_name}\n- UUID: {inst_uuid}\n"

        yield event.plain_result(result)

    @filter.command("mcsm-start")
    async def mcsm_start(self, event: AstrMessageEvent, daemon_id: str, instance_id: str):
        """启动实例"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        if self.cooldown_manager.check_cooldown(instance_id):
            yield event.plain_result("⏳ 操作太快了，请稍后再试")
            return

        start_resp = await self.make_mcsm_request(
            "/protected_instance/open", 
            method="GET", 
            params={"uuid": instance_id, "daemonId": daemon_id} 
        )
        
        if start_resp.get("status") != 200:
            err = start_resp.get("data") or start_resp.get("error") or "未知错误"
            status_code = start_resp.get("status", "???")
            yield event.plain_result(f"❌ 启动失败: [{status_code}] {err}")
            return

        self.cooldown_manager.set_cooldown(instance_id)
        yield event.plain_result("✅ 启动命令已发送")

    @filter.command("mcsm-stop")
    async def mcsm_stop(self, event: AstrMessageEvent, daemon_id: str, instance_id: str):
        """停止实例"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        if self.cooldown_manager.check_cooldown(instance_id):
            yield event.plain_result("⏳ 操作太快了，请稍后再试")
            return

        stop_resp = await self.make_mcsm_request(
            "/protected_instance/stop",
            method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )

        if stop_resp.get("status") != 200:
            err = stop_resp.get("data") or stop_resp.get("error") or "未知错误"
            status_code = stop_resp.get("status", "???")
            yield event.plain_result(f"❌ 停止失败: [{status_code}] {err}")
            return

        self.cooldown_manager.set_cooldown(instance_id)
        yield event.plain_result("✅ 停止命令已发送")

    @filter.command("mcsm-cmd")
    async def mcsm_cmd(self, event: AstrMessageEvent, daemon_id: str, instance_id: str, command: str):
        """发送命令"""
        if not self.is_admin_or_authorized(event):
            yield event.plain_result("❌ 权限不足")
            return

        cmd_resp = await self.make_mcsm_request(
            "/protected_instance/command",
            method="GET",
            params={
                "uuid": instance_id,
                "daemonId": daemon_id,
                "command": command
            }
        )

        if cmd_resp.get("status") != 200:
            err = cmd_resp.get("data") or cmd_resp.get("error") or "未知错误"
            yield event.plain_result(f"❌ 发送失败: {err}")
            return

        await asyncio.sleep(1) 

        output_resp = await self.make_mcsm_request(
            "/protected_instance/outputlog",
            method="GET",
            params={"uuid": instance_id, "daemonId": daemon_id}
        )

        output = "无返回数据"
        if output_resp.get("status") == 200:
            output = output_resp.get("data") or "无最新日志"
        
        if isinstance(output, str) and len(output) > 500:
            output = "..." + output[-500:]

        yield event.plain_result(f"✅ 命令已发送\n📝 最近日志:\n{output}")

    @filter.command("mcsm-status")
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
        r_avail = r_count.get('available', 0) if isinstance(r_count, dict) else r_avail
        r_total = r_count.get('total', 0) if isinstance(r_count, dict) else r_total

        total_instances = 0
        running_instances = 0
        
        mcsm_version = data.get("version", "未知版本")
        
        # --- 1. 提取并格式化根层级的 time 字段 (数据时间点) ---
        panel_timestamp_ms = overview_resp.get("time")
        panel_time_formatted = "未知时间"
        if panel_timestamp_ms and isinstance(panel_timestamp_ms, (int, float)):
            try:
                # 将毫秒转换为秒，并格式化为可读的日期时间
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
                
                # CPU 占用
                node_cpu_percent = f"{(node_sys.get('cpuUsage', 0) * 100):.2f}%" 
                
                # 内存占用
                mem_total_bytes = node_sys.get("totalmem", 0)
                mem_usage_ratio = node_sys.get("memUsage", 0)
                mem_used_bytes = mem_total_bytes * mem_usage_ratio
                
                mem_used_formatted = format_memory_gb(mem_used_bytes)
                mem_total_formatted = format_memory_gb(mem_total_bytes)
                
                inst_running = inst_info.get("running", 0)
                inst_total = inst_info.get("total", 0)


                status_text += (
                    f"🖥️ 节点: {node_name}\n"
                    f"- 状态: {'🟢 在线' if node.get('available') else '🔴 离线'}\n"
                    f"- 节点版本: {node_version}\n"
                    f"- OS 版本: {os_version}\n"
                    f"- CPU 占用: {node_cpu_percent}\n"
                    f"- 内存占用: {mem_used_formatted} / {mem_total_formatted}\n"
                    f"- 实例数量: {inst_running} 运行中 / {inst_total} 总数\n"
                    "----------------------\n"
                )

        status_text += (
            f"- 在线时间: {os_uptime_formatted}\n" # <-- 面板时间（）
            f"总节点状态: {r_avail} 在线 / {r_total} 总数\n"
            f"总实例运行中: {running_instances} / {total_instances}\n"
            f"提示: 使用 /mcsm-list 查看详情"
        )

        yield event.plain_result(status_text)
