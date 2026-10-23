"""Unit tests for fandom_import_worker.py (stdlib unittest; not deployed by Salt).

Run from the repository root:

    python3 -m unittest discover -s salt/fandom_import/tests -v

MediaWiki is replaced by a tiny fake mwscript (run with this interpreter) that
records every maintenance-script call, so the claim, discard, callback and
stage-retry paths run for real against a temporary spool.
"""

from __future__ import annotations

import dataclasses
import gzip
import importlib.util
import io
import json
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
        "source": {
            "key": "muppet",
            "subdomain": "muppet",
            "lang": None,
            "base_url": "https://muppet.fandom.com",
            "api_url": "https://muppet.fandom.com/api.php",
        },
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
    source = {
        "key": "harrypotter/de",
        "subdomain": "harrypotter",
        "lang": "de",
        "base_url": "https://harrypotter.fandom.com/de",
        "api_url": "https://harrypotter.fandom.com/de/api.php",
    }
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
            source = {
                "key": subdomain,
                "subdomain": subdomain,
                "lang": None,
                "base_url": f"https://{subdomain}.fandom.com",
                "api_url": f"https://{subdomain}.fandom.com/api.php",
            }
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
            source = lang_source(
                lang=lang,
                key=f"harrypotter/{lang}",
                base_url=f"https://harrypotter.fandom.com/{lang}",
                api_url=f"https://harrypotter.fandom.com/{lang}/api.php",
            )
            with self.subTest(lang=lang):
                with self.assertRaises(W.ManifestError):
                    self.validate(good_manifest(source=source))

    def test_lang_with_region_is_fine(self):
        source = lang_source(
            lang="pt-br",
            key="harrypotter/pt-br",
            base_url="https://harrypotter.fandom.com/pt-br",
            api_url="https://harrypotter.fandom.com/pt-br/api.php",
        )
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
        for overrides in (
            {"version": "1"},
            {"version": True},
            {"id": True},
            {"id": "42"},
            {"prefer_full_history": "yes"},
            {"attempt": 0},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaises(W.ManifestError):
                    self.validate(good_manifest(**overrides), expected_id=None)

    def test_upload_user_and_summary(self):
        for overrides in (
            {"upload_user": "Fandom/import"},
            {"upload_user": "a" * 86},
            {"upload_user": ""},
            {"upload_user": "x\ty"},
            {"summary": "line\nbreak"},
            {"summary": "x" * 501},
            {"username_prefix": "Wikia"},
            {"username_prefix": "a" * 17},
        ):
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
        expected = SAMPLE_DUMP.replace(page_block(SAMPLE_DUMP, "Message Wall:Kermit"), "").replace(
            page_block(SAMPLE_DUMP, "Board Thread:Fozzie"), ""
        )
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
        truncated = SAMPLE_DUMP[: SAMPLE_DUMP.index("<id>20</id>")]
        with self.assertRaises(W.DumpFormatError):
            self.run_filter(truncated, {0})

    def test_missing_footer_is_reported(self):
        _, stats = self.run_filter(SAMPLE_DUMP.replace("</mediawiki>\n", ""), {0})
        self.assertFalse(stats.saw_footer)

    def test_check_is_called(self):
        calls = []
        W.filter_dump_lines(
            io.StringIO(SAMPLE_DUMP), lambda _l: None, {0}, check=lambda: calls.append(1), check_every=5
        )
        self.assertGreater(len(calls), 3)

    def test_bytes_round_trip_through_gzip(self):
        """Same text layers the worker uses: invalid UTF-8 and CR survive."""
        raw = SAMPLE_DUMP.encode("utf-8").replace(b"Frog.", b"Fr\xffog.\r")
        with tempfile.TemporaryDirectory() as tmp:
            gz = Path(tmp) / "pages.xml.gz"
            reader = io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8", errors="surrogateescape", newline="\n")
            with gzip.open(gz, "wt", compresslevel=6, encoding="utf-8", errors="surrogateescape", newline="\n") as out:
                W.filter_dump_lines(reader, out.write, {0, 2, 1200, 1201})
            self.assertEqual(gzip.decompress(gz.read_bytes()), raw)
            W.verify_gzip_xml(gz)


class DumpUrlTest(unittest.TestCase):
    def test_full_first(self):
        self.assertEqual(
            W.dump_candidates("muppet", True),
            [
                ("full", "https://s3.amazonaws.com/wikia_xml_dumps/m/mu/muppet_pages_full.xml.7z"),
                ("current", "https://s3.amazonaws.com/wikia_xml_dumps/m/mu/muppet_pages_current.xml.7z"),
            ],
        )

    def test_current_first(self):
        self.assertEqual([v for v, _ in W.dump_candidates("deharrypotter", False)], ["current", "full"])
        self.assertTrue(
            W.dump_candidates("deharrypotter", False)[0][1].startswith(
                "https://s3.amazonaws.com/wikia_xml_dumps/d/de/deharrypotter_pages_current"
            )
        )

    def test_one_letter_id(self):
        self.assertEqual(
            W.dump_candidates("a", True)[0][1], "https://s3.amazonaws.com/wikia_xml_dumps/a/a/a_pages_full.xml.7z"
        )

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


def entry(name, size, timestamp):
    return W.ImageEntry(name=name, size=size, timestamp=timestamp)


class ImagesTxtTest(unittest.TestCase):
    def parse(self, text):
        return W.parse_images_txt(io.StringIO(text))

    def row(self, *fields):
        return "\t".join(fields) + "\n"

    def test_complete_list_with_nulls(self):
        text = (
            self.row("Kermit.png", "https://x/a", "Uploader", "1234", "abc", "2020-01-02T03:04:05Z")
            + self.row("Ghost.png", "https://x/b", "null", "null", "null", "null")
            + "--END--\n"
        )
        listing = self.parse(text)
        self.assertTrue(listing.complete)
        self.assertTrue(listing.usable)
        self.assertEqual(listing.malformed, [])
        self.assertEqual(
            listing.entries, [entry("Kermit.png", 1234, "2020-01-02T03:04:05Z"), entry("Ghost.png", 0, None)]
        )
        self.assertEqual(listing.total_bytes, 1234)

    def test_missing_end_marker(self):
        listing = self.parse(self.row("A.png", "u", "x", "1", "s", "2020-01-02T03:04:05Z"))
        self.assertFalse(listing.complete)
        self.assertFalse(listing.usable)
        self.assertEqual(len(listing.entries), 1)
        self.assertFalse(self.parse("").complete)

    def test_end_marker_must_be_last(self):
        text = "--END--\n" + self.row("A.png", "u", "x", "1", "s", "2020-01-02T03:04:05Z")
        self.assertFalse(self.parse(text).complete)

    def test_reading_stops_at_a_blank_line_like_wikiteam3(self):
        text = self.row("A.png", "u", "x", "1", "s", "null") + "\n" + "--END--\n"
        listing = self.parse(text)
        self.assertFalse(listing.complete)

    def test_malformed_lines_are_reported_and_left_out(self):
        text = (
            self.row("Good.png", "u", "x", "10", "s", "2020-01-02T03:04:05Z")
            + self.row("Short.png", "u", "x", "10", "s")
            + self.row("BadSize.png", "u", "x", "ten", "s", "2020-01-02T03:04:05Z")
            + self.row("BadTime.png", "u", "x", "10", "s", "2020-01-02 03:04:05")
            + "no tabs at all\n"
            + self.row("", "u", "x", "10", "s", "null")
            + "--END--\n"
        )
        listing = self.parse(text)
        self.assertTrue(listing.complete)
        self.assertEqual(listing.malformed, [2, 3, 4, 5, 6])
        self.assertFalse(listing.usable)
        self.assertEqual([e.name for e in listing.entries], ["Good.png"])


class WindowPlanTest(unittest.TestCase):
    def plan(self, entries, max_bytes=1000, max_files=1000):
        return W.plan_image_windows(entries, max_bytes, max_files)

    def test_byte_limit(self):
        entries = [entry(f"f{i}.png", 400, f"2020-01-01T00:00:0{i}Z") for i in range(5)]
        windows = self.plan(entries, max_bytes=1000)
        self.assertEqual([w["files"] for w in windows], [2, 2, 1])
        self.assertEqual([w["bytes"] for w in windows], [800, 800, 400])
        self.assertTrue(all(w["done"] is False for w in windows))

    def test_file_limit(self):
        entries = [entry(f"f{i}.png", 1, f"2020-01-01T00:00:0{i}Z") for i in range(7)]
        windows = self.plan(entries, max_files=3)
        self.assertEqual([w["files"] for w in windows], [3, 3, 1])

    def test_open_first_and_last_bounds_and_inner_bounds(self):
        entries = [
            entry("a", 600, "2020-01-01T00:00:00Z"),
            entry("b", 600, "2021-01-01T00:00:00Z"),
            entry("c", 300, "2022-01-01T00:00:00Z"),
            entry("d", 300, "2023-01-01T00:00:00Z"),
        ]
        windows = self.plan(entries)
        self.assertEqual(
            [(w["start"], w["end"]) for w in windows],
            [
                ("1970-01-01T00:00:00Z", "2020-01-01T00:00:00Z"),
                ("2021-01-01T00:00:00Z", "2022-01-01T00:00:00Z"),
                ("2023-01-01T00:00:00Z", "9999-12-31T23:59:59Z"),
            ],
        )
        self.assertEqual(W.window_interval(windows[0]), "1970-01-01T00:00:00Z/2020-01-01T00:00:00Z")

    def test_single_window_covers_everything(self):
        windows = self.plan([entry("a", 1, "2020-01-01T00:00:00Z"), entry("b", 1, "2020-06-01T00:00:00Z")])
        self.assertEqual([(w["start"], w["end"]) for w in windows], [("1970-01-01T00:00:00Z", "9999-12-31T23:59:59Z")])

    def test_same_second_group_is_never_split(self):
        same = "2020-01-01T00:00:05Z"
        entries = (
            [entry("a", 100, "2020-01-01T00:00:01Z")]
            + [entry(f"s{i}", 100, same) for i in range(5)]
            + [entry("z", 100, "2020-01-01T00:00:09Z")]
        )
        windows = self.plan(entries, max_bytes=250, max_files=3)
        self.assertEqual([w["files"] for w in windows], [1, 5, 1])
        self.assertEqual((windows[1]["start"], windows[1]["end"]), (same, same))
        self.assertEqual(windows[1]["bytes"], 500)

    def test_unsorted_input_and_null_timestamps(self):
        entries = [
            entry("late", 10, "2024-01-01T00:00:00Z"),
            entry("ghost", 99999, None),
            entry("early", 10, "2019-01-01T00:00:00Z"),
        ]
        windows = self.plan(entries, max_bytes=10)
        self.assertEqual([w["files"] for w in windows], [1, 1])
        self.assertEqual(windows[0]["end"], "2019-01-01T00:00:00Z")
        self.assertEqual(windows[1]["start"], "2024-01-01T00:00:00Z")
        self.assertEqual(sum(w["bytes"] for w in windows), 20)

    def test_nothing_to_plan(self):
        self.assertEqual(self.plan([]), [])
        self.assertEqual(self.plan([entry("ghost", 5, None)]), [])


class PrepareOutputTest(unittest.TestCase):
    def test_valid(self):
        line = json.dumps(
            {
                "namespaces": [0, 2, 1, 0],
                "upload_user": "Maintenance script",
                "enabled_extensions": ["Cite"],
                "created_namespaces": [{"id": 112, "name": "Transcript"}],
                "warnings": ["x"],
            }
        )
        result = W.parse_prepare_output(line)
        self.assertEqual(result["namespaces"], [0, 1, 2])
        self.assertEqual(result["upload_user"], "Maintenance script")

    def test_invalid(self):
        for data in (
            {"namespaces": [], "upload_user": "x"},
            {"namespaces": [True], "upload_user": "x"},
            {"namespaces": [0], "upload_user": "a/b"},
            [0],
        ):
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
        for path in (
            self.outside,
            self.outside / "precious.txt",
            self.base / "spool",
            self.work / ".." / ".." / "outside",
            Path("/"),
        ):
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
        states = {1: self.st("running", next_try=self.at(-1)), 2: self.st("waiting-dump", next_check=self.at(-60))}
        self.assertEqual(W.pick_next(states, [(5, 1.0)], NOW), ("resume", 1))

    def test_running_without_next_try_is_due(self):
        self.assertEqual(W.pick_next({3: self.st("running", next_try=None)}, [], NOW), ("resume", 3))

    def test_running_not_due_then_waiting_due(self):
        states = {1: self.st("running", next_try=self.at(10)), 2: self.st("waiting-dump", next_check=self.at(-5))}
        self.assertEqual(W.pick_next(states, [(5, 1.0)], NOW), ("recheck", 2))

    def test_waiting_not_due_falls_through_to_queue_order(self):
        states = {
            1: self.st("running", next_try=self.at(10)),
            2: self.st("waiting-dump", next_check=self.at(60)),
            3: self.st("failed"),
            4: self.st("done"),
            6: self.st("deleted"),
        }
        queue = [(7, 200.0), (9, 100.0), (4, 100.0)]
        self.assertEqual(W.pick_next(states, queue, NOW), ("claim", 4))

    def test_earliest_due_first(self):
        states = {1: self.st("running", next_try=self.at(-1)), 2: self.st("running", next_try=self.at(-30))}
        self.assertEqual(W.pick_next(states, [], NOW), ("resume", 2))

    def test_nothing_to_do(self):
        states = {1: self.st("waiting-dump", next_check=self.at(5)), 2: self.st("failed")}
        self.assertIsNone(W.pick_next(states, [], NOW))


FAKE_MWSCRIPT = """\
import json, sys
from pathlib import Path
here = Path(__file__).resolve().parent
with open(here / "calls.jsonl", "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
script = sys.argv[2]
if script == "WikiOasisMagic:FandomImportCallback" and (here / "fail-callbacks").exists():
    sys.exit(1)
if script == "importImages":
    marker = here / "fail-importImages-once"
    if marker.exists():
        marker.unlink()
        print("PHP Fatal error: simulated crash")
        sys.exit(255)
    folder = Path(sys.argv[-1])
    names = sorted(p.name for p in folder.rglob("*") if p.is_file())
    wiki = here / "on-wiki.json"
    on_wiki = set(json.loads(wiki.read_text())) if wiki.exists() else set()
    added = skipped = 0
    for name in names:
        if name in on_wiki:
            print(name + " exists, skipping")
            skipped += 1
            continue
        print("Importing " + name + "...done.")
        added += 1
        on_wiki.add(name)
        with open(here / "imported.jsonl", "a") as f:
            f.write(json.dumps(name) + "\\n")
    wiki.write_text(json.dumps(sorted(on_wiki)))
    print()
    print("Found: " + str(len(names)))
    if added:
        print("Added: " + str(added))
    if skipped:
        print("Skipped: " + str(skipped))
"""


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
        self.cfg = W.Config(
            spool_dir=spool,
            central_wiki="metawiki",
            php=sys.executable,
            mwscript=str(self.fake / "mwscript.py"),
            user_agent="test",
        )
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
        st.update(
            status="failed",
            completed=["resolve", "prepare"],
            attempts={"dump": 3},
            files_expire=W.iso(self.now + timedelta(days=3)),
        )
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
            data = json.loads(next(a for a in waiting if a.startswith("--data="))[len("--data=") :])
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


FAKE_WIKITEAM3 = """\
import json, sys
from datetime import datetime
from pathlib import Path
here = Path(__file__).resolve().parent
args = sys.argv[1:]
def opt(name):
    return args[args.index(name) + 1]
path = Path(opt("--path"))
interval = opt("--image-timestamp-interval")
resume = "--resume" in args
images = path / "images"
mismatch = path / "images_mismatch"
present = sorted(p.name for d in (images, mismatch) if d.is_dir() for p in d.iterdir())
with open(here / "wt3-calls.jsonl", "a") as f:
    threshold = opt("--index-check-threshold") if "--index-check-threshold" in args else None
    f.write(json.dumps({"interval": interval, "resume": resume, "present": present,
                        "threshold": threshold}) + "\\n")
listfile = path / "muppet.fandom.com-20261009-images.txt"
if not resume:
    path.mkdir()
    (path / "config.json").write_text("{}")
    with open(listfile, "w") as f:
        for e in json.loads((here / "catalog.json").read_text()):
            f.write("\\t".join([e["name"], "https://static.wikia.nocookie.net/x", "Uploader",
                               str(e["size"]), "null", e["timestamp"]]) + "\\n")
        if (here / "no-end-once").exists():
            (here / "no-end-once").unlink()
        else:
            f.write("--END--\\n")
fmt = "%Y-%m-%dT%H:%M:%SZ"
low, high = (datetime.strptime(x, fmt) for x in interval.split("/"))
images.mkdir(exist_ok=True)
mismatch.mkdir(exist_ok=True)
written = 0
for line in listfile.read_text().splitlines():
    if line == "--END--":
        continue
    name, url, uploader, size, sha1, ts = line.split("\\t")
    if ts != "null" and not low <= datetime.strptime(ts, fmt) <= high:
        continue
    target = (mismatch if name.startswith("mm_") else images) / name
    if target.exists():
        continue
    if resume and (here / "blocked-once").exists():
        continue
    target.write_bytes(b"x" * int(size))
    written += 1
    if resume and written == 1 and (here / "crash-once").exists():
        (here / "crash-once").unlink()
        print("simulated crash")
        sys.exit(1)
"""

CATALOG = [
    {"name": "a.png", "size": 100, "timestamp": "2020-01-01T00:00:00Z"},
    {"name": "b.png", "size": 100, "timestamp": "2020-01-01T00:00:01Z"},
    {"name": "c.png", "size": 100, "timestamp": "2020-01-01T00:00:01Z"},
    {"name": "mm_d.png", "size": 100, "timestamp": "2021-06-01T00:00:00Z"},
    {"name": "e.png", "size": 500, "timestamp": "2022-01-01T00:00:00Z"},
    {"name": "f.png", "size": 100, "timestamp": "2023-01-01T00:00:00Z"},
    {"name": "n.png", "size": 50, "timestamp": "null"},
]
LIST_INTERVAL = "1970-01-01T00:00:00Z/1970-01-01T00:00:01Z"
WINDOWS = [
    "1970-01-01T00:00:00Z/2020-01-01T00:00:00Z",
    "2020-01-01T00:00:01Z/2020-01-01T00:00:01Z",
    "2021-06-01T00:00:00Z/2021-06-01T00:00:00Z",
    "2022-01-01T00:00:00Z/2022-01-01T00:00:00Z",
    "2023-01-01T00:00:00Z/9999-12-31T23:59:59Z",
]


class ImageBatchTest(SpoolTestCase):
    """The images/upload stages against a fake wikiteam3 and fake MediaWiki.

    With 250-byte batches the catalog plans into five windows: a | b+c (same
    second) | mm_d (lands in images_mismatch) | e (500 bytes, alone) | f, and
    n.png has a "null" timestamp, so it is in none.
    """

    def setUp(self):
        super().setUp()
        wt3 = self.fake / "wikiteam3"
        wt3.write_text(f"#!{sys.executable}\n" + FAKE_WIKITEAM3)
        wt3.chmod(0o755)
        (self.fake / "catalog.json").write_text(json.dumps(CATALOG))
        self.cfg = dataclasses.replace(
            self.cfg,
            wikiteam3=str(wt3),
            image_batch_bytes=250,
            image_batch_files=1000,
            disk_headroom_bytes=0,
            min_free_bytes=0,
        )
        self.worker.close_logs()
        self.worker = W.Worker(self.cfg, clock=lambda: self.now)
        self.free = 10**12
        patcher = mock.patch.object(W.ImportRunner, "free_bytes", lambda _runner: self.free)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.queue(good_manifest())
        st = self.worker.claim(42)
        st["completed"] = ["resolve", "prepare", "dump", "pages"]
        st["stage_data"]["prepare"] = {"namespaces": [0, 6], "upload_user": "Fandom import"}
        st["summary"]["fandom_files"] = len(CATALOG)
        self.worker.save_state(st)

    def run_import(self):
        W.ImportRunner(self.worker, self.worker.load_state(42)).run()
        return self.worker.load_state(42)

    def wt3_calls(self):
        path = self.fake / "wt3-calls.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def imported(self):
        path = self.fake / "imported.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def done_data(self):
        argv = [a for a in self.calls() if "--event=done" in a][-1]
        return json.loads(next(a for a in argv if a.startswith("--data="))[len("--data=") :])

    def assert_finished(self):
        self.assertFalse(self.worker.work_dir(42).exists())
        self.assertEqual(sorted(self.imported()), sorted(e["name"] for e in CATALOG))
        self.assertEqual(self.imported()[-1], "n.png", "null-timestamp files go in the final sweep")
        data = self.done_data()
        self.assertEqual((data["images_total"], data["images_bytes_total"]), (7, 1050))
        self.assertEqual((data["batches_total"], data["batches_done"]), (5, 5))
        self.assertEqual((data["images_fetched"], data["images_added"]), (7, 7))
        self.assertEqual((data["images_skipped"], data["images_failed"]), (0, 0))

    def test_each_batch_is_downloaded_imported_and_deleted(self):
        self.assertIsNone(self.run_import())
        calls = self.wt3_calls()
        self.assertEqual(
            [(c["interval"], c["resume"]) for c in calls], [(LIST_INTERVAL, False)] + [(w, True) for w in WINDOWS]
        )
        for call in calls[1:]:
            self.assertEqual(call["present"], ["n.png"], "the previous batch must be gone")
        self.assert_finished()
        progress = [a for a in self.calls() if "--event=progress" in a]
        self.assertTrue(any('"batches_total":5' in a for argv in progress for a in argv))

    def test_disk_check_is_per_batch(self):
        self.free = 300
        st = self.run_import()
        self.assertEqual([w["done"] for w in st["stage_data"]["images"]["windows"]], [True, True, True, False, False])
        self.assertEqual(st["status"], "running")
        self.assertEqual(st["waiting_for"], "disk")
        self.assertEqual(st["attempts"], {})
        self.assertEqual(st["next_try"], W.iso(self.now + timedelta(hours=1)))
        self.assertEqual(st["pending_progress"]["message"], "Waiting for disk space")
        self.assertEqual(st["pending_progress"]["data"]["disk_needed_bytes"], 500)
        self.assertEqual(len(self.wt3_calls()), 4)
        self.assertEqual(st["summary"]["batches_done"], 3)
        self.free = 10**12
        self.now += timedelta(minutes=61)
        self.assertEqual(W.pick_next({42: st}, [], self.now), ("resume", 42))
        self.run_import()
        self.assertEqual([c["interval"] for c in self.wt3_calls()], [LIST_INTERVAL] + WINDOWS)
        self.assert_finished()

    def test_crash_during_download_reruns_the_same_batch(self):
        (self.fake / "crash-once").touch()
        st = self.run_import()
        self.assertEqual(st["attempts"], {"images": 1})
        self.assertFalse(st["stage_data"]["images"]["windows"][0].get("fetched"))
        self.now += timedelta(minutes=16)
        self.run_import()
        calls = self.wt3_calls()
        self.assertEqual([c["interval"] for c in calls], [LIST_INTERVAL, WINDOWS[0]] + WINDOWS)
        self.assertEqual(calls[2]["present"], ["a.png", "n.png"])
        self.assert_finished()

    def test_wikiteam3_is_told_to_skip_its_index_php_check(self):
        self.run_import()
        self.assertEqual({c["threshold"] for c in self.wt3_calls()}, {"0"})

    def test_a_batch_with_no_files_fetched_fails_and_is_downloaded_again(self):
        (self.fake / "blocked-once").touch()
        st = self.run_import()
        self.assertEqual(st["attempts"], {"images": 1})
        self.assertIn("Fandom sent none of the 1 files in batch 1/5", st["error"])
        window = st["stage_data"]["images"]["windows"][0]
        self.assertFalse(window.get("fetched"))
        self.assertNotIn("fetched_files", window)
        (self.fake / "blocked-once").unlink()
        self.now += timedelta(minutes=16)
        self.run_import()
        self.assertEqual([c["interval"] for c in self.wt3_calls()], [LIST_INTERVAL, WINDOWS[0]] + WINDOWS)
        self.assert_finished()

    def test_crash_during_import_resumes_at_the_import(self):
        (self.fake / "fail-importImages-once").touch()
        st = self.run_import()
        window = st["stage_data"]["images"]["windows"][0]
        self.assertTrue(window["fetched"])
        self.assertFalse(window["done"])
        self.assertTrue((self.worker.work_dir(42) / "crawl" / "batch" / "images" / "a.png").exists())
        self.now += timedelta(minutes=16)
        self.run_import()
        self.assertEqual([c["interval"] for c in self.wt3_calls()], [LIST_INTERVAL] + WINDOWS)
        self.assert_finished()

    def test_list_without_end_marker_is_retried_from_scratch(self):
        (self.fake / "no-end-once").touch()
        st = self.run_import()
        self.assertEqual(st["attempts"], {"images": 1})
        self.assertIn("--END--", st["error"])
        self.now += timedelta(minutes=16)
        self.run_import()
        calls = self.wt3_calls()
        self.assertEqual(
            [(c["interval"], c["resume"]) for c in calls],
            [(LIST_INTERVAL, False), (LIST_INTERVAL, False)] + [(w, True) for w in WINDOWS],
        )
        self.assert_finished()

    def test_no_files_skips_wikiteam3(self):
        st = self.worker.load_state(42)
        st["summary"]["fandom_files"] = 0
        self.worker.save_state(st)
        self.run_import()
        self.assertEqual(self.wt3_calls(), [])
        self.assertFalse(self.worker.work_dir(42).exists())
        data = self.done_data()
        self.assertEqual((data["images_total"], data["batches_total"], data["images_added"]), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
