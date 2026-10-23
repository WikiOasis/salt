from __future__ import annotations

import importlib.util
import io
import json
import sys
import threading
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

FILES = Path(__file__).resolve().parent.parent / "files"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, FILES / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


S = load("sal_server", "sal_server.py")
C = load("sal_client", "sal_client.py")


def entry(**overrides):
    base = {
        "id": 1,
        "created_at": datetime(2026, 10, 16, 14, 2),
        "updated_at": None,
        "user": "thomas",
        "host": "mw-us-east-021",
        "minion": "mw-us-east-021.ovvin.wonet",
        "message": "restarted php-fpm",
        "is_command": 0,
        "exit_code": None,
        "deleted": 0,
        "wiki_state": "pending",
        "wiki_op": "insert",
        "wiki_line": None,
        "wiki_revid": None,
        "wiki_attempts": 0,
        "wiki_error": None,
        "phorge_state": "pending",
        "phorge_refs": None,
        "phorge_attempts": 0,
        "phorge_error": None,
    }
    base.update(overrides)
    return base


PAGE = """Intro text.

== 2026-10-16 ==
* 13:00 unai@db-c1-us-east-021: started backup

== 2026-10-14 ==
* 09:00 thomas@proxy-us-east-021: depooled mw1
"""


class WikiTextTest(unittest.TestCase):
    def test_new_day_goes_above_older_days(self):
        out = S.insert_line(PAGE, "2026-10-17", "08:00", "* 08:00 a@b: x")
        self.assertTrue(out.startswith("Intro text.\n\n== 2026-10-17 ==\n* 08:00 a@b: x\n\n== 2026-10-16 =="))

    def test_same_day_newest_first(self):
        out = S.insert_line(PAGE, "2026-10-16", "14:02", "* 14:02 a@b: x")
        self.assertIn("== 2026-10-16 ==\n* 14:02 a@b: x\n* 13:00 unai", out)

    def test_backlog_entry_sorted_inside_day(self):
        out = S.insert_line(PAGE, "2026-10-16", "12:00", "* 12:00 a@b: x")
        self.assertIn("* 13:00 unai@db-c1-us-east-021: started backup\n* 12:00 a@b: x\n\n== 2026-10-14", out)

    def test_missing_middle_day_inserted_in_order(self):
        out = S.insert_line(PAGE, "2026-10-15", "10:00", "* 10:00 a@b: x")
        self.assertIn("started backup\n\n== 2026-10-15 ==\n* 10:00 a@b: x\n\n== 2026-10-14 ==", out)

    def test_oldest_day_appended(self):
        out = S.insert_line(PAGE, "2026-10-01", "10:00", "* 10:00 a@b: x")
        self.assertTrue(out.endswith("depooled mw1\n\n== 2026-10-01 ==\n* 10:00 a@b: x\n"))

    def test_empty_page(self):
        self.assertEqual(S.insert_line("", "2026-10-16", "10:00", "* l"), "== 2026-10-16 ==\n* l\n")

    def test_remove_last_line_drops_heading(self):
        out = S.remove_line(PAGE, "* 09:00 thomas@proxy-us-east-021: depooled mw1")
        self.assertNotIn("2026-10-14", out)
        self.assertIn("started backup", out)

    def test_remove_keeps_heading_with_entries(self):
        page = S.insert_line(PAGE, "2026-10-16", "14:02", "* 14:02 a@b: x")
        out = S.remove_line(page, "* 14:02 a@b: x")
        self.assertEqual(out, PAGE)

    def test_replace(self):
        out = S.replace_line(PAGE, "* 13:00 unai@db-c1-us-east-021: started backup", "* 13:00 new")
        self.assertIn("== 2026-10-16 ==\n* 13:00 new\n", out)
        self.assertIsNone(S.replace_line(PAGE, "* nope", "x"))


class RenderTest(unittest.TestCase):
    def test_markup_is_neutralised_and_refs_linked(self):
        line = S.render_line(entry(message="fixed [[x]] <b> ~~~~ for T12 and D3"), "https://phorge.wikioasis.org")
        self.assertEqual(
            line,
            "* 14:02 thomas@mw-us-east-021: <nowiki>fixed [[x]] &lt;b&gt; ~~~~ for </nowiki>"
            "[https://phorge.wikioasis.org/T12 T12]<nowiki> and </nowiki>[https://phorge.wikioasis.org/D3 D3]",
        )

    def test_command_rendering(self):
        line = S.render_line(entry(message="systemctl restart nginx", is_command=1, exit_code=3), "p")
        self.assertEqual(
            line, "* 14:02 thomas@mw-us-east-021: <code><nowiki>systemctl restart nginx</nowiki></code> (exit 3)"
        )

    def test_ref_extraction(self):
        self.assertEqual(S.extract_refs("T1 T1, see D22/rMWabcdef1 T0 xT5 url/T9 P3."), ["T1", "D22", "P3"])
        self.assertEqual(S.extract_refs("commit rMW1a2b3c4d"), ["rMW1a2b3c4d"])

    def test_apply_insert_is_idempotent(self):
        row = entry()
        text, line = S.apply_wiki_op(PAGE, row, "p")
        again, line2 = S.apply_wiki_op(text, row, "p")
        self.assertEqual(text, again)
        self.assertEqual(line, line2)

    def test_apply_update_and_delete(self):
        row = entry()
        text, line = S.apply_wiki_op(PAGE, row, "p")
        edited, new_line = S.apply_wiki_op(
            text, entry(message="restarted nginx", wiki_op="update", wiki_line=line), "p"
        )
        self.assertNotIn(line, edited)
        self.assertIn(new_line, edited)
        removed, gone = S.apply_wiki_op(edited, entry(wiki_op="delete", deleted=1, wiki_line=new_line), "p")
        self.assertEqual(removed, PAGE)
        self.assertIsNone(gone)


class PhorgePayloadTest(unittest.TestCase):
    def test_payload_shape(self):
        cfg = S.Config({})
        payload = S.phorge_payload(cfg, entry(message="restarted php-fpm on mw1 for T1"))
        self.assertEqual(
            payload,
            {"message": "restarted php-fpm on mw1 for T1", "user": "thomas", "channel": "mw-us-east-021"},
        )
        self.assertEqual(cfg.phorge_hook, "https://phorge.wikioasis.org/sal/hook")

    def test_command_payload(self):
        payload = S.phorge_payload(S.Config({}), entry(message="apt upgrade", is_command=1, exit_code=1))
        self.assertEqual(payload["message"], "`apt upgrade` (exit 1)")
        self.assertEqual((payload["user"], payload["channel"]), ("thomas", "mw-us-east-021"))


class AuthAndInputTest(unittest.TestCase):
    def test_token_matches_salt_sha256_of_secret_and_id(self):
        import hashlib

        token = hashlib.sha256(b"s3cret:mw-us-east-021.ovvin.wonet").hexdigest()
        self.assertTrue(S.verify_host("s3cret", "mw-us-east-021.ovvin.wonet", token))
        self.assertFalse(S.verify_host("s3cret", "db-c1-us-east-021.ovvin.wonet", token))
        self.assertFalse(S.verify_host("", "x", token))

    def test_message_cleaning(self):
        self.assertEqual(S.clean_message("  a\n\tb  ", 10), "a b")
        with self.assertRaises(ValueError):
            S.clean_message("   ", 10)
        with self.assertRaises(ValueError):
            S.clean_message("x" * 11, 10)

    def test_parse_when(self):
        now = datetime(2026, 10, 16, 12, 0)
        self.assertEqual(S.parse_when("2h", now), datetime(2026, 10, 16, 10, 0))
        self.assertEqual(S.parse_when("2026-10-15T08:00:00Z"), datetime(2026, 10, 15, 8, 0))
        self.assertEqual(S.parse_when("2026-10-15"), datetime(2026, 10, 15))


class FakeWiki:
    def __init__(self, text=""):
        self.text = text
        self.saves = []
        self.fail = None

    def fetch(self):
        return {"text": self.text, "basetimestamp": None, "starttimestamp": None, "token": "t", "missing": False}

    def save(self, page, text, summary):
        if self.fail:
            error, self.fail = self.fail, None
            raise error
        self.text = text
        self.saves.append(summary)
        return len(self.saves)


class FakeDb:
    def __init__(self):
        self.calls = []

    def run(self, sql, args=None, fetch=None):
        self.calls.append((sql, args))


class WorkerTest(unittest.TestCase):
    def make(self, text=""):
        worker = S.Worker(S.Config({}), FakeDb(), threading.Event(), threading.Event())
        worker.wiki = FakeWiki(text)
        return worker

    def test_batch_is_one_edit(self):
        worker = self.make(PAGE)
        worker.wiki_batch([entry(id=1), entry(id=2, message="second", created_at=datetime(2026, 10, 16, 14, 5))])
        self.assertEqual(len(worker.wiki.saves), 1)
        self.assertIn("(+1 more)", worker.wiki.saves[0])
        self.assertIn("* 14:05 thomas@mw-us-east-021: <nowiki>second</nowiki>\n* 14:02", worker.wiki.text)
        done = [c for c in worker.db.calls if "wiki_state = 'done'" in c[0]]
        self.assertEqual(len(done), 2)

    def test_rejected_batch_is_split_and_bad_entry_failed(self):
        worker = self.make(PAGE)
        worker.wiki.fail = S.WikiError("abusefilter-disallowed")
        worker.wiki_batch([entry(id=1), entry(id=2, message="second")])
        self.assertEqual(len(worker.wiki.saves), 2)

    def test_transient_error_defers(self):
        worker = self.make(PAGE)
        worker.wiki.fail = S.WikiError("ratelimited")
        worker.wiki_batch([entry(id=7)])
        deferred = [c for c in worker.db.calls if "wiki_attempts" in c[0]]
        self.assertEqual(deferred[0][1][0], "pending")


class ClientTest(unittest.TestCase):
    def test_log_takes_everything_verbatim(self):
        with (
            mock.patch.object(C, "load_config", return_value={}),
            mock.patch.object(C, "post", return_value={"id": 5, "user": "u", "host": "h", "message": "m"}) as post,
            mock.patch("sys.stdout", new=io.StringIO()),
        ):
            self.assertEqual(C.main_log(["restarted", "nginx", "-f", "--search", "x"]), 0)
        self.assertEqual(post.call_args[0][1], "restarted nginx -f --search x")

    def test_log_without_message_is_usage_error(self):
        with mock.patch("sys.stdin", new=mock.Mock(isatty=lambda: True)), mock.patch("sys.stderr", new=io.StringIO()):
            self.assertEqual(C.main_log([]), 2)

    def test_log_reports_unlogged_message_on_failure(self):
        err = io.StringIO()
        with mock.patch.object(C, "load_config", side_effect=C.ClientError("nope")), mock.patch("sys.stderr", new=err):
            self.assertEqual(C.main_log(["hi", "there"]), 1)
        self.assertIn("not logged: hi there", err.getvalue())

    def test_cli_subcommands_parse(self):
        parser = C.build_cli()
        args = parser.parse_args(["search", "php-fpm", "-H", "mw*", "--since", "2d"])
        self.assertEqual((args.text, args.host, args.since), (["php-fpm"], "mw*", "2d"))
        args = parser.parse_args(["run", "--", "systemctl", "restart", "nginx", "-q"])
        self.assertEqual(args.command[-3:], ["restart", "nginx", "-q"])

    def test_user_detection_prefers_sudo_user(self):
        with mock.patch.dict("os.environ", {"SUDO_USER": "unai"}, clear=False):
            self.assertEqual(C.login_user(), "unai")

    def test_format_entry(self):
        data = S.serialize(entry(id=42, phorge_refs="T1"))
        line = C.format_entry(json.loads(json.dumps(data)), verbose=True)
        self.assertEqual(
            line, "2026-10-16 14:02  #42     thomas@mw-us-east-021: restarted php-fpm  [wiki:pending phorge:pending T1]"
        )


if __name__ == "__main__":
    unittest.main()
