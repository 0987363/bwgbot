import asyncio
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import bwg
import dmit


class ProviderBoundaryTests(unittest.TestCase):
    def test_bwg_reads_environment_and_applies_multiplier_in_provider(self):
        with patch.dict(os.environ, {'WEST_VEID':'123', 'WEST_API_KEY':'private-key'}, clear=True):
            server = bwg.load_servers()['west']
        response = Mock(status_code=200)
        response.json.return_value = {
            'error':0, 'plan_monthly_data':1024**3, 'monthly_data_multiplier':2,
            'data_counter':1024**2, 'node_location':'US', 'hostname':'bwg',
            'plan':'test', 'ip_addresses':['203.0.113.1'], 'data_next_reset':1792886400,
        }
        with patch.object(bwg.requests, 'get', return_value=response) as get:
            usage = server.get_usage()
        self.assertEqual(usage['quota_bytes'], 2*1024**3)
        self.assertEqual(usage['used_bytes'], 1024**2)
        self.assertEqual(usage['location'], 'US')
        self.assertNotIn('monthly_data_multiplier', usage)
        self.assertNotIn('private-key', repr(server))
        self.assertEqual(get.call_args.kwargs['params']['api_key'], 'private-key')

    def test_bwg_transport_errors_do_not_expose_api_key(self):
        with patch.dict(os.environ, {'WEST_VEID':'123', 'WEST_API_KEY':'private-key'}, clear=True):
            server = bwg.load_servers()['west']
        with patch.object(bwg.requests, 'get', side_effect=bwg.requests.exceptions.RequestException('url?api_key=private-key')):
            with self.assertRaises(bwg.BwgError) as result:
                server.get_usage()
        self.assertNotIn('private-key', str(result.exception))

    def test_provider_config_rejects_missing_credentials(self):
        for module, env in [(bwg, {'WEST_VEID':'123'}),
                            (dmit, {'EAST_DMIT_SERVICE_ID':'456', 'EAST_DMIT_COOKIE':'WHMCSUser=cookie'})]:
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaises(ValueError):
                    module.load_servers()

    def test_dmit_reads_cookie_and_user_agent_directly_from_environment(self):
        with patch.dict(os.environ, {'EAST_DMIT_SERVICE_ID':'456', 'EAST_DMIT_COOKIE':'WHMCSUser=private-cookie',
                                     'EAST_DMIT_USER_AGENT':'browser'}, clear=True):
            server = dmit.load_servers()['east']
        self.assertNotIn('private-cookie', repr(server))
        self.assertEqual(server.service_id, '456')
        self.assertEqual(server.cookie, 'WHMCSUser=private-cookie')
        self.assertEqual(server.user_agent, 'browser')

    def test_bot_only_consumes_normalized_usage_for_mixed_providers(self):
        env = {'BOT_TOKEN':'123456:offline', 'WEST_VEID':'123', 'WEST_API_KEY':'key',
               'EAST_DMIT_SERVICE_ID':'456', 'EAST_DMIT_COOKIE':'WHMCSUser=cookie', 'EAST_DMIT_USER_AGENT':'browser'}
        spec = importlib.util.spec_from_file_location('bot_providers_test', Path(__file__).resolve().parents[1]/'bot.py')
        bot = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, env, clear=True), patch('dotenv.load_dotenv'):
            spec.loader.exec_module(bot)
        payload = {'hostname':'host', 'ip_addresses':['203.0.113.1'], 'location':'test', 'plan':'test',
                   'quota_bytes':10*1024**3, 'used_bytes':2*1024**3, 'reset_date':'2026-10-25'}
        with patch.object(bwg.BwgServer, 'get_usage', return_value=payload), patch.object(dmit.DmitServer, 'get_usage', return_value=payload):
            report = asyncio.run(bot.generate_servers_report(['west','east']))
        self.assertIn('WEST', report)
        self.assertIn('EAST', report)
        self.assertEqual(report.count('`2.0` / `10.0 GB`'), 2)
        self.assertNotIn('requests', bot.__dict__)


if __name__ == '__main__':
    unittest.main()
