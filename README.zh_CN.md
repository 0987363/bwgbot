中文版|[English](README.md)


# BWG Bot - 服务器使用监控机器人

一个 Telegram 机器人，通过查询 64clouds API 监控 BandwagonHost (BWG) VPS 服务器使用情况，并在指定的时间自动向配置的 Telegram 群组或用户发送报告。

## 功能特性

- 📊 **实时服务器监控**：查询单个服务器使用统计信息
- 📈 **自动报告**：定期向多个群组/用户发送使用报告
- 🔍 **多服务器支持**：监控多个服务器，支持不同配置
- 🎯 **灵活通知**：为不同群组配置不同的服务器
- 📅 **灵活调度**：设置每天、每周或每月的具体报告时间
- 🛡️ **错误处理**：全面的错误处理和日志记录

## 机器人命令

- `/usage <服务器名称>` - 查询单个服务器使用统计信息
- `/report` - 生成所有配置服务器的报告
- `/getgroupid` - 获取当前聊天/群组 ID 用于配置

## 安装步骤

1. **克隆仓库**：
   ```bash
   git clone <仓库地址>
   cd bwgbot
   ```

2. **安装依赖**：
   ```bash
   pip install -r requirements.txt
   ```

3. **配置环境变量**：
   在项目根目录创建 `.env` 文件：
   ```env
   # Telegram 机器人令牌（必需）
   BOT_TOKEN=your_telegram_bot_token_here
   
   # 自动报告调度（可选，默认：daily:09:00）
   # 支持的格式：
   # - 每天：daily:HH:MM（例如：daily:09:00）
   # - 每周：weekly:DAY:HH:MM 或 DAY:HH:MM（例如：MON:09:00）
   # - 每月：monthly:DD:HH:MM 或 DD:HH:MM（例如：06:09:00）
   AUTO_REPORT_SCHEDULE=daily:09:00
   
   # 服务器配置（根据需要添加）
   SERVER1_VEID=your_veid_here
   SERVER1_API_KEY=your_api_key_here
   
   SERVER2_VEID=another_veid_here
   SERVER2_API_KEY=another_api_key_here
   
   # 群组配置（可选，用于自动报告）
   GROUP_CONFIG_1=-1001234567890:server1,server2
   GROUP_CONFIG_2=123456789:server1
   ```

4. **运行机器人**：
   ```bash
   python bot.py
   ```

## 配置说明

### 服务器配置

对于每个要监控的服务器，需要添加两个环境变量：
- `{服务器名称}_VEID`：来自 BWG 控制面板的 VEID
- `{服务器名称}_API_KEY`：来自 BWG 控制面板的 API 密钥

`服务器名称` 可以是任何你选择的标识符（例如：`US1`、`EU1`、`ASIA1`）。

### 群组配置

要启用自动报告，请配置群组/用户：
- 格式：`GROUP_CONFIG_{N}={聊天ID}:{服务器列表}`
- `{N}`：序列号（1、2、3...）
- `{聊天ID}`：Telegram 群组 ID（负数）或用户 ID（正数）
- `{服务器列表}`：逗号分隔的服务器名称列表

**示例**：
```env
# 向群组发送 server1 和 server2 的报告
GROUP_CONFIG_1=-1001234567890:server1,server2

# 向用户发送 server1 的报告
GROUP_CONFIG_2=123456789:server1
```

### 获取聊天 ID

1. 将机器人添加到群组或开始私聊
2. 发送 `/getgroupid` 命令
3. 复制返回的 ID 到 `.env` 文件中

## API 集成

此机器人使用 64clouds API 获取服务器统计信息。您需要：
1. 从 BWG 控制面板获取 VEID（虚拟环境 ID）
2. 从 BWG 控制面板获取 API 密钥

## 调度示例

### 每日报告
```env
# 每天上午 9:00 发送报告
AUTO_REPORT_SCHEDULE=daily:09:00
```

### 每周报告
```env
# 每周一上午 9:00 发送报告
AUTO_REPORT_SCHEDULE=MON:09:00
# 或
AUTO_REPORT_SCHEDULE=weekly:MON:09:00
```

### 每月报告
```env
# 每月 6 日上午 9:00 发送报告
AUTO_REPORT_SCHEDULE=06:09:00
# 或
AUTO_REPORT_SCHEDULE=monthly:06:09:00
```

**支持的星期**：MON, TUE, WED, THU, FRI, SAT, SUN

## 使用示例

### 查询单个服务器
```
/usage server1
```

### 生成完整报告
```
/report
```

### 获取聊天 ID
```
/getgroupid
```

## 错误处理

机器人包含全面的错误处理：
- 网络超时保护
- API 错误检测和报告
- 启动时配置验证
- 优雅的失败处理和用户通知

## 日志记录

机器人记录所有活动，包括：
- 配置加载
- API 请求和响应
- 错误条件
- 报告生成和传送

## 系统要求

- Python 3.7+
- Telegram Bot API 令牌
- 具有 API 访问权限的 BWG 账户

## 许可证

此项目是开源的，根据 MIT 许可证提供。

## 贡献

欢迎贡献！请随时提交 Pull Request。

## 支持

如果您遇到任何问题或有疑问，请在仓库中创建 issue。