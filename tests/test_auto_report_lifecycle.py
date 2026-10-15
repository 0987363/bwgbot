import asyncio
import datetime
import importlib.util
import json
import os
import pathlib
import unittest
from unittest.mock import patch

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from telegram.ext import Application
from telegram.request import BaseRequest


class OfflineTelegramRequest(BaseRequest):
    """保留真实机器人生命周期，只替换 Telegram 网络边界。"""

    def __init__(self, startup_delay: float = 0) -> None:
        self.startup_delay = startup_delay
        self.messages = []

    @property
    def read_timeout(self) -> float:
        return 5

    async def initialize(self) -> None:
        await asyncio.sleep(self.startup_delay)

    async def shutdown(self) -> None:
        pass

    async def do_request(self, url, method, request_data=None, **kwargs):
        endpoint = url.rsplit('/', 1)[-1]
        if endpoint == 'getMe':
            result = {'id': 123456, 'is_bot': True, 'first_name': 'Test', 'username': 'test_bot'}
        elif endpoint == 'sendMessage':
            parameters = request_data.parameters
            self.messages.append(parameters)
            result = {
                'message_id': len(self.messages),
                'date': 0,
                'chat': {'id': parameters['chat_id'], 'type': 'private'},
                'text': parameters['text'],
            }
        else:
            raise AssertionError(f'出现未预期的 Telegram 请求: {endpoint}')
        return 200, json.dumps({'ok': True, 'result': result}).encode()


class AutoReportLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        source = pathlib.Path(__file__).resolve().parents[1] / 'bot.py'
        spec = importlib.util.spec_from_file_location('bot_lifecycle_test', source)
        self.bot = importlib.util.module_from_spec(spec)
        with patch.dict(os.environ, {
            'BOT_TOKEN': '123456:offline-test',
            'TEST_VEID': '123',
            'TEST_API_KEY': 'offline-test',
            'GROUP_CONFIG_1': '123456:test',
            'AUTO_REPORT_ON_START': '1',
        }, clear=True), patch('dotenv.load_dotenv'):
            spec.loader.exec_module(self.bot)

    async def test_slow_start_sends_once_and_keeps_next_report(self):
        request = OfflineTelegramRequest(startup_delay=1.2)
        application = Application.builder().token(self.bot.config.bot_token).updater(None).request(request).build()
        queue = application.job_queue
        finished = asyncio.Event()
        queue.scheduler.add_listener(
            lambda event: finished.set(),
            EVENT_JOB_EXECUTED | EVENT_JOB_MISSED | EVENT_JOB_ERROR,
        )
        # 和 main 一样，在联网初始化之前注册首次任务。
        self.bot.schedule_initial_auto_report(queue, self.bot.auto_report_job, self.bot.config)
        response = {
            'error': 0,
            'hostname': 'test-server',
            'ip_addresses': ['203.0.113.10', '2001:db8::10'],
            'node_location': 'test-location',
            'plan': 'test-plan',
            'plan_monthly_data': 1024 ** 3,
            'data_counter': 0,
            'data_next_reset': 1800000000,
        }
        with patch.object(self.bot.requests, 'get') as get_usage:
            get_usage.return_value.json.return_value = response
            async with application:
                await application.start()
                try:
                    await asyncio.wait_for(finished.wait(), timeout=5)
                    self.assertEqual(len(request.messages), 1)
                    self.assertEqual(request.messages[0]['chat_id'], 123456)
                    self.assertIn('TEST', request.messages[0]['text'])
                    self.assertIn('`203.0.113.10`', request.messages[0]['text'])
                    self.assertIn('`2001:db8::10`', request.messages[0]['text'])
                    self.assertIn('test-location', request.messages[0]['text'])
                    self.assertEqual(len(queue.jobs()), 1)
                    self.assertIs(queue.jobs()[0].callback, self.bot.auto_report_job)
                    self.assertGreater(
                        queue.jobs()[0].next_t, datetime.datetime.now(datetime.timezone.utc)
                    )
                finally:
                    await application.stop()

    async def test_disabled_startup_flag_waits_for_scheduled_time(self):
        self.bot.config.auto_report_on_start = False
        request = OfflineTelegramRequest()
        application = Application.builder().token(self.bot.config.bot_token).updater(None).request(request).build()
        queue = application.job_queue
        next_run = datetime.datetime.now() + datetime.timedelta(hours=1)
        with patch.object(self.bot, 'calculate_next_run_time', return_value=next_run):
            self.bot.schedule_initial_auto_report(queue, self.bot.auto_report_job, self.bot.config)
        async with application:
            await application.start()
            try:
                self.assertEqual(request.messages, [])
                self.assertEqual(len(queue.jobs()), 1)
                self.assertGreater(
                    queue.jobs()[0].next_t, datetime.datetime.now(datetime.timezone.utc)
                )
            finally:
                await application.stop()
