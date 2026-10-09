"""Unit tests for fandom_import_worker.py (stdlib unittest; not deployed by Salt).

Run from the repository root:

    python3 -m unittest discover -s salt/fandom_import/tests -v

MediaWiki is replaced by a tiny fake mwscript (run with this interpreter) that
records every maintenance-script call, so the claim, discard, callback and
stage-retry paths run for real against a temporary spool.
"""

from __future__ import annotations

import gzip
import importlib.util
import io
import json
import os
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

WORKER_PATH = Path(__file__).resolve().parent.parent / "files" / "fandom_import_worker.py"


def load_worker():
    """Import the worker from its file; it is not on sys.path."""
    spec = importlib.util.spec_from_file_location("fandom_import_worker", WORKER_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


W = load_worker()

NOW = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)


def good_manifest(**overrides):
    data = {
        "version": 1,
        "id": 42,
        "central_wiki": "metawiki",
        "target_wiki": "muppetwiki",
        "source": {"key": "muppet", "subdomain": "muppet", "lang": None,
                   "base_url": "https://muppet.fandom.com", "api_url": "https://muppet.fandom.com/api.php"},
        "username_prefix": "wikia",
        "upload_user": "Fandom import",
        "summary": "Imported from https://muppet.fandom.com",
        "prefer_full_history": True,
        "queued_at": "2026-10-09T12:00:00Z",
        "attempt": 1,
    }
    data.update(overrides)
    return data


def lang_source(**overrides):
    source = {"key": "harrypotter/de", "subdomain": "harrypotter", "lang": "de",
              "base_url": "https://harrypotter.fandom.com/de",
              "api_url": "https://harrypotter.fandom.com/de/api.php"}
    source.update(overrides)
    return source


class ManifestValidationTest(unittest.TestCase):
    def validate(self, data, **kwargs):
        kwargs.setdefault("expected_id", 42)
        kwargs.setdefault("central_wiki", "metawiki")
        return W.validate_manifest(data, **kwargs)

    def test_good_manifest(self):
        m = self.validate(good_manifest())
        self.assertEqual(m.id, 42)
        self.assertEqual(m.target_wiki, "muppetwiki")
        self.assertEqual(m.source.api_url, "https://muppet.fandom.com/api.php")
        self.assertEqual(m.source.index_url, "https://muppet.fandom.com/index.php")
        self.assertTrue(m.prefer_full_history)

    def test_good_language_manifest(self):
        m = self.validate(good_manifest(source=lang_source()))
        self.assertEqual(m.source.key, "harrypotter/de")
        self.assertEqual(m.source.index_url, "https://harrypotter.fandom.com/de/index.php")

    def test_bad_subdomain(self):
        for subdomain in ("muppet.evil.com", "-muppet", "Muppet", "", "a" * 64, "muppet/x"):
            source = {"key": subdomain, "subdomain": subdomain, "lang": None,
                      "base_url": f"https://{subdomain}.fandom.com",
                      "api_url": f"https://{subdomain}.fandom.com/api.php"}
            with self.subTest(subdomain=subdomain):
                with self.assertRaises(W.ManifestError) as ctx:
                    self.validate(good_manifest(source=source))
                self.assertEqual(ctx.exception.import_id, 42)
                self.assertEqual(ctx.exception.central_wiki, "metawiki")

    def test_mismatched_api_url(self):
        source = dict(good_manifest()["source"], api_url="https://evil.example/api.php")
        with self.assertRaises(W.ManifestError):
            self.validate(good_manifest(source=source))

    def test_mismatched_base_url_for_language(self):
        with self.assertRaises(W.ManifestError):
            self.validate(good_manifest(source=lang_source(base_url="https://harrypotter.fandom.com")))

    def test_bad_lang(self):
        for lang in ("DE", "d", "deutsch", "de/../x", "de-", "de_at", "de\n"):
            source = lang_source(lang=lang, key=f"harrypotter/{lang}",
                                 base_url=f"https://harrypotter.fandom.com/{lang}",
                                 api_url=f"https://harrypotter.fandom.com/{lang}/api.php")
            with self.subTest(lang=lang):
                with self.assertRaises(W.ManifestError):
                    self.validate(good_manifest(source=source))

    def test_lang_with_region_is_fine(self):
        source = lang_source(lang="pt-br", key="harrypotter/pt-br",
                             base_url="https://harrypotter.fandom.com/pt-br",
                             api_url="https://harrypotter.fandom.com/pt-br/api.php")
        self.assertEqual(self.validate(good_manifest(source=source)).source.lang, "pt-br")

    def test_key_must_match(self):
        with self.assertRaises(W.ManifestError):
            self.validate(good_manifest(source=lang_source(key="harrypotter")))

    def test_trailing_newline_is_not_a_valid_dbname(self):
        with self.assertRaises(W.ManifestError):
            self.validate(good_manifest(target_wiki="muppetwiki\n"))

    def test_target_must_not_be_central(self):
        with self.assertRaises(W.ManifestError):
            self.validate(good_manifest(target_wiki="metawiki"))

    def test_types_are_strict(self):
        for overrides in ({"version": "1"}, {"version": True}, {"id": True}, {"id": "42"},
                          {"prefer_full_history": "yes"}, {"attempt": 0}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(W.ManifestError):
                    self.validate(good_manifest(**overrides), expected_id=None)

    def test_upload_user_and_summary(self):
        for overrides in ({"upload_user": "Fandom/import"}, {"upload_user": "a" * 86},
                          {"upload_user": ""}, {"upload_user": "x\ty"},
                          {"summary": "line\nbreak"}, {"summary": "x" * 501},
                          {"username_prefix": "Wikia"}, {"username_prefix": "a" * 17}):
            with self.subTest(overrides=overrides):
                with self.assertRaises(W.ManifestError):
                    self.validate(good_manifest(**overrides))

    def test_id_mismatch_is_not_reportable(self):
        with self.assertRaises(W.ManifestError) as ctx:
            self.validate(good_manifest(), expected_id=43)
        self.assertIsNone(ctx.exception.import_id)

    def test_foreign_central_wiki_is_not_reportable(self):
        with self.assertRaises(W.ManifestError) as ctx:
            self.validate(good_manifest(central_wiki="otherwiki"))
        self.assertIsNone(ctx.exception.central_wiki)


SAMPLE_DUMP = textwrap.dedent("""\
    <mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/" version="0.11" xml:lang="en">
      <siteinfo>
        <sitename>Muppet Wiki</sitename>
        <namespaces>
          <namespace key="0" case="first-letter" />
        </namespaces>
      </siteinfo>
      <page>
        <title>Kermit</title>
        <ns>0</ns>
        <id>1</id>
        <revision>
          <id>10</id>
          <text bytes="40" xml:space="preserve">Frog. Literal &lt;page&gt; and
    &lt;/page&gt;
    &lt;ns&gt;1200&lt;/ns&gt; stay text.</text>
        </revision>
      </page>
      <page>
        <title>Message Wall:Kermit</title>
        <ns>1200</ns>
        <id>2</id>
        <revision>
          <id>20</id>
          <text bytes="5" xml:space="preserve">Hello</text>
        </revision>
      </page>
      <page>
        <title>User:Piggy</title>
        <ns>2</ns>
        <id>3</id>
        <revision>
          <id>30</id>
          <text bytes="4" xml:space="preserve">Moi.</text>
        </revision>
      </page>
      <page>
        <title>Board Thread:Fozzie</title>
        <ns>1201</ns>
        <id>4</id>
        <revision>
          <text bytes="4" xml:space="preserve">Wocka</text>
        </revision>
      </page>
    </mediawiki>
    """)


def page_block(xml: str, title: str) -> str:
    start = xml.index(f"<title>{title}</title>")
    start = xml.rindex("  <page>", 0, start)
    end = xml.index("</page>\n", start) + len("</page>\n")
    return xml[start:end]


class FilterTest(unittest.TestCase):
    def run_filter(self, xml, keep):
        out = []
        stats = W.filter_dump_lines(io.StringIO(xml), out.append, keep)
        return "".join(out), stats

    def test_drops_unwanted_namespaces_and_keeps_the_rest(self):
        output, stats = self.run_filter(SAMPLE_DUMP, {0, 2})
        expected = (SAMPLE_DUMP.replace(page_block(SAMPLE_DUMP, "Message Wall:Kermit"), "")
                    .replace(page_block(SAMPLE_DUMP, "Board Thread:Fozzie"), ""))
        self.assertEqual(output, expected)
        self.assertEqual(stats.pages_kept, 2)
        self.assertEqual(stats.pages_skipped, 2)
        self.assertEqual(stats.skipped_namespaces, {"1200": 1, "1201": 1})
        self.assertTrue(stats.saw_footer)

    def test_header_footer_and_escaped_markup_survive(self):
        output, _ = self.run_filter(SAMPLE_DUMP, {0})
        self.assertTrue(output.startswith("<mediawiki xmlns="))
        self.assertIn("<sitename>Muppet Wiki</sitename>", output)
        self.assertTrue(output.endswith("</mediawiki>\n"))
        self.assertIn("Literal &lt;page&gt; and\n&lt;/page&gt;\n&lt;ns&gt;1200&lt;/ns&gt; stay text.", output)
        self.assertNotIn("User:Piggy", output)

    def test_keep_everything_is_identity(self):
        output, stats = self.run_filter(SAMPLE_DUMP, {0, 2, 1200, 1201})
        self.assertEqual(output, SAMPLE_DUMP)
        self.assertEqual(stats.pages_skipped, 0)

    def test_page_without_ns_is_kept(self):
        xml = "<mediawiki>\n  <page>\n    <title>Old</title>\n    <id>1</id>\n  </page>\n</mediawiki>\n"
        output, stats = self.run_filter(xml, {0})
        self.assertEqual(output, xml)
        self.assertEqual(stats.pages_kept, 1)

    def test_truncated_dump_is_an_error(self):
        truncated = SAMPLE_DUMP[:SAMPLE_DUMP.index("<id>20</id>")]
        with self.assertRaises(W.DumpFormatError):
            self.run_filter(truncated, {0})

    def test_missing_footer_is_reported(self):
        _, stats = self.run_filter(SAMPLE_DUMP.replace("</mediawiki>\n", ""), {0})
        self.assertFalse(stats.saw_footer)

    def test_check_is_called(self):
        calls = []
        W.filter_dump_lines(io.StringIO(SAMPLE_DUMP), lambda _l: None, {0},
                            check=lambda: calls.append(1), check_every=5)
        self.assertGreater(len(calls), 3)

    def test_bytes_round_trip_through_gzip(self):
        """Same text layers the worker uses: invalid UTF-8 and CR survive."""
        raw = SAMPLE_DUMP.encode("utf-8").replace(b"Frog.", b"Fr\xffog.\r")
        with tempfile.TemporaryDirectory() as tmp:
            gz = Path(tmp) / "pages.xml.gz"
            reader = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", errors="surrogateescape", newline="\n")
            with gzip.open(gz, "wt", compresslevel=6, encoding="utf-8",
                           errors="surrogateescape", newline="\n") as out:
                W.filter_dump_lines(reader, out.write, {0, 2, 1200, 1201})
            self.assertEqual(gzip.decompress(gz.read_bytes()), raw)
            W.verify_gzip_xml(gz)


class DumpUrlTest(unittest.TestCase):
    def test_full_first(self):
        self.assertEqual(W.dump_candidates("muppet", True), [
            ("full", "https://s3.amazonaws.com/wikia_xml_dumps/m/mu/muppet_pages_full.xml.7z"),
            ("current", "https://s3.amazonaws.com/wikia_xml_dumps/m/mu/muppet_pages_current.xml.7z"),
        ])

    def test_current_first(self):
        self.assertEqual([v for v, _ in W.dump_candidates("deharrypotter", False)], ["current", "full"])
        self.assertTrue(W.dump_candidates("deharrypotter", False)[0][1].startswith(
            "https://s3.amazonaws.com/wikia_xml_dumps/d/de/deharrypotter_pages_current"))

    def test_one_letter_id(self):
        self.assertEqual(W.dump_candidates("a", True)[0][1],
                         "https://s3.amazonaws.com/wikia_xml_dumps/a/a/a_pages_full.xml.7z")

    def test_invalid_id(self):
        for wikiid in ("../x", "Muppet", "", "a b"):
            with self.subTest(wikiid=wikiid):
                with self.assertRaises(ValueError):
                    W.dump_candidates(wikiid, True)

    def test_storage_classes(self):
        url = "https://s3.amazonaws.com/x"
        self.assertTrue(W.DumpCheck("full", url, 200).usable)
        self.assertTrue(W.DumpCheck("full", url, 200, storage_class="GLACIER_IR").usable)
        self.assertFalse(W.DumpCheck("full", url, 200, storage_class="DEEP_ARCHIVE").usable)
        self.assertFalse(W.DumpCheck("full", url, 200, storage_class="GLACIER").usable)
        self.assertTrue(W.DumpCheck("full", url, 200, storage_class="GLACIER", restored=True).usable)
        self.assertFalse(W.DumpCheck("full", url, 403).usable)

    def test_7z_listing(self):
        listing = textwrap.dedent("""\
            Path = dump.xml.7z
            Type = 7z
            Physical Size = 1234

            ----------
            Path = muppet_pages_full.xml
            Size = 987654321
            Packed Size = 1234
            """)
        self.assertEqual(W.parse_7z_listing_size(listing), 987654321)
        self.assertIsNone(W.parse_7z_listing_size("garbage"))


IMPORTIMAGES_OUTPUT = """\
Importing Kermit.png...done.
Importing Empty.jpg...failed. (The file you uploaded seems to be empty.)
Importing Odd...name.png...failed. (filetype-mime-mismatch)
Fozzie.gif exists, skipping
Importing Late.png...
PHP Warning:  something odd in /srv/mediawiki/x.php on line 3
failed. (backend-fail-internal)
Importing Piggy.webp...done.

Found: 6
Added: 2
Skipped: 1
Failed: 3
"""


class ImportImagesParserTest(unittest.TestCase):
    def parse(self, text):
        parser = W.ImportImagesParser()
        for line in text.splitlines():
            parser.feed(line)
        return parser

    def test_summary_and_failures(self):
        parser = self.parse(IMPORTIMAGES_OUTPUT)
        self.assertTrue(parser.has_summary)
        result = parser.result()
        self.assertEqual(result["found"], 6)
        self.assertEqual(result["added"], 2)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["failed"], 3)
        self.assertEqual(result["failed_files"], ["Empty.jpg", "Odd...name.png", "Late.png"])
        self.assertEqual(parser.done_lines, 2)

    def test_partial_failure_is_a_result(self):
        """Exit 1 with a summary: some files failed, the stage did not."""
        parser = self.parse(IMPORTIMAGES_OUTPUT)
        self.assertTrue(parser.has_summary or parser.no_files)
        self.assertGreater(parser.result()["failed"], 0)

    def test_failed_names_are_capped(self):
        text = "".join(f"Importing f{i}.png...failed. (x)\n" for i in range(150)) + "Found: 150\nFailed: 150\n"
        result = self.parse(text).result()
        self.assertEqual(result["failed"], 150)
        self.assertEqual(len(result["failed_files"]), W.FAILED_FILES_KEEP)

    def test_no_suitable_files(self):
        parser = self.parse("No suitable files could be found for import.\n")
        self.assertTrue(parser.no_files)
        self.assertFalse(parser.has_summary)

    def test_crash_without_summary(self):
        parser = self.parse("Importing A.png...done.\nPHP Fatal error: Allowed memory size exhausted\n")
        self.assertFalse(parser.has_summary)
        self.assertFalse(parser.no_files)


class PrepareOutputTest(unittest.TestCase):
    def test_valid(self):
        line = json.dumps({"namespaces": [0, 2, 1, 0], "upload_user": "Maintenance script",
                           "enabled_extensions": ["Cite"], "created_namespaces": [{"id": 112, "name": "Transcript"}],
                           "warnings": ["x"]})
        result = W.parse_prepare_output(line)
        self.assertEqual(result["namespaces"], [0, 1, 2])
        self.assertEqual(result["upload_user"], "Maintenance script")

    def test_invalid(self):
        for data in ({"namespaces": [], "upload_user": "x"}, {"namespaces": [True], "upload_user": "x"},
                     {"namespaces": [0], "upload_user": "a/b"}, [0]):
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    W.parse_prepare_output(json.dumps(data))


class SafeRmtreeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name).resolve()
        self.work = self.base / "spool" / "work"
        self.queue = self.base / "spool" / "queue"
        self.outside = self.base / "outside"
        for d in (self.work, self.queue, self.outside):
            d.mkdir(parents=True)
        (self.outside / "precious.txt").write_text("keep me")
        self.roots = (self.work, self.queue)

    def tearDown(self):
        self._tmp.cleanup()

    def test_deletes_inside(self):
        target = self.work / "42" / "crawl"
        target.mkdir(parents=True)
        (target / "a.bin").write_bytes(b"x" * 100)
        (target / "b.bin").write_bytes(b"y" * 23)
        self.assertEqual(W.safe_rmtree(target, self.roots, log=lambda _m: None), 123)
        self.assertFalse(target.exists())
        file_target = self.queue / "1.json"
        file_target.write_text("{}")
        self.assertEqual(W.safe_rmtree(file_target, self.roots, log=lambda _m: None), 2)
        self.assertFalse(file_target.exists())

    def test_missing_is_fine(self):
        self.assertEqual(W.safe_rmtree(self.work / "nope", self.roots), 0)

    def test_refuses_outside(self):
        for path in (self.outside, self.outside / "precious.txt", self.base / "spool",
                     self.work / ".." / ".." / "outside", Path("/")):
            with self.subTest(path=path):
                with self.assertRaises(W.UnsafePathError):
                    W.safe_rmtree(path, self.roots)
        self.assertTrue((self.outside / "precious.txt").exists())

    def test_refuses_the_roots_themselves(self):
        for root in self.roots:
            with self.assertRaises(W.UnsafePathError):
                W.safe_rmtree(root, self.roots)
        self.assertTrue(self.work.is_dir())

    def test_refuses_symlinks(self):
        link = self.work / "42"
        link.symlink_to(self.outside, target_is_directory=True)
        with self.assertRaises(W.UnsafePathError):
            W.safe_rmtree(link, self.roots)
        with self.assertRaises(W.UnsafePathError):
            W.safe_rmtree(link / "precious.txt", self.roots)
        file_link = self.queue / "1.json"
        file_link.symlink_to(self.outside / "precious.txt")
        with self.assertRaises(W.UnsafePathError):
            W.safe_rmtree(file_link, self.roots)
        self.assertTrue(link.is_symlink())
        self.assertEqual((self.outside / "precious.txt").read_text(), "keep me")


class PickNextTest(unittest.TestCase):
    def st(self, status, **kw):
        return {"status": status, **kw}

    def at(self, minutes):
        return W.iso(NOW + timedelta(minutes=minutes))

    def test_running_due_wins(self):
        states = {1: self.st("running", next_try=self.at(-1)),
                  2: self.st("waiting-dump", next_check=self.at(-60))}
        self.assertEqual(W.pick_next(states, [(5, 1.0)], NOW), ("resume", 1))

    def test_running_without_next_try_is_due(self):
        self.assertEqual(W.pick_next({3: self.st("running", next_try=None)}, [], NOW), ("resume", 3))

    def test_running_not_due_then_waiting_due(self):
        states = {1: self.st("running", next_try=self.at(10)),
                  2: self.st("waiting-dump", next_check=self.at(-5))}
        self.assertEqual(W.pick_next(states, [(5, 1.0)], NOW), ("recheck", 2))

    def test_waiting_not_due_falls_through_to_queue_order(self):
        states = {1: self.st("running", next_try=self.at(10)),
                  2: self.st("waiting-dump", next_check=self.at(60)),
                  3: self.st("failed"), 4: self.st("done"), 6: self.st("deleted")}
        queue = [(7, 200.0), (9, 100.0), (4, 100.0)]
        self.assertEqual(W.pick_next(states, queue, NOW), ("claim", 4))

    def test_earliest_due_first(self):
        states = {1: self.st("running", next_try=self.at(-1)), 2: self.st("running", next_try=self.at(-30))}
        self.assertEqual(W.pick_next(states, [], NOW), ("resume", 2))

    def test_nothing_to_do(self):
        states = {1: self.st("waiting-dump", next_check=self.at(5)), 2: self.st("failed")}
        self.assertIsNone(W.pick_next(states, [], NOW))


FAKE_MWSCRIPT = '''\
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
with open(here / "calls.jsonl", "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
if sys.argv[2] == "WikiOasisMagic:FandomImportCallback" and (here / "fail-callbacks").exists():
    sys.exit(1)
'''


class SpoolTestCase(unittest.TestCase):
    """A temporary spool and a fake MediaWiki that records its calls."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.fake = base / "fake-mw"
        self.fake.mkdir()
        (self.fake / "mwscript.py").write_text(FAKE_MWSCRIPT)
        spool = base / "spool"
        spool.mkdir()
        self.now = NOW
        self.cfg = W.Config(spool_dir=spool, central_wiki="metawiki", php=sys.executable,
                            mwscript=str(self.fake / "mwscript.py"), proxy="http://127.0.0.1:9",
                            user_agent="test")
        self.worker = W.Worker(self.cfg, clock=lambda: self.now)
        self.worker.ensure_dirs()

    def tearDown(self):
        self.worker.close_logs()
        self._tmp.cleanup()

    def calls(self):
        path = self.fake / "calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def events(self):
        out = []
        for argv in self.calls():
            if argv[1] == "WikiOasisMagic:FandomImportCallback":
                out.append(next(a.split("=", 1)[1] for a in argv if a.startswith("--event=")))
        return out

    def queue(self, data, import_id=42):
        path = self.cfg.queue_dir / f"{import_id}.json"
        path.write_text(json.dumps(data))
        return path


class ClaimAndDiscardTest(SpoolTestCase):
    def test_claim_valid_manifest(self):
        self.queue(good_manifest())
        st = self.worker.claim(42)
        self.assertEqual(st["status"], "running")
        self.assertFalse((self.cfg.queue_dir / "42.json").exists())
        self.assertTrue(self.worker.manifest_path(42).is_file())
        self.assertTrue(self.worker.tmp_dir(42).is_dir())
        self.assertEqual(self.events(), ["started"])
        self.assertIn("--stage=resolve", self.calls()[0])
        self.assertIn("--wiki=metawiki", self.calls()[0])

    def test_invalid_manifest_is_deleted_and_reported(self):
        source = dict(good_manifest()["source"], api_url="https://evil.example/api.php")
        self.queue(good_manifest(source=source))
        self.assertIsNone(self.worker.claim(42))
        self.assertFalse((self.cfg.queue_dir / "42.json").exists())
        self.assertFalse(self.worker.work_dir(42).exists())
        self.assertEqual(self.events(), ["failed"])
        argv = self.calls()[0]
        self.assertTrue(any(a.startswith("--message=Invalid import request") for a in argv))
        self.assertIn('--data={"files_expire":null}', argv)

    def test_unattributable_manifest_is_dropped_silently(self):
        self.queue(good_manifest(id=7), import_id=42)
        self.assertIsNone(self.worker.claim(42))
        self.assertEqual(self.calls(), [])
        self.assertFalse(self.worker.work_dir(42).exists())

    def test_retry_keeps_completed_stages(self):
        self.queue(good_manifest())
        st = self.worker.claim(42)
        st.update(status="failed", completed=["resolve", "prepare"], attempts={"dump": 3},
                  files_expire=W.iso(self.now + timedelta(days=3)))
        self.worker.save_state(st)
        (self.worker.work_dir(42) / "siteinfo.json").write_text("{}")
        self.queue(good_manifest(attempt=2))
        st = self.worker.claim(42)
        self.assertEqual(st["status"], "running")
        self.assertEqual(st["completed"], ["resolve", "prepare"])
        self.assertEqual(st["attempts"], {})
        self.assertTrue((self.worker.work_dir(42) / "siteinfo.json").exists())
        self.assertIn("--stage=dump", self.calls()[-1])

    def test_discard_deletes_files_and_reports(self):
        self.queue(good_manifest())
        st = self.worker.claim(42)
        st.update(status="failed", files_expire=W.iso(self.now + timedelta(days=3)))
        self.worker.save_state(st)
        (self.worker.work_dir(42) / "dump.xml.7z").write_bytes(b"x" * 1000)
        discard = self.cfg.queue_dir / "42.discard"
        discard.write_text(json.dumps({"version": 1, "id": 42, "central_wiki": "metawiki"}))
        self.worker.process_discards()
        self.assertFalse(discard.exists())
        self.assertFalse(self.worker.work_dir(42).exists())
        self.assertEqual(self.events(), ["started", "files-deleted"])

    def test_undelivered_callback_is_kept_and_retried(self):
        (self.fake / "fail-callbacks").touch()
        discard = self.cfg.queue_dir / "42.discard"
        discard.write_text(json.dumps({"version": 1, "id": 42, "central_wiki": "metawiki"}))
        self.worker.process_discards()
        self.assertFalse(discard.exists())
        st = self.worker.load_state(42)
        self.assertEqual(st["status"], "deleted")
        self.assertEqual([c["event"] for c in st["pending_callbacks"]], ["files-deleted"])
        (self.fake / "fail-callbacks").unlink()
        self.worker.cleanup_work()
        self.assertTrue(self.worker.work_dir(42).exists(), "backoff must hold the retry")
        self.now += timedelta(hours=2)
        self.worker.cleanup_work()
        self.assertFalse(self.worker.work_dir(42).exists())
        self.assertEqual(self.events(), ["files-deleted", "files-deleted"])

    def test_failed_files_expire(self):
        self.queue(good_manifest())
        st = self.worker.claim(42)
        st.update(status="failed", files_expire=W.iso(self.now + timedelta(days=3)))
        self.worker.save_state(st)
        self.worker.cleanup_work()
        self.assertTrue(self.worker.work_dir(42).exists())
        self.now += timedelta(days=3, minutes=1)
        self.worker.cleanup_work()
        self.assertFalse(self.worker.work_dir(42).exists())
        self.assertEqual(self.events(), ["started", "files-deleted"])


class StageMachineTest(SpoolTestCase):
    def claimed(self):
        self.queue(good_manifest())
        return self.worker.claim(42)

    def test_failures_back_off_then_fail(self):
        st = self.claimed()
        with mock.patch.object(W.ImportRunner, "stage_resolve", side_effect=W.StageError("boom")):
            W.ImportRunner(self.worker, st).run()
            self.assertEqual(st["status"], "running")
            self.assertEqual(st["attempts"], {"resolve": 1})
            self.assertEqual(st["next_try"], W.iso(self.now + timedelta(minutes=15)))
            self.assertEqual(W.pick_next({42: st}, [], self.now), None)
            self.now += timedelta(minutes=16)
            W.ImportRunner(self.worker, st).run()
            self.assertEqual(st["next_try"], W.iso(self.now + timedelta(hours=1)))
            self.now += timedelta(hours=2)
            W.ImportRunner(self.worker, st).run()
        st = self.worker.load_state(42)
        self.assertEqual(st["status"], "failed")
        self.assertEqual(st["files_expire"], W.iso(self.now + timedelta(days=3)))
        self.assertEqual(self.events(), ["started", "failed"])
        failed = self.calls()[-1]
        self.assertIn("--stage=resolve", failed)
        self.assertIn("--message=boom", failed)

    def test_deferral_does_not_count_an_attempt(self):
        st = self.claimed()
        deferral = W.Deferral(3600, "Waiting for disk space", {"disk_free_bytes": 1})
        with mock.patch.object(W.ImportRunner, "stage_resolve", return_value=deferral):
            W.ImportRunner(self.worker, st).run()
        self.assertEqual(st["attempts"], {})
        self.assertEqual(st["waiting_for"], "disk")
        self.assertEqual(st["next_try"], W.iso(self.now + timedelta(hours=1)))
        progress = self.calls()[-1]
        self.assertIn("--event=progress", progress)
        self.assertIn("--message=Waiting for disk space", progress)

    def test_interrupted_stage_is_counted_separately(self):
        st = self.claimed()
        st["inflight"] = {"stage": "resolve", "pid": 1, "started_at": W.iso(self.now)}
        self.worker.save_state(st)
        with mock.patch.object(W.ImportRunner, "stage_resolve", side_effect=W.StageError("x")):
            W.ImportRunner(self.worker, st).run()
        self.assertEqual(st["interruptions"], {"resolve": 1})
        self.assertEqual(st["attempts"], {"resolve": 1})

    def test_waiting_for_a_dump(self):
        st = self.claimed()
        st["completed"] = ["resolve", "prepare"]
        st["summary"]["fandom_wikiid"] = "muppet"
        self.worker.save_state(st)

        def missing(_runner, variant, url):
            return W.DumpCheck(variant, url, 403)

        with mock.patch.object(W.ImportRunner, "check_dump", missing):
            W.ImportRunner(self.worker, st).run()
            st = self.worker.load_state(42)
            self.assertEqual(st["status"], "waiting-dump")
            self.assertIsNone(st["inflight"])
            self.assertEqual(st["next_check"], W.iso(self.now + timedelta(hours=24)))
            waiting = self.calls()[-1]
            self.assertIn("--event=waiting-dump", waiting)
            data = json.loads(next(a for a in waiting if a.startswith("--data="))[len("--data="):])
            self.assertEqual([d["variant"] for d in data["dumps"]], ["full", "current"])
            self.assertEqual(data["dumps"][0]["status"], 403)
            self.assertIsNone(W.pick_next({42: st}, [], self.now + timedelta(hours=1)))

            for _ in range(13):
                self.now += timedelta(hours=24)
                self.assertEqual(W.pick_next({42: st}, [], self.now), ("recheck", 42))
                W.ImportRunner(self.worker, st).run(recheck=True)
                st = self.worker.load_state(42)
                self.assertEqual(st["status"], "waiting-dump")
                self.assertEqual(st["interruptions"], {})
            self.now += timedelta(hours=24)
            W.ImportRunner(self.worker, st).run(recheck=True)
        st = self.worker.load_state(42)
        self.assertEqual(st["status"], "failed")
        self.assertIn("No usable Fandom XML dump", st["error"])
        self.assertEqual(self.events().count("stage"), 15)
        self.assertEqual(self.events().count("waiting-dump"), 14)

    def test_happy_path_through_cmd_run(self):
        self.queue(good_manifest())
        names = ["stage_resolve", "stage_prepare", "stage_dump", "stage_pages", "stage_images", "stage_upload"]
        patches = [mock.patch.object(W.ImportRunner, n, return_value=None) for n in names]
        for p in patches:
            p.start()
        try:
            self.assertEqual(self.worker.cmd_run(), 0)
        finally:
            for p in patches:
                p.stop()
        self.assertFalse(self.worker.work_dir(42).exists())
        self.assertEqual(self.events(), ["started", "stage", "stage", "stage", "stage", "stage", "stage", "done"])
        self.assertTrue(any(argv[1] == "initSiteStats" and "--wiki=muppetwiki" in argv for argv in self.calls()))
        self.assertTrue((self.cfg.logs_dir / "42.log").is_file())


if __name__ == "__main__":
    unittest.main()
