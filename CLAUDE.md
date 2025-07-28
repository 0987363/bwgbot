# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Telegram bot that monitors server usage for BWG (BandwagonHost) VPS servers. The bot queries the 64clouds API to retrieve server statistics and sends automated reports to configured Telegram groups.

## Main Architecture

- **Single-file application**: `bot.py` contains the entire bot implementation
- **Configuration-driven**: All server and group configurations are loaded from environment variables in `.env`
- **Class-based config management**: `Config` class handles loading and validation of all settings
- **Async Telegram bot**: Built using `python-telegram-bot` library with async/await pattern
- **Scheduled reporting**: Uses job queue for automated reports to multiple groups

## Key Components

### Configuration System
- `Config` class loads server configurations (VEID and API keys) dynamically from environment variables
- Group configurations map Telegram group IDs to specific servers for reporting
- Validates all configurations on startup and logs detailed information

### API Integration
- `get_server_usage()` fetches data from 64clouds API
- `format_server_info()` processes raw API data into structured format
- Handles API errors, network timeouts, and JSON parsing failures

### Bot Commands
- `/usage <server>` - Query individual server usage
- `/report` - Generate report for all servers
- `/getgroupid` - Get current chat/group ID for configuration

### Automated Reporting
- `auto_report_job()` runs periodically based on configured interval
- Sends reports to different groups with their specific server configurations
- Includes error handling and notification to groups on failures

## Development Commands

Since this is a Python project without a package.json, common development tasks would be:

```bash
# Run the bot
python bot.py

# Install dependencies (if requirements.txt exists)
pip install -r requirements.txt

# Install common dependencies manually
pip install python-telegram-bot requests python-dotenv
```

## Environment Configuration

The bot requires a `.env` file with:
- `BOT_TOKEN` - Telegram bot token
- `AUTO_REPORT_SCHEDULE` - Reporting schedule with specific time points (default: daily:09:00)
  - Supported formats:
    - Daily: `daily:HH:MM` (e.g., `daily:09:00`)
    - Weekly: `weekly:DAY:HH:MM` or `DAY:HH:MM` (e.g., `weekly:MON:09:00` or `MON:09:00`)
    - Monthly: `monthly:DD:HH:MM` or `DD:HH:MM` (e.g., `monthly:06:09:00` or `06:09:00`)
  - Supported weekdays: MON, TUE, WED, THU, FRI, SAT, SUN
- Server configs: `{SERVER_NAME}_VEID` and `{SERVER_NAME}_API_KEY`
- Group configs: `GROUP_CONFIG_{N}` in format `group_id:server1,server2`

## Error Handling

The application includes comprehensive error handling:
- Configuration validation on startup
- API request timeouts and HTTP errors
- JSON parsing failures
- Telegram API errors with retry logic
- Logging throughout the application for debugging