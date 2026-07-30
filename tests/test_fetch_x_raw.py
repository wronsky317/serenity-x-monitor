from __future__ import annotations

import argparse
import importlib.util
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_x_raw.py"
SPEC = importlib.util.spec_from_file_location("fetch_x_raw", MODULE_PATH)
assert SPEC and SPEC.loader
fetcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetcher)


def row(timestamp: str, row_id: str = "row-1") -> dict:
    return {
        "id": row_id,
        "sortAt": timestamp,
        "caller": {"handle": "aleabitoreddit"},
        "post": {"postedAt": timestamp, "xPostId": row_id},
    }


class FetchXRawTest(unittest.TestCase):
    def test_extracts_authored_candidates_from_x_profile_html(self) -> None:
        profile = """
<article>
  <meta itemProp="alternateName" content="aleabitoreddit"/>
  <meta itemProp="datePublished" content="2026-07-24T20:22:41.000Z"/>
  <a href="/aleabitoreddit/status/2080750537121874206">Jul 24</a>
</article>
<article>
  <meta itemProp="alternateName" content="someone_else"/>
  <meta itemProp="datePublished" content="2026-07-24T21:00:00.000Z"/>
  <a href="/someone_else/status/2080750537121874999">Jul 24</a>
</article>
"""
        self.assertEqual(
            fetcher.extract_x_profile_candidates(profile, "aleabitoreddit"),
            [("2080750537121874206", "2026-07-24T20:22:41.000Z")],
        )

    def test_extracts_complete_jina_status_body(self) -> None:
        status = """
Published Time: 2026-07-24T00:11:40.000Z

## Post

* [@aleabitoreddit](https://x.com/aleabitoreddit) Not exactly for
[$AAOI](https://x.com/search?q=$AAOI). Pluggables will stay.
[![Image](https://pbs.twimg.com/media/example)](https://x.com/aleabitoreddit/status/2080445777395298454/photo/1)
[@quoted_user](https://x.com/quoted_user) This quoted reply is not Serenity text.
[12:11 AM · Jul 24, 2026](https://x.com/aleabitoreddit/status/2080445777395298454)
"""
        timestamp, text = fetcher.extract_jina_post(
            status,
            "aleabitoreddit",
            "2080445777395298454",
        )
        self.assertEqual(timestamp, "2026-07-24T00:11:40.000Z")
        self.assertEqual(text, "Not exactly for $AAOI. Pluggables will stay.")

    def test_x_public_recovery_rejects_partial_status_results(self) -> None:
        profile = """
<article>
  <meta itemProp="alternateName" content="aleabitoreddit"/>
  <meta itemProp="datePublished" content="2026-07-24T20:22:41.000Z"/>
  <a href="/aleabitoreddit/status/2080750537121874206">Jul 24</a>
</article>
<article>
  <meta itemProp="alternateName" content="aleabitoreddit"/>
  <meta itemProp="datePublished" content="2026-07-24T16:21:59.000Z"/>
  <a href="/aleabitoreddit/status/2080689966045348047">Jul 24</a>
</article>
"""
        good = {
            "tweet": {
                "text": "Complete text",
                "created_at": "Fri Jul 24 20:22:41 +0000 2026",
                "author": {
                    "screen_name": "aleabitoreddit",
                    "id": "1940360837547565056",
                    "name": "Serenity",
                },
            }
        }

        def fake_fetch_json(url: str, timeout: int) -> tuple[dict, bytes]:
            if "2080750537121874206" in url:
                return good, b'{"tweet":{}}'
            raise urllib.error.HTTPError(url, 503, "Unavailable", {}, None)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            fetcher,
            "fetch_text",
            return_value=profile,
        ), mock.patch.object(
            fetcher,
            "fetch_json",
            side_effect=fake_fetch_json,
        ):
            with self.assertRaisesRegex(ValueError, r"incomplete \(1/2 rows\)"):
                fetcher.fetch_x_public_rows(
                    handle="aleabitoreddit",
                    timeout=30,
                    run_dir=Path(tmp),
                )

    def test_rejects_recovery_snapshot_that_stops_inside_window(self) -> None:
        rows = [
            row("2026-07-30T08:10:00Z", "latest"),
            row("2026-07-29T20:03:30Z", "fifth"),
        ]

        with self.assertRaisesRegex(
            fetcher.IncompleteRecoveryError,
            "refusing to publish a partial report",
        ):
            fetcher.validate_recovery_coverage(
                rows,
                since=fetcher.parse_iso_utc("2026-07-29T07:15:55Z"),
                endpoint="https://x.com/aleabitoreddit",
            )

    def test_accepts_recovery_snapshot_that_reaches_before_window(self) -> None:
        fetcher.validate_recovery_coverage(
            [row("2026-07-24T20:22:41Z", "old")],
            since=fetcher.parse_iso_utc("2026-07-25T07:00:00Z"),
            endpoint="https://x.com/aleabitoreddit",
        )

    def test_rejects_feed_older_than_lag_limit(self) -> None:
        with self.assertRaisesRegex(fetcher.StaleFeedError, r"25\.0h behind"):
            fetcher.validate_feed_freshness(
                [row("2026-07-23T12:00:00Z")],
                until=fetcher.parse_iso_utc("2026-07-24T13:00:00Z"),
                max_lag_hours=12,
                endpoint="https://primary.example/api/feed",
            )

    def test_accepts_current_feed_even_when_target_count_can_be_zero(self) -> None:
        fetcher.validate_feed_freshness(
            [row("2026-07-24T12:55:00Z", row_id="other-account")],
            until=fetcher.parse_iso_utc("2026-07-24T13:00:00Z"),
            max_lag_hours=12,
            endpoint="https://primary.example/api/feed",
        )

    def test_skips_freshness_check_without_until(self) -> None:
        fetcher.validate_feed_freshness(
            [],
            until=None,
            max_lag_hours=12,
            endpoint="https://primary.example/api/feed",
        )

    def test_stale_primary_falls_back_to_fresh_secondary(self) -> None:
        stale_page = {
            "rows": [row("2026-07-23T12:00:00Z", "stale")],
            "nextCursor": None,
        }
        fresh_page = {
            "rows": [row("2026-07-24T12:55:00Z", "fresh")],
            "nextCursor": None,
        }

        def fake_fetch(url: str, timeout: int) -> tuple[dict, bytes]:
            page = stale_page if "primary.example" in url else fresh_page
            return page, b'{"rows":[]}'

        args = argparse.Namespace(
            since="2026-07-24T00:00:00Z",
            until="2026-07-24T13:00:00Z",
            cursor=None,
            endpoint=[
                "https://primary.example/api/feed",
                "https://secondary.example/api/feed",
            ],
            take=50,
            timeout=30,
            max_pages=5,
            sleep=0,
            max_feed_lag_hours=12,
            handle="aleabitoreddit",
            run_started_at="2026-07-24T13:00:00+00:00",
        )

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            fetcher, "fetch_json", side_effect=fake_fetch
        ):
            manifest = fetcher.fetch_pages(args, Path(tmp))

        self.assertEqual(
            manifest["selectedEndpoint"],
            "https://secondary.example/api/feed",
        )
        self.assertEqual(manifest["matchedHandleRowCount"], 1)
        self.assertEqual(len(manifest["endpointErrors"]), 1)
        self.assertIn("StaleFeedError", manifest["endpointErrors"][0]["error"])

    def test_stale_supercycle_falls_back_to_jina_rows(self) -> None:
        args = argparse.Namespace(
            since="2026-07-23T07:00:00Z",
            until="2026-07-24T13:00:00Z",
            cursor=None,
            endpoint=["https://primary.example/api/feed"],
            take=50,
            timeout=30,
            max_pages=5,
            sleep=0,
            max_feed_lag_hours=12,
            handle="aleabitoreddit",
            run_started_at="2026-07-24T13:00:00+00:00",
        )
        recovered = [
            row("2026-07-24T00:11:40Z", "2080445777395298454"),
            row("2026-07-23T06:59:59Z", "coverage-anchor"),
        ]

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            fetcher,
            "fetch_json",
            return_value=(
                {"rows": [row("2026-07-23T12:00:00Z", "stale")]},
                b'{"rows":[]}',
            ),
        ), mock.patch.object(
            fetcher,
            "fetch_x_public_rows",
            side_effect=urllib.error.HTTPError(
                "https://x.com/aleabitoreddit", 403, "Forbidden", {}, None
            ),
        ), mock.patch.object(
            fetcher,
            "fetch_jina_rows",
            return_value=(recovered, "https://reader.example/aleabitoreddit"),
        ):
            manifest = fetcher.fetch_pages(args, Path(tmp))

        self.assertEqual(
            manifest["selectedEndpoint"],
            "https://reader.example/aleabitoreddit",
        )
        self.assertEqual(manifest["matchedHandleRowCount"], 1)
        self.assertEqual(manifest["pages"][0]["recoverySource"], "X public page via Jina Reader")

    def test_x_public_profile_can_confirm_zero_rows_in_window(self) -> None:
        args = argparse.Namespace(
            since="2026-07-25T07:00:00Z",
            until="2026-07-26T13:00:00Z",
            cursor=None,
            endpoint=["https://primary.example/api/feed"],
            take=50,
            timeout=30,
            max_pages=5,
            sleep=0,
            max_feed_lag_hours=12,
            handle="aleabitoreddit",
            run_started_at="2026-07-26T13:00:00+00:00",
        )
        recovered = [row("2026-07-24T20:22:41Z", "2080750537121874206")]

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            fetcher,
            "fetch_json",
            return_value=(
                {"rows": [row("2026-07-23T12:00:00Z", "stale")]},
                b'{"rows":[]}',
            ),
        ), mock.patch.object(
            fetcher,
            "fetch_x_public_rows",
            return_value=(recovered, "https://x.com/aleabitoreddit"),
        ):
            manifest = fetcher.fetch_pages(args, Path(tmp))

        self.assertEqual(manifest["selectedEndpoint"], "https://x.com/aleabitoreddit")
        self.assertEqual(manifest["matchedHandleRowCount"], 0)
        self.assertEqual(
            manifest["pages"][0]["recoverySource"],
            "X public profile + FxTwitter status API",
        )


if __name__ == "__main__":
    unittest.main()
