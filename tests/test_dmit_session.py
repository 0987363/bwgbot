import json
from email.message import Message
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import requests
import dmit


DETAIL = {
    'serviceid': 123, 'bwusage': 1024, 'bwlimit': 4096,
    'nextduedate': '2026-12-25', 'hostname': 'test-host',
    'dedicatedip': '203.0.113.1', 'assignedips': '',
}


class DmitSessionTests(unittest.TestCase):
    def test_response_cookies_replace_initial_values_on_subsequent_queries(self):
        server = dmit.DmitServer('123', 'WHMCSUser=remember; WHMCStest=old; cf_clearance=cf-old', 'test-agent')
        sent = []

        def respond(request, **kwargs):
            sent.append(request.headers.get('Cookie', ''))
            response = requests.Response()
            response.status_code = 200
            response.url = request.url
            response.request = request
            response._content = json.dumps({'result': 'success', 'success': DETAIL}).encode()
            message = Message()
            message.add_header('Set-Cookie', f'WHMCStest=new-{len(sent)}; Path=/; Secure; HttpOnly')
            message.add_header('Set-Cookie', 'cf_clearance=cf-new; Domain=.dmit.io; Path=/; Secure')
            response.raw = SimpleNamespace(_original_response=SimpleNamespace(msg=message))
            return response

        # 保留真实 Session、请求准备和 Cookie 提取，只替换网络适配器边界。
        with patch.object(requests.adapters.HTTPAdapter, 'send', side_effect=respond):
            for _ in range(3):
                self.assertEqual(server.get_usage()['used_bytes'], 1024**3)
        self.assertIn('WHMCStest=old', sent[0])
        self.assertIn('WHMCStest=new-1', sent[1])
        self.assertNotIn('WHMCStest=old', sent[1])
        self.assertIn('WHMCStest=new-2', sent[2])
        self.assertEqual(sent[1].count('cf_clearance='), 1)
        self.assertIn('cf_clearance=cf-new', sent[1])
        self.assertIn('WHMCSUser=remember', sent[2])

    def test_short_session_cookie_alone_is_rejected(self):
        with patch.object(requests.sessions.Session, 'request') as request:
            with self.assertRaisesRegex(dmit.DmitError, 'WHMCSUser|记住我'):
                dmit.DmitServer('123', 'WHMCStest=short-only', 'test-agent')
            request.assert_not_called()

    def test_servers_do_not_share_authentication_state(self):
        first = dmit.DmitServer('123', 'WHMCSUser=first-private', 'test-agent')
        second = dmit.DmitServer('124', 'WHMCSUser=second-private', 'test-agent')
        first._session.cookies.set('WHMCStest', 'temporary', domain='www.dmit.io', path='/')
        self.assertNotIn('WHMCStest', second._session.cookies)
        self.assertNotIn('first-private', repr(first))
        self.assertNotIn('second-private', repr(second))

    def test_expired_authentication_has_actionable_safe_message(self):
        server = dmit.DmitServer('123', 'WHMCSUser=private-token', 'test-agent')
        response = requests.Response()
        response.status_code = 403
        response._content = b'private-server-body'
        with patch.object(requests.sessions.Session, 'get', return_value=response):
            with self.assertRaises(dmit.DmitAuthError) as error:
                server.get_usage()
        self.assertIn('记住我', str(error.exception))
        self.assertIn('DMIT_COOKIE', str(error.exception))
        self.assertIn('重启', str(error.exception))
        self.assertNotIn('private', str(error.exception))


if __name__ == '__main__':
    unittest.main()
