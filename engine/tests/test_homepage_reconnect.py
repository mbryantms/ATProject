"""Homepage recovery must never replay a write or an open transaction."""

from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import OperationalError, connection, transaction
from django.test import RequestFactory, TransactionTestCase

from engine.models import SiteSettings
from engine.views import IndexView


class HomepageReconnectTests(TransactionTestCase):
    def setUp(self):
        connection.close()
        connection.ensure_connection()
        SiteSettings.load()
        self.view = IndexView()
        request = RequestFactory().get("/")
        request.user = AnonymousUser()
        self.view.setup(request)

    def break_connection(self):
        connection.ensure_connection()
        connection.connection.close()
        # Exercise the real psycopg -> Django exception path.
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

    def test_closed_connection_is_reopened_once(self):
        original = self.view._get_home_context
        calls = 0

        def interrupted(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                self.break_connection()
            return original(**kwargs)

        with patch.object(self.view, "_get_home_context", side_effect=interrupted):
            with self.assertLogs("engine.views", level="WARNING"):
                context = self.view.get_context_data()
        self.assertEqual(calls, 2)
        self.assertIn("newest_posts", context)
        self.assertTrue(connection.is_usable())

    def test_repeated_disconnect_is_not_hidden(self):
        with patch.object(
            self.view, "_get_home_context", side_effect=self.break_connection
        ) as read:
            with self.assertLogs("engine.views", level="WARNING"):
                with self.assertRaises(OperationalError):
                    self.view.get_context_data()
        self.assertEqual(read.call_count, 2)
        connection.close()

    def test_query_error_on_healthy_connection_is_not_retried(self):
        error = OperationalError("canceling statement due to statement timeout")
        with patch.object(self.view, "_get_home_context", side_effect=error) as read:
            with self.assertRaises(OperationalError):
                self.view.get_context_data()
        self.assertEqual(read.call_count, 1)
        self.assertTrue(connection.is_usable())

    def test_atomic_transaction_is_never_retried(self):
        with patch.object(
            self.view, "_get_home_context", side_effect=self.break_connection
        ) as read:
            with self.assertRaises(OperationalError):
                with transaction.atomic():
                    self.view.get_context_data()
            self.assertEqual(read.call_count, 1)
        connection.close()

    def test_manual_transaction_is_never_retried(self):
        connection.set_autocommit(False)
        try:
            with patch.object(
                self.view, "_get_home_context", side_effect=self.break_connection
            ) as read:
                with self.assertRaises(OperationalError):
                    self.view.get_context_data()
                self.assertEqual(read.call_count, 1)
        finally:
            connection.close()
            connection.ensure_connection()

    def test_connection_setup_failure_is_not_retried(self):
        connection.close()
        with patch.object(
            self.view,
            "_get_home_context",
            side_effect=OperationalError("connect failed"),
        ) as read:
            with self.assertRaises(OperationalError):
                self.view.get_context_data()
        self.assertEqual(read.call_count, 1)
