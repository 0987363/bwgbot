import datetime
import importlib.util
import json
import os
from pathlib import Path
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import dmit


DETAIL = {
    'serviceid': 116313, 'bwusage': 622926, 'bwlimit': 4096000,
    'bwusage_in': 324893, 'bwusage_out': 298033, 'bw_method': 'both',
    'nextduedate': '2026-12-25', 'hostname': 'test-dmit',
    'dedicatedip': '203.0.113.10', 'assignedips': '2001:db8::/64',
    'password': 'must-not-escape',
}


class DmitUsageTests(unittest.TestCase):
    def setUp(self):
        self.cookie = 'WHMCSUser=test-secret'
        self.user_agent = 'test-agent'
        self.response = Mock(status_code=200)
        self.response.json.return_value = {'result': 'success', 'success': DETAIL.copy()}

    def test_query_uses_observed_read_only_endpoint_and_whitelist(self):
        with patch.object(dmit.requests.sessions.Session, 'get', return_value=self.response) as get:
            result = dmit.DmitServer('116313', self.cookie, self.user_agent).get_usage()
        self.assertEqual(result['used_bytes'], 622926 * 1024**2)
        self.assertEqual(result['quota_bytes'], 4096000 * 1024**2)
        self.assertEqual(result['ip_addresses'], ['203.0.113.10', '2001:db8::/64'])
        self.assertNotIn('password', result)
        self.assertNotIn('must-not-escape', json.dumps(result))
        self.assertEqual(get.call_args.args[0], 'https://www.dmit.io/clientarea.php')
        self.assertEqual(get.call_args.kwargs['params']['subaction'], 'whmcsdetail')
        self.assertEqual(get.call_args.kwargs['params']['id'], '116313')
        self.assertFalse(get.call_args.kwargs['allow_redirects'])

    def test_max_billing_uses_provider_usage_without_adding_directions(self):
        self.response.json.return_value['success'].update(bw_method='max', bwusage=324893)
        with patch.object(dmit.requests.sessions.Session, 'get', return_value=self.response):
            result = dmit.DmitServer('116313', self.cookie, self.user_agent).get_usage()
        self.assertEqual(result['used_bytes'], 324893 * 1024**2)

    def test_invalid_responses_never_become_zero_usage_or_leak_response(self):
        cases = [
            (302, None), (403, None),
            (200, {'result': 'error', 'message': 'secret-server-response'}),
            (200, {'result': 'success', 'success': {}}),
            (200, {'result': 'success', 'success': dict(DETAIL, serviceid=1)}),
            (200, {'result': 'success', 'success': dict(DETAIL, bwusage=-1)}),
            (200, {'result': 'success', 'success': dict(DETAIL, bwusage='NaN')}),
        ]
        for status, body in cases:
            with self.subTest(status=status, body=body):
                self.response.status_code = status
                self.response.json.return_value = body
                with patch.object(dmit.requests.sessions.Session, 'get', return_value=self.response):
                    with self.assertRaises(dmit.DmitError) as error:
                        dmit.DmitServer('116313', self.cookie, self.user_agent).get_usage()
                self.assertNotIn('secret-server-response', str(error.exception))

    def test_login_html_is_reported_as_expired_session(self):
        self.response.json.side_effect = ValueError('html login')
        with patch.object(dmit.requests.sessions.Session, 'get', return_value=self.response):
            with self.assertRaisesRegex(dmit.DmitError, '登录|凭据'):
                dmit.DmitServer('116313', self.cookie, self.user_agent).get_usage()

    def test_monthly_reset_uses_utc_and_clamps_short_month(self):
        utc = datetime.timezone.utc
        cases = [
            ('2026-12-25', datetime.datetime(2026, 10, 15, tzinfo=utc), '2026-10-25'),
            ('2026-12-25', datetime.datetime(2026, 10, 25, 1, tzinfo=utc), '2026-11-25'),
            ('2026-12-31', datetime.datetime(2026, 2, 1, tzinfo=utc), '2026-02-28'),
            ('2026-12-25', datetime.datetime(2026, 12, 26, tzinfo=utc), '2027-01-25'),
        ]
        for due, now, expected in cases:
            self.assertEqual(dmit.next_reset_date(due, now), expected)

    def test_missing_credentials_fail_before_network(self):
        self.cookie = ''
        with patch.object(dmit.requests.sessions.Session, 'get') as get:
            with self.assertRaises(dmit.DmitError):
                dmit.DmitServer('116313', self.cookie, self.user_agent).get_usage()
            get.assert_not_called()


class DmitBotIntegrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[1] / 'bot.py'
        spec = importlib.util.spec_from_file_location('bot_dmit_test', source)
        self.bot = importlib.util.module_from_spec(spec)
        self.environment = {
            'BOT_TOKEN': '123456:offline-test',
            'FONTANA_DMIT_SERVICE_ID': '116313',
            'FONTANA_DMIT_COOKIE': 'WHMCSUser=cookie',
            'FONTANA_DMIT_USER_AGENT': 'browser',
            'GROUP_CONFIG_1': '123456:fontana',
        }
        with patch.dict(os.environ, self.environment, clear=True), patch('dotenv.load_dotenv'):
            spec.loader.exec_module(self.bot)

    async def test_dmit_only_config_flows_through_existing_report(self):
        payload = {'used_bytes': 622926*1024**2, 'quota_bytes': 4096000*1024**2,
                   'hostname': 'test-dmit', 'ip_addresses': ['203.0.113.10'], 'location':'N/A',
                   'reset_date': '2026-10-25'}
        with patch.object(dmit.DmitServer, 'get_usage', return_value=payload) as query:
            report = await self.bot.generate_servers_report(['fontana'])
        query.assert_called_once_with()
        self.assertIn('608.33', report)
        self.assertIn('4000.0', report)
        self.assertIn('2026-10-25', report)
        self.assertIn('203.0.113.10', report)
        self.assertEqual(self.bot.config.group_configs, {123456: ['fontana']})

    def test_session_failure_returns_query_error(self):
        with patch.object(dmit.DmitServer, 'get_usage', side_effect=dmit.DmitError('登录态已失效')):
            data, error = self.bot.get_server_usage('fontana')
        self.assertIsNone(data)
        self.assertIn('登录态已失效', error)

    async def test_authentication_failure_appears_in_scheduled_report(self):
        context = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()), job_queue=Mock())
        error = dmit.DmitAuthError('DMIT 认证失效。' + dmit.RENEW_AUTH_MESSAGE)
        with patch.object(dmit.DmitServer, 'get_usage', side_effect=error), patch.object(self.bot.asyncio, 'sleep', new=AsyncMock()):
            await self.bot.auto_report_job(context)
        message = context.bot.send_message.call_args.kwargs['text']
        self.assertIn('查询失败', message)
        self.assertIn('记住我', message)
        self.assertIn('`DMIT_COOKIE`', message)
        self.assertIn('重启', message)
        self.assertNotIn('WHMCSUser=cookie', message)
        self.assertEqual(context.bot.send_message.call_args.kwargs['chat_id'], 123456)
        context.job_queue.run_once.assert_called_once()

    def test_conflicting_provider_config_is_rejected(self):
        with patch.dict(os.environ, dict(self.environment, FONTANA_VEID='1', FONTANA_API_KEY='key'), clear=True):
            with self.assertRaisesRegex(ValueError, '同时'):
                self.bot.Config()


if __name__ == '__main__':
    unittest.main()
