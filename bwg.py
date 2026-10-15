"""从环境变量读取 BWG 实例配置；直接运行时查询所有已配置 BWG 实例并输出 JSON。"""

from dataclasses import dataclass, field
import datetime
import json
import math
import os
import sys

from dotenv import load_dotenv
from loguru import logger
import requests


class BwgError(ValueError):
    """可安全展示的 BWG 配置或查询错误。"""


@dataclass(frozen=True)
class BwgServer:
    veid: str
    api_key: str = field(repr=False)

    def get_usage(self) -> dict:
        """查询该实例并转换为供应商无关的报告数据，不返回原始响应。"""
        logger.info('BWG 查询开始，虚拟环境编号={}', self.veid)
        try:
            try:
                response = requests.get(
                    'https://api.64clouds.com/v1/getServiceInfo',
                    params={'veid': self.veid, 'api_key': self.api_key},
                    timeout=15, allow_redirects=False,
                )
            except requests.exceptions.RequestException as error:
                raise BwgError(f'BWG 网络请求失败（{type(error).__name__}）。') from error
            logger.debug('BWG 请求完成，HTTP={}', response.status_code)
            if response.status_code != 200:
                raise BwgError(f'BWG HTTP {response.status_code}。')
            try:
                payload = response.json()
            except ValueError as error:
                raise BwgError('BWG 响应不是有效 JSON。') from error
            usage = parse_bwg_usage(payload)
            logger.debug('BWG 流量转换完成，虚拟环境编号={}', self.veid)
        except BwgError as error:
            logger.error('BWG 查询失败，虚拟环境编号={}，原因={}', self.veid, error)
            raise
        logger.info('BWG 查询完成，虚拟环境编号={}', self.veid)
        return usage


def load_servers() -> dict:
    """读取每个实例的 {名称}_VEID 与 {名称}_API_KEY，不读取其他供应商配置。"""
    servers = {}
    for key, veid in os.environ.items():
        if not key.endswith('_VEID'):
            continue
        name = key[:-len('_VEID')].lower()
        api_key = os.getenv(f'{name.upper()}_API_KEY', '')
        if not name or not veid.isascii() or not veid.isdecimal() or int(veid) <= 0 or not api_key.strip():
            raise BwgError(f'服务器 {name} 的 BWG 虚拟环境编号或 API 密钥未正确配置。')
        servers[name] = BwgServer(veid, api_key)
    return servers


def parse_bwg_usage(payload: dict) -> dict:
    """由 BWG 模块解释额度倍数、原始字段和重置时间戳，向上层提供统一数据。"""
    if not isinstance(payload, dict) or payload.get('error') != 0:
        raise BwgError('BWG API 返回失败，请检查实例和密钥。')
    try:
        quota = float(payload['plan_monthly_data']) * float(payload.get('monthly_data_multiplier', 1))
        used = float(payload['data_counter'])
        if not math.isfinite(quota) or not math.isfinite(used) or quota < 0 or used < 0:
            raise BwgError('BWG 返回无效的流量数据。')
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, BwgError):
            raise
        raise BwgError('BWG 响应缺少有效的流量字段。') from error
    try:
        reset_date = datetime.datetime.fromtimestamp(int(payload['data_next_reset'])).strftime('%Y-%m-%d')
    except (KeyError, TypeError, ValueError, OverflowError, OSError):
        reset_date = 'N/A'
    return {
        'hostname': payload.get('hostname', 'N/A'),
        'ip_addresses': payload.get('ip_addresses', []),
        'location': payload.get('node_location', 'N/A'),
        'plan': payload.get('plan', 'N/A'),
        'quota_bytes': int(quota),
        'used_bytes': int(used),
        'reset_date': reset_date,
    }


def main() -> int:
    """所有参数从环境变量或 .env 读取；标准输出仅包含 JSON，日志写入标准错误。"""
    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level='INFO', backtrace=False, diagnose=False)
    try:
        servers = load_servers()
        if not servers:
            raise BwgError('未找到 BWG 环境变量配置。')
        usages = {name: server.get_usage() for name, server in servers.items()}
    except BwgError as error:
        logger.error('BWG 独立查询失败：{}', error)
        return 1
    print(json.dumps(usages, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
