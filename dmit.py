"""从环境变量读取 DMIT 服务编号、Cookie 和 User-Agent；直接运行输出所有实例的流量 JSON。"""

from dataclasses import dataclass, field
import os
from http.cookies import CookieError, SimpleCookie
import calendar
import datetime
import ipaddress
import json
import math
import sys
from typing import Optional

from dotenv import load_dotenv
from loguru import logger
import requests


class DmitError(ValueError):
    """可安全展示给用户的 DMIT 查询错误，不包含凭据或原始响应。"""


class DmitAuthError(DmitError):
    """长效认证或 Cloudflare 通行资格失效，需要人工更新初始凭据。"""


RENEW_AUTH_MESSAGE = (
    '请在浏览器重新登录并勾选“记住我”，更新对应服务器的 '
    '`DMIT_COOKIE` 和 `DMIT_USER_AGENT` 环境变量后重启机器人。'
)


def next_reset_date(next_due_date: str, now: Optional[datetime.datetime] = None) -> str:
    """按控制台的 UTC 月度规则计算重置日期，续费日只提供每月的日号。"""
    reset_day = datetime.date.fromisoformat(next_due_date).day
    now = now or datetime.datetime.now(datetime.timezone.utc)
    now = now.astimezone(datetime.timezone.utc)
    year, month = now.year, now.month
    day = min(reset_day, calendar.monthrange(year, month)[1])
    reset = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    if reset < now:
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
        day = min(reset_day, calendar.monthrange(year, month)[1])
        reset = datetime.datetime(year, month, day, tzinfo=datetime.timezone.utc)
    return reset.date().isoformat()


def parse_dmit_usage(payload: dict, service_id: str) -> dict:
    """只提取报告字段；返回现有报告数据契约中的字节数及 UTC 重置日期。"""
    if not isinstance(payload, dict) or payload.get('result') != 'success':
        raise DmitError(f'DMIT 未返回成功结果，请检查服务访问权限和登录态。{RENEW_AUTH_MESSAGE}')
    detail = payload.get('success')
    if not isinstance(detail, dict):
        raise DmitError('DMIT 响应缺少服务详情。')
    try:
        if str(detail['serviceid']) != service_id:
            raise DmitError('DMIT 返回的服务记录编号与请求不一致。')
        used, quota = float(detail['bwusage']), float(detail['bwlimit'])
        if not math.isfinite(used) or not math.isfinite(quota) or used < 0 or quota <= 0:
            raise DmitError('DMIT 套餐流量数据无效；当前查询仅支持有流量配额的实例。')
        reset_date = next_reset_date(detail['nextduedate'])
        addresses = []
        for field in ('dedicatedip', 'assignedips'):
            for address in detail.get(field, '').split():
                ipaddress.ip_interface(address)
                addresses.append(address)
        hostname = detail['hostname']
        if not isinstance(hostname, str):
            raise DmitError('DMIT 主机名字段格式无效。')
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        if isinstance(error, DmitError):
            raise
        raise DmitError('DMIT 响应字段缺失或格式错误，不能作为流量数据使用。') from error
    return {
        'hostname': hostname,
        'ip_addresses': addresses,
        'plan': 'DMIT VPS',
        'location': 'N/A',
        'quota_bytes': int(quota * 1024**2),
        'used_bytes': int(used * 1024**2),
        'reset_date': reset_date,
    }


@dataclass(frozen=True)
class DmitServer:
    service_id: str
    cookie: str = field(repr=False)
    user_agent: str = field(repr=False)

    _session: requests.Session = field(default_factory=requests.Session, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        cookies = parse_auth_cookies(self.service_id, self.cookie, self.user_agent)
        self._session.headers.update({'User-Agent': self.user_agent, 'Accept': 'application/json'})
        for name, morsel in cookies.items():
            # 与已验证的 Cookie 域一致，避免后续 Set-Cookie 产生同名重复值。
            domain = '.dmit.io' if name == 'cf_clearance' else 'www.dmit.io'
            self._session.cookies.set(name, morsel.value, domain=domain, path='/', secure=True)

    def get_usage(self) -> dict:
        """复用该实例的会话及服务端更新的 Cookie，只返回白名单流量数据。"""
        service_id = self.service_id
        logger.info('DMIT 套餐查询开始，服务记录编号={}', service_id)
        try:
            try:
                response = self._session.get(
                    'https://www.dmit.io/clientarea.php',
                    params={'action': 'productdetails', 'id': service_id, 'json': '1',
                            'pure': '1', 'page': 'standard', 'subaction': 'whmcsdetail'},
                    timeout=25, allow_redirects=False,
                )
            except requests.exceptions.RequestException as error:
                raise DmitError(f'DMIT 网络请求失败（{type(error).__name__}）。') from error
            logger.debug('DMIT 请求完成，服务记录编号={}，HTTP={}', service_id, response.status_code)
            if response.status_code in (301, 302, 303, 307, 308, 401, 403):
                raise DmitAuthError(f'DMIT 认证失败或需要 Cloudflare 验证（HTTP {response.status_code}）。{RENEW_AUTH_MESSAGE}')
            if response.status_code != 200:
                raise DmitError(f'DMIT 服务返回 HTTP {response.status_code}。')
            try:
                payload = response.json()
            except ValueError as error:
                raise DmitAuthError(f'DMIT 返回非 JSON 内容，登录态可能失效或需要浏览器验证。{RENEW_AUTH_MESSAGE}') from error
            usage = parse_dmit_usage(payload, service_id)
            logger.debug('DMIT 流量字段校验完成，服务记录编号={}', service_id)
        except DmitError as error:
            logger.error('DMIT 套餐查询失败，服务记录编号={}，原因={}', service_id, error)
            raise
        logger.info('DMIT 套餐查询完成，服务记录编号={}', service_id)
        return usage


def load_servers() -> dict:
    """从每个服务器前缀下的 DMIT_SERVICE_ID、DMIT_COOKIE、DMIT_USER_AGENT 读取配置。"""
    servers = {}
    for key, service_id in os.environ.items():
        if not key.endswith('_DMIT_SERVICE_ID'):
            continue
        name = key[:-len('_DMIT_SERVICE_ID')].lower()
        cookie = os.getenv(f'{name.upper()}_DMIT_COOKIE', '')
        user_agent = os.getenv(f'{name.upper()}_DMIT_USER_AGENT', '')
        if not name:
            raise DmitError('DMIT 环境变量必须包含服务器名称前缀。')
        servers[name] = DmitServer(service_id, cookie, user_agent)
    return servers


def parse_auth_cookies(service_id: str, cookie: str, user_agent: str) -> SimpleCookie:
    """验证环境配置并解析 Cookie；仅接受含记住我凭据的长效认证配置。"""
    if not service_id.isascii() or not service_id.isdecimal() or int(service_id) <= 0:
        raise DmitError('DMIT 服务记录编号必须为正整数。')
    if any(not isinstance(value, str) or not value.strip() or '\r' in value or '\n' in value
           for value in (cookie, user_agent)):
        raise DmitError('DMIT_COOKIE 和 DMIT_USER_AGENT 必须为非空单行字符串。')
    cookies = SimpleCookie()
    try:
        cookies.load(cookie)
    except CookieError as error:
        raise DmitError('DMIT_COOKIE 格式无效。') from error
    if 'WHMCSUser' not in cookies or not cookies['WHMCSUser'].value.strip():
        raise DmitError(f'DMIT_COOKIE 缺少长效认证 WHMCSUser。{RENEW_AUTH_MESSAGE}')
    return cookies


def main() -> int:
    """所有参数从环境变量或 .env 读取，不加载机器人或发送 Telegram 消息。"""
    load_dotenv()
    logger.remove()
    logger.add(sys.stderr, level='INFO', backtrace=False, diagnose=False)
    try:
        servers = load_servers()
        if not servers:
            raise DmitError('未找到 DMIT 环境变量配置。')
        usages = {name: server.get_usage() for name, server in servers.items()}
    except DmitError as error:
        logger.error('DMIT 独立查询失败：{}', error)
        return 1
    print(json.dumps(usages, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
