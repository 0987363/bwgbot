# main.py

import requests
import json
import datetime
import os
import logging
import asyncio
import re
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量
load_dotenv()

# 配置日志记录
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class Config:
    """配置管理类，从环境变量加载所有配置"""
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        if not self.bot_token:
            raise ValueError("BOT_TOKEN 未在 .env 文件中配置")

        self.auto_report_schedule = self._parse_report_schedule()
        self.servers = self._load_servers()
        self.group_configs = self._load_group_configs()

        logger.info("配置加载完成:")
        logger.info(f"- 服务器数量: {len(self.servers)}")
        logger.info(f"- 群组配置数量: {len(self.group_configs)}")
        logger.info(f"- 自动报告调度: {self._format_schedule_display()}")

    def _parse_report_schedule(self):
        """解析报告调度配置，支持具体时间点"""
        schedule_str = os.getenv('AUTO_REPORT_SCHEDULE', 'daily:09:00')
        
        try:
            return self._parse_schedule_string(schedule_str)
        except ValueError as e:
            logger.warning(f"无效的调度格式: {schedule_str}，错误: {e}，使用默认值 daily:09:00")
            return self._parse_schedule_string('daily:09:00')
    
    def _parse_schedule_string(self, schedule_str):
        """解析调度字符串"""
        schedule_str = schedule_str.strip()
        
        # 支持的格式:
        # 1. daily:HH:MM - 每天指定时间
        # 2. weekly:DAY:HH:MM 或 DAY:HH:MM - 每周指定星期几的指定时间
        # 3. monthly:DD:HH:MM 或 DD:HH:MM - 每月指定日期的指定时间
        
        # 每天调度: daily:09:00
        daily_pattern = r'^daily:(\d{1,2}):(\d{2})$'
        match = re.match(daily_pattern, schedule_str, re.IGNORECASE)
        if match:
            hour, minute = int(match.group(1)), int(match.group(2))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"无效的时间格式: {hour:02d}:{minute:02d}")
            return {'type': 'daily', 'hour': hour, 'minute': minute}
        
        # 每周调度: weekly:MON:09:00 或 MON:09:00
        weekly_pattern = r'^(?:weekly:)?(MON|TUE|WED|THU|FRI|SAT|SUN):(\d{1,2}):(\d{2})$'
        match = re.match(weekly_pattern, schedule_str, re.IGNORECASE)
        if match:
            day_name, hour, minute = match.group(1).upper(), int(match.group(2)), int(match.group(3))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"无效的时间格式: {hour:02d}:{minute:02d}")
            weekdays = {'MON': 0, 'TUE': 1, 'WED': 2, 'THU': 3, 'FRI': 4, 'SAT': 5, 'SUN': 6}
            return {'type': 'weekly', 'weekday': weekdays[day_name], 'hour': hour, 'minute': minute, 'day_name': day_name}
        
        # 每月调度: monthly:06:09:00 或 06:09:00
        monthly_pattern = r'^(?:monthly:)?(\d{1,2}):(\d{1,2}):(\d{2})$'
        match = re.match(monthly_pattern, schedule_str, re.IGNORECASE)
        if match:
            day, hour, minute = int(match.group(1)), int(match.group(2)), int(match.group(3))
            if not (1 <= day <= 31 and 0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError(f"无效的日期时间格式: {day}日 {hour:02d}:{minute:02d}")
            return {'type': 'monthly', 'day': day, 'hour': hour, 'minute': minute}
        
        raise ValueError(f"不支持的调度格式: {schedule_str}")
    
    def _format_schedule_display(self):
        """格式化调度显示"""
        schedule = self.auto_report_schedule
        
        if schedule['type'] == 'daily':
            return f"每天 {schedule['hour']:02d}:{schedule['minute']:02d}"
        elif schedule['type'] == 'weekly':
            return f"每周{schedule['day_name']} {schedule['hour']:02d}:{schedule['minute']:02d}"
        elif schedule['type'] == 'monthly':
            return f"每月{schedule['day']}日 {schedule['hour']:02d}:{schedule['minute']:02d}"
        else:
            return "未知调度类型"

    def _load_servers(self):
        """从环境变量加载所有服务器配置"""
        servers = {}
        server_names = set(key.replace('_VEID', '').lower() for key in os.environ if key.endswith('_VEID'))

        for name in server_names:
            veid = os.getenv(f'{name.upper()}_VEID')
            api_key = os.getenv(f'{name.upper()}_API_KEY')
            if veid and api_key:
                servers[name] = {'veid': veid, 'api_key': api_key}
                logger.info(f"加载服务器配置: {name}")
            else:
                logger.warning(f"服务器 {name} 配置不完整，已跳过。")
        
        if not servers:
            raise ValueError("未在 .env 文件中找到任何有效的服务器配置。")
        return servers

    def _load_group_configs(self):
        """从环境变量加载所有群组报告配置"""
        group_configs = {}
        for key, value in os.environ.items():
            if key.startswith('GROUP_CONFIG_'):
                try:
                    group_id_str, servers_str = value.split(':', 1)
                    group_id = int(group_id_str)
                    server_names = [s.strip().lower() for s in servers_str.split(',') if s.strip()]
                    
                    valid_servers = [s for s in server_names if s in self.servers]
                    invalid_servers = [s for s in server_names if s not in self.servers]

                    if invalid_servers:
                        logger.warning(f"群组 {group_id} 配置中的服务器 {invalid_servers} 不存在，已忽略。")
                    
                    if valid_servers:
                        group_configs[group_id] = valid_servers
                        logger.info(f"加载群组配置: {group_id} -> {valid_servers}")
                    else:
                        logger.warning(f"群组 {group_id} 没有有效的服务器配置，已跳过。")

                except (ValueError, IndexError):
                    logger.error(f"群组配置 {key} 格式错误，应为 'group_id:server1,server2'，已跳过。")
        return group_configs

# 初始化配置
try:
    config = Config()
except ValueError as e:
    logger.critical(f"配置错误，程序终止: {e}")
    exit()

def bytes_to_gb(bytes_value):
    """将字节转换为GB"""
    return round(bytes_value / (1024**3), 2)

def timestamp_to_date(timestamp):
    """将Unix时间戳转换为可读日期"""
    try:
        return datetime.datetime.fromtimestamp(int(timestamp)).strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return "N/A"

def get_server_usage(server_name):
    """通过API获取单个服务器的使用情况"""
    if server_name not in config.servers:
        return None, f"服务器名称 '{server_name}' 不存在。"
    
    server_config = config.servers[server_name]
    url = f"https://api.64clouds.com/v1/getServiceInfo?veid={server_config['veid']}&api_key={server_config['api_key']}"
    
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get('error') != 0:
            return None, f"API 返回错误: {data.get('message', '未知错误')}"
        return data, None
    except requests.exceptions.RequestException as e:
        return None, f"网络请求失败: {e}"
    except json.JSONDecodeError:
        return None, "无法解析API响应 (JSON格式错误)"

def format_server_info(server_name, data):
    """格式化从API获取的服务器数据"""
    multiplier = data.get('monthly_data_multiplier', 1)
    quota = data.get('plan_monthly_data', 0) * multiplier
    used = data.get('data_counter', 0)
    usage_percentage = (used / quota * 100) if quota > 0 else 0
    
    if usage_percentage > 90: status_icon = "🔴"
    elif usage_percentage > 80: status_icon = "🟡"
    else: status_icon = "🟢"

    return {
        'server_name': server_name.upper(),
        'hostname': data.get('hostname', 'N/A'),
        'location': data.get('node_location', 'N/A'),
        'plan': data.get('plan', 'N/A'),
        'quota_gb': bytes_to_gb(quota),
        'used_gb': bytes_to_gb(used),
        'remaining_gb': bytes_to_gb(quota - used),
        'usage_percentage': usage_percentage,
        'reset_date': timestamp_to_date(data.get('data_next_reset')),
        'status_icon': status_icon,
    }

def format_server_usage_text(server_name, data):
    """格式化单个服务器使用信息为文本"""
    if data is None:
        return f"❌ **{server_name.upper()}**: 查询失败"
    
    info = format_server_info(server_name, data)
    return (
        f"🖥️ **服务器 {info['server_name']} 流量详情**\n\n"
        f"📍 **位置:** {info['location']}\n"
        f"📦 **套餐:** {info['plan']}\n\n"
        f"📊 **流量统计:**\n"
        f"  ├─ 已用: `{info['used_gb']}` / `{info['quota_gb']} GB`\n"
        f"  ├─ 剩余: `{info['remaining_gb']} GB`\n"
        f"  └─ 使用率: `{info['usage_percentage']:.1f}%`\n\n"
        f"📅 **流量重置日期:** {info['reset_date']}\n\n"
        f"{info['status_icon']} 状态正常。"
    )

async def generate_servers_report(server_names):
    """生成包含多个服务器信息的文本报告"""
    report_parts = [
        f"📊 **服务器流量报告**",
        f"🕒 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "─" * 40
    ]
    
    for name in server_names:
        data, error = get_server_usage(name)
        if error:
            report_parts.append(f"\n❌ **{name.upper()}**: 查询失败 - {error}")
        else:
            server_text = format_server_usage_text(name, data)
            report_parts.append(f"\n{server_text}")
        
        # 在多个服务器之间添加分隔线
        if name != server_names[-1]:
            report_parts.append("\n" + "─" * 40)
    
    return "\n".join(report_parts)

async def usage_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /usage 命令，查询单个服务器"""
    if not context.args:
        await update.message.reply_text(
            "请指定服务器名称。\n"
            f"用法: `/usage <服务器名>`\n"
            f"支持的服务器: `{', '.join(config.servers.keys())}`",
            parse_mode='Markdown'
        )
        return
    
    server_name = context.args[0].lower()
    status_msg = await update.message.reply_text(f"🔍 正在查询服务器 {server_name.upper()}...")
    
    data, error = get_server_usage(server_name)
    if error:
        await status_msg.edit_text(f"❌ 查询失败: {error}")
        return
        
    response = format_server_usage_text(server_name, data)
    await status_msg.edit_text(response, parse_mode='Markdown')

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /report 命令，手动生成报告"""
    # 默认使用所有服务器
    server_names = list(config.servers.keys())
    
    status_msg = await update.message.reply_text("📊 正在生成所有服务器的报告...")
    report_text = await generate_servers_report(server_names)
    await status_msg.edit_text(report_text, parse_mode='Markdown')

async def get_group_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /getgroupid 命令，获取群组ID"""
    chat_id = update.message.chat_id
    chat_type = update.message.chat.type
    
    if chat_type in ['group', 'supergroup']:
        message = (
            f"ℹ️ **当前群组的 ID 是:**\n`{chat_id}`\n\n"
            f"请将此 ID 用于 `.env` 文件中的 `GROUP_CONFIG` 配置。"
        )
    else:
        message = f"ℹ️ **您的用户 ID 是:**\n`{chat_id}`"
    await update.message.reply_text(message, parse_mode='Markdown')

def calculate_next_run_time(schedule):
    """根据调度配置计算下一次运行时间"""
    import datetime
    
    now = datetime.datetime.now()
    
    if schedule['type'] == 'daily':
        next_run = now.replace(hour=schedule['hour'], minute=schedule['minute'], second=0, microsecond=0)
        if next_run <= now:
            next_run += datetime.timedelta(days=1)
    
    elif schedule['type'] == 'weekly':
        target_weekday = schedule['weekday']
        days_ahead = target_weekday - now.weekday()
        
        if days_ahead < 0:  # 目标日期已过
            days_ahead += 7
        elif days_ahead == 0:  # 就是今天
            target_time = now.replace(hour=schedule['hour'], minute=schedule['minute'], second=0, microsecond=0)
            if target_time <= now:
                days_ahead = 7
        
        next_run = now + datetime.timedelta(days=days_ahead)
        next_run = next_run.replace(hour=schedule['hour'], minute=schedule['minute'], second=0, microsecond=0)
    
    elif schedule['type'] == 'monthly':
        try:
            next_run = now.replace(day=schedule['day'], hour=schedule['hour'], minute=schedule['minute'], second=0, microsecond=0)
            if next_run <= now:
                # 下个月
                if now.month == 12:
                    next_run = next_run.replace(year=now.year + 1, month=1)
                else:
                    next_run = next_run.replace(month=now.month + 1)
        except ValueError:
            # 当月没有这一天（如2月30日），跳到下个月
            if now.month == 12:
                next_run = now.replace(year=now.year + 1, month=1, day=schedule['day'], hour=schedule['hour'], minute=schedule['minute'], second=0, microsecond=0)
            else:
                next_run = now.replace(month=now.month + 1, day=schedule['day'], hour=schedule['hour'], minute=schedule['minute'], second=0, microsecond=0)
    
    return next_run

async def auto_report_job(context: ContextTypes.DEFAULT_TYPE):
    """定时任务，自动发送报告到指定群组"""
    logger.info("开始执行自动报告任务...")
    if not config.group_configs:
        logger.warning("未配置任何群组，自动报告任务跳过。")
        return
        
    for group_id, server_names in config.group_configs.items():
        logger.info(f"为群组 {group_id} 生成报告，服务器: {server_names}")
        try:
            report_text = await generate_servers_report(server_names)
            await context.bot.send_message(
                chat_id=group_id, text=report_text, parse_mode='Markdown'
            )
            logger.info(f"报告已成功发送到群组 {group_id}")
            await asyncio.sleep(1)  # 避免API速率限制
        except Exception as e:
            logger.error(f"为群组 {group_id} 发送报告时失败: {e}")
            try: # 尝试向群组发送错误通知
                await context.bot.send_message(
                    chat_id=group_id, text=f"❌ 自动生成服务器报告时出错: {str(e)}"
                )
            except Exception as notify_e:
                logger.error(f"无法向群组 {group_id} 发送错误通知: {notify_e}")
    
    # 计算下一次运行时间并重新调度
    next_run_time = calculate_next_run_time(config.auto_report_schedule)
    delay = (next_run_time - datetime.datetime.now()).total_seconds()
    
    logger.info(f"下一次自动报告时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 重新调度下一次任务
    context.job_queue.run_once(auto_report_job, when=delay)

def main():
    """启动机器人"""
    application = Application.builder().token(config.bot_token).build()

    # 注册命令处理器
    application.add_handler(CommandHandler("usage", usage_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("getgroupid", get_group_id_command))

    # 设置并启动自动报告任务
    if config.group_configs:
        job_queue = application.job_queue
        
        # 计算首次运行时间
        next_run_time = calculate_next_run_time(config.auto_report_schedule)
        delay = (next_run_time - datetime.datetime.now()).total_seconds()
        
        # 如果延迟时间太短（小于30秒），则延迟到下一个调度时间
        if delay < 30:
            logger.info("首次运行时间过于接近，延迟到下一个调度时间")
            # 模拟执行一次来计算下一次时间
            temp_schedule = config.auto_report_schedule.copy()
            if temp_schedule['type'] == 'daily':
                next_run_time += datetime.timedelta(days=1)
            elif temp_schedule['type'] == 'weekly':
                next_run_time += datetime.timedelta(weeks=1)
            elif temp_schedule['type'] == 'monthly':
                if next_run_time.month == 12:
                    next_run_time = next_run_time.replace(year=next_run_time.year + 1, month=1)
                else:
                    next_run_time = next_run_time.replace(month=next_run_time.month + 1)
            delay = (next_run_time - datetime.datetime.now()).total_seconds()
        
        job_queue.run_once(auto_report_job, when=delay)
        logger.info(f"自动报告任务已设置，{config._format_schedule_display()}，首次运行时间: {next_run_time.strftime('%Y-%m-%d %H:%M:%S')}")
    else:
        logger.warning("未配置群组，将不启动自动报告任务。")

    logger.info("机器人正在启动...")
    application.run_polling()

if __name__ == '__main__':
    main()

