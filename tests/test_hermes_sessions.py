from __future__ import annotations

import json
import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from _local_package import load_local_package

load_local_package()
from omh.paths import OmhPaths
from omh.surfaces.hermes_sessions import HERMES_SESSION_SCHEMA_VERSION, observe_hermes_sessions


CREATE_SESSIONS = """
create table sessions (
    source text,
    model text,
    model_config text,
    ended_at text,
    archived integer not null,
    hidden integer not null,
    started_at text,
    last_activity_at text,
    title text,
    token_count integer
)
"""


class HermesSessionObservationTests(unittest.TestCase):
    def test_observes_visible_sessions_and_latest_live_model_with_three_selects(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            paths.hermes_home.mkdir()
            db_path = paths.hermes_home / "state.db"
            connection = sqlite3.connect(db_path)
            connection.execute(CREATE_SESSIONS)
            model_config = json.dumps(
                {
                    "model": "gpt-5.6-sol",
                    "provider": "openai-codex",
                    "reasoning_config": {"enabled": True, "effort": "medium"},
                }
            )
            rows = [
                ("tui", "older-model", None, None, 0, 0, "2026-08-01", "2026-08-02", "secret", 11),
                ("api", "gpt-5.6-sol", model_config, None, 0, 0, "2026-08-03", "2026-08-04", "secret", 22),
                ("tui", "ended-model", None, "2026-08-05", 0, 0, "2026-08-01", "2026-08-05", "secret", 33),
                ("tui", "archived-model", None, None, 1, 0, "2026-08-06", "2026-08-06", "secret", 44),
                ("tui", "hidden-model", None, None, 0, 1, "2026-08-07", "2026-08-07", "secret", 55),
            ]
            connection.executemany("insert into sessions values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
            connection.commit()
            connection.close()

            statements: list[str] = []
            connect_calls: list[tuple[object, dict[str, object]]] = []
            real_connect = sqlite3.connect

            def recording_connect(database: object, **kwargs: object) -> sqlite3.Connection:
                connect_calls.append((database, kwargs))
                observed_connection = real_connect(database, **kwargs)
                observed_connection.set_trace_callback(statements.append)
                return observed_connection

            with patch("omh.surfaces.hermes_sessions.sqlite3.connect", side_effect=recording_connect):
                payload = observe_hermes_sessions(paths)

            self.assertEqual(
                connect_calls,
                [(f"file:{db_path}?mode=ro", {"uri": True, "timeout": 1.0})],
            )
            self.assertEqual(len(statements), 3)
            self.assertTrue(all(statement.lower().startswith("select ") for statement in statements))
            self.assertTrue(all("source" not in statement.lower() for statement in statements))
            self.assertTrue(all("title" not in statement.lower() for statement in statements))
            self.assertTrue(all("token" not in statement.lower() for statement in statements))
            self.assertEqual(payload["schema_version"], HERMES_SESSION_SCHEMA_VERSION)
            self.assertTrue(payload["observed"])
            self.assertEqual(payload["reason"], "")
            self.assertEqual(payload["live"], 2)
            self.assertEqual(payload["total"], 3)
            self.assertEqual(
                payload["current_model"],
                {
                    "observed": True,
                    "value": "gpt-5.6-sol",
                    "effort": "medium",
                    "provider": "openai-codex",
                    "label": "gpt-5.6-sol:medium",
                },
            )
            self.assertNotIn("by_source", payload)
            self.assertNotIn("source", payload["current_model"])
            self.assertNotIn("title", payload)
            self.assertNotIn("token_count", payload)

    def test_missing_database_degrades_without_creating_it(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            paths.hermes_home.mkdir()

            payload = observe_hermes_sessions(paths)

            self.assertFalse(payload["observed"])
            self.assertEqual(payload["reason"], "state_db_missing")
            self.assertEqual(payload["live"], 0)
            self.assertEqual(payload["total"], 0)
            self.assertFalse(payload["current_model"]["observed"])
            self.assertFalse((paths.hermes_home / "state.db").exists())

    def test_non_sqlite_database_degrades_as_unreadable(self) -> None:
        with TemporaryDirectory() as tmp:
            paths = self._paths(Path(tmp))
            paths.hermes_home.mkdir()
            (paths.hermes_home / "state.db").write_bytes(b"not a sqlite database")

            payload = observe_hermes_sessions(paths)

            self.assertFalse(payload["observed"])
            self.assertEqual(payload["reason"], "state_db_unreadable")
            self.assertFalse(payload["current_model"]["observed"])

    def test_missing_or_malformed_model_config_preserves_the_observed_model(self) -> None:
        for model_config in (None, "not-json", "[]", '{"reasoning_config": []}'):
            with self.subTest(model_config=model_config), TemporaryDirectory() as tmp:
                paths = self._paths(Path(tmp))
                paths.hermes_home.mkdir()
                connection = sqlite3.connect(paths.hermes_home / "state.db")
                connection.execute(CREATE_SESSIONS)
                connection.execute(
                    "insert into sessions values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    ("tui", "model-only", model_config, None, 0, 0, "2026-08-01", None, "secret", 99),
                )
                connection.commit()
                connection.close()

                payload = observe_hermes_sessions(paths)

                self.assertTrue(payload["observed"])
                self.assertEqual(
                    payload["current_model"],
                    {
                        "observed": True,
                        "value": "model-only",
                        "effort": "",
                        "provider": "",
                        "label": "model-only",
                    },
                )

    @staticmethod
    def _paths(root: Path) -> OmhPaths:
        return OmhPaths(omh_home=root / ".omh", hermes_home=root / ".hermes")


if __name__ == "__main__":
    unittest.main()
