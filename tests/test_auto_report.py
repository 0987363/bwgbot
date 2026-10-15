import importlib
import os
import pathlib
import sys
import types
import unittest
from unittest.mock import Mock, patch


def load_bot_module():
    repo_root = pathlib.Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    telegram = types.ModuleType("telegram")
    telegram.Update = object

    telegram_ext = types.ModuleType("telegram.ext")
    telegram_ext.Application = object
    telegram_ext.CommandHandler = object
    telegram_ext.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda: None

    with patch.dict(
        sys.modules,
        {
            "telegram": telegram,
            "telegram.ext": telegram_ext,
            "dotenv": dotenv,
        },
    ), patch.dict(
        os.environ,
        {
            "BOT_TOKEN": "test-token",
            "TEST_VEID": "123",
            "TEST_API_KEY": "test-key",
        },
        clear=False,
    ):
        sys.modules.pop("bot", None)
        return importlib.import_module("bot")


class AutoReportSchedulingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bot = load_bot_module()

    def test_startup_flag_schedules_immediate_report_only(self):
        job_queue = Mock()
        config = types.SimpleNamespace(
            auto_report_on_start=True,
            auto_report_schedule={"type": "daily", "hour": 9, "minute": 0},
        )

        self.bot.schedule_initial_auto_report(job_queue, Mock(), config)

        job_queue.run_once.assert_called_once()
        self.assertEqual(job_queue.run_once.call_args.kwargs["when"], 0)

    def test_config_reads_non_empty_startup_flag(self):
        with patch.dict(
            os.environ,
            {
                "AUTO_REPORT_ON_START": "1",
                "BOT_TOKEN": "test-token",
                "TEST_VEID": "123",
                "TEST_API_KEY": "test-key",
            },
            clear=False,
        ):
            config = self.bot.Config()

        self.assertTrue(config.auto_report_on_start)

    def test_without_startup_flag_schedules_next_cron_time(self):
        job_queue = Mock()
        config = types.SimpleNamespace(
            auto_report_on_start=False,
            auto_report_schedule={"type": "daily", "hour": 9, "minute": 0},
            _format_schedule_display=lambda: "每天 09:00",
        )

        self.bot.schedule_initial_auto_report(job_queue, Mock(), config)

        job_queue.run_once.assert_called_once()
        self.assertGreater(job_queue.run_once.call_args.kwargs["when"], 0)


if __name__ == "__main__":
    unittest.main()
