# astrbot_plugin_mcsmanager

<div align="center">

_✨ AstrBot 一个可以管理mcsm的小插件 ✨_

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![AstrBot](https://img.shields.io/badge/AstrBot-3.4%2B-orange.svg)](https://github.com/Soulter/AstrBot)
[![MCSM](https://img.shields.io/badge/MCSM-9.7.0-blue.svg)](https://github.com/MCSManager/MCSManager)

</div>

## 介绍
主要功能:
- 通过指令开/关mcsm实例
- mcsm节点状态（内存，cpu占用）
- 查看实例列表

## 📦 安装
### 方式一：从插件市场安装
你可以通过搜索关键词：mcsm 找到本插件
### 方式二：手动安装
```bash
# 克隆仓库到插件目录
cd /path/to/AstrBot/data/plugins
git clone https://github.com/your-repo/permission-manager.git

# 重启 AstrBot
```
或者从[此页面](https://github.com/HSOS6/astrbot_plugin_mcsmanager/archive/refs/heads/main.zip)下载，通过从文件安装此插件

## 使用说明
### 插件配置：
<img width="1866" height="893" alt="image" src="https://github.com/user-attachments/assets/a79bdc26-c081-4994-9d62-5656d6493cce" />
所有可选框均为必填配置
MCSManager 面板地址 (mcsm_url)需要填mcsmWeb地址（默认为23333）
APIkey需要从
<img width="1867" height="895" alt="屏幕截图 2025-11-17 175417" src="https://github.com/user-attachments/assets/786c3495-efad-4938-8506-ddf3f23296fb" />
<img width="1867" height="890" alt="image" src="https://github.com/user-attachments/assets/f64221b9-fe76-476b-ab09-438ff14d1d47" />
获取

### 指令介绍
- 显示帮助信息 mcsm-help
- 授权用户 mcsm-auth
- 取消用户授权 mcsm-unauth
- 查看实例列表 mcsm-list
- 启动实例 mcsm-start
- 停止实例 mcsm-stop
- 发送命令 mcsm-cmd
- 查看面板状态 (精简显示 CPU/内存)		mcsm-status

## 🔗 相关链接

- [AstrBot 官方文档](https://astrbot.app)
- [AstrBot GitHub](https://github.com/Soulter/AstrBot)
- [基于xinghanxu_astrbot_for_mcsmanager制作](https://github.com/xinghanxu666/xinghanxu_astrbot_for_mcsmanager)
- [MCSManager](https://docs.mcsmanager.com/)
