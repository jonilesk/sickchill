"""
Tests for the TVmaze upcoming-premieres cache.

The interesting behaviour is all in the filter and in what happens when TVmaze is unreachable, so
the HTTP call is patched out and the real cache.db is driven underneath.
"""

import datetime
import unittest
from unittest.mock import patch

from sickchill.oldbeard import db
from sickchill.show.recommendations import tvmaze
from tests import conftest


def _episode(
    episode_id=1,
    show_id=100,
    name="Show Name",
    season=1,
    number=1,
    days=10,
    thetvdb=12345,
    **show_overrides,
):
    """Build one /schedule/full entry, defaulting to a usable series premiere."""
    when = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)

    show = {
        "id": show_id,
        "name": name,
        "url": f"https://www.tvmaze.com/shows/{show_id}/slug",
        "language": "English",
        "genres": ["Drama", "Thriller"],
        "status": "To Be Determined",
        "averageRuntime": 60,
        "weight": 90,
        "rating": {"average": 7.5},
        "network": {"name": "HBO", "country": {"code": "US"}},
        "webChannel": None,
        "externals": {"thetvdb": thetvdb, "imdb": "tt1234567"},
        "image": {"medium": "https://static.tvmaze.com/x.jpg", "original": "https://static.tvmaze.com/y.jpg"},
        "summary": "<p>A <b>very</b> good show.</p>",
    }
    show.update(show_overrides)

    return {
        "id": episode_id,
        "season": season,
        "number": number,
        "airstamp": when.isoformat(),
        "airdate": when.date().isoformat(),
        "_embedded": {"show": show},
    }


class TVmazePremiereTests(conftest.SickChillTestDBCase):
    def setUp(self):
        super().setUp()
        self.cache_db_con = db.DBConnection("cache.db")
        self.cache_db_con.action("DELETE FROM tvmaze_premieres")
        self.cache_db_con.action("DELETE FROM tvmaze_refresh")

    def _rows(self):
        return self.cache_db_con.select("SELECT * FROM tvmaze_premieres ORDER BY airstamp ASC")

    @staticmethod
    def _refresh(payload, force=False):
        with patch.object(tvmaze.helpers, "getURL", return_value=payload) as fetch:
            stored = tvmaze.refresh_premieres(force=force)
        return stored, fetch

    def test_series_premiere_is_stored(self):
        stored, _fetch = self._refresh([_episode()])

        self.assertEqual(1, stored)
        rows = self._rows()
        self.assertEqual(1, len(rows))
        self.assertEqual(tvmaze.SERIES, rows[0]["kind"])
        self.assertEqual(12345, rows[0]["tvdb_id"])
        self.assertEqual("HBO", rows[0]["network"])
        self.assertEqual("network", rows[0]["channel_kind"])
        self.assertEqual("Drama, Thriller", rows[0]["genres"])

    def test_show_without_a_tvdb_id_is_dropped(self):
        """
        tv_shows is keyed on a TVDB indexer_id, so a show without one could never be added.
        """
        stored, _fetch = self._refresh([_episode(thetvdb=None), _episode(episode_id=2, show_id=200, thetvdb=999)])

        self.assertEqual(1, stored)
        self.assertEqual([999], [row["tvdb_id"] for row in self._rows()])

    def test_non_premiere_episodes_are_dropped(self):
        stored, _fetch = self._refresh([_episode(number=4)])

        self.assertEqual(0, stored)
        self.assertEqual([], self._rows())

    def test_later_seasons_are_classified_as_season_premieres(self):
        stored, _fetch = self._refresh([_episode(season=3)])

        self.assertEqual(1, stored)
        self.assertEqual(tvmaze.SEASON, self._rows()[0]["kind"])

    def test_episodes_beyond_the_horizon_are_dropped(self):
        stored, _fetch = self._refresh([_episode(days=tvmaze.HORIZON_DAYS + 30)])

        self.assertEqual(0, stored)

    def test_episodes_in_the_past_are_dropped(self):
        stored, _fetch = self._refresh([_episode(days=-5)])

        self.assertEqual(0, stored)

    def test_web_channel_shows_are_kept_and_labelled(self):
        stored, _fetch = self._refresh([_episode(network=None, webChannel={"name": "Netflix", "country": None})])

        self.assertEqual(1, stored)
        row = self._rows()[0]
        self.assertEqual("Netflix", row["network"])
        self.assertEqual("web", row["channel_kind"])
        self.assertIsNone(row["country"])

    def test_summary_html_is_stripped(self):
        self._refresh([_episode()])

        self.assertEqual("A very good show.", self._rows()[0]["summary"])

    def test_a_show_can_hold_two_season_premieres(self):
        """
        Keyed on the episode id, not the show id: a returning show can premiere twice in a year.
        """
        stored, _fetch = self._refresh(
            [
                _episode(episode_id=1, show_id=100, season=2, days=10),
                _episode(episode_id=2, show_id=100, season=3, days=300),
            ]
        )

        self.assertEqual(2, stored)
        self.assertEqual(2, len(self._rows()))

    def test_throttle_skips_the_second_refresh(self):
        self._refresh([_episode()])

        stored, fetch = self._refresh([_episode(episode_id=2, show_id=200)])

        fetch.assert_not_called()
        self.assertEqual(0, stored)
        self.assertEqual(1, len(self._rows()))

    def test_force_bypasses_the_throttle(self):
        self._refresh([_episode()])

        stored, fetch = self._refresh([_episode(episode_id=2, show_id=200)], force=True)

        fetch.assert_called()
        self.assertEqual(1, stored)
        self.assertEqual([2], [row["episode_id"] for row in self._rows()])

    def test_a_failed_fetch_keeps_the_previously_cached_rows(self):
        """
        getURL returns "" for every failure mode. A stale page beats an empty one, so the existing
        rows must survive rather than being replaced by nothing.
        """
        self._refresh([_episode()])

        with patch.object(tvmaze.helpers, "getURL", return_value=""), patch.object(tvmaze.time, "sleep"):
            stored = tvmaze.refresh_premieres(force=True)

        self.assertEqual(0, stored)
        self.assertEqual(1, len(self._rows()))

    def test_a_response_with_no_usable_premieres_keeps_the_cached_rows(self):
        self._refresh([_episode()])

        stored, _fetch = self._refresh([_episode(episode_id=2, thetvdb=None)], force=True)

        self.assertEqual(0, stored)
        self.assertEqual(1, len(self._rows()))

    def test_failed_fetch_retries_once(self):
        with patch.object(tvmaze.helpers, "getURL", return_value="") as fetch, patch.object(tvmaze.time, "sleep") as sleep:
            tvmaze.refresh_premieres(force=True)

        self.assertEqual(2, fetch.call_count)
        sleep.assert_called_once_with(tvmaze.RETRY_DELAY_SECONDS)

    def test_get_premieres_returns_soonest_first_and_filters_by_kind(self):
        self._refresh(
            [
                _episode(episode_id=1, show_id=100, days=30),
                _episode(episode_id=2, show_id=200, days=5),
                _episode(episode_id=3, show_id=300, season=2, days=1),
            ]
        )

        series = tvmaze.get_premieres(tvmaze.SERIES)
        self.assertEqual([2, 1], [row["episode_id"] for row in series])

        season = tvmaze.get_premieres(tvmaze.SEASON)
        self.assertEqual([3], [row["episode_id"] for row in season])

    def test_get_premieres_falls_back_for_an_unknown_kind(self):
        self._refresh([_episode()])

        self.assertEqual(1, len(tvmaze.get_premieres("nonsense")))

    def test_strip_html_handles_empty_and_entities(self):
        self.assertEqual("", tvmaze.strip_html(None))
        self.assertEqual("", tvmaze.strip_html(""))
        self.assertEqual("Tom & Jerry", tvmaze.strip_html("<p>Tom &amp; Jerry</p>"))


if __name__ == "__main__":
    unittest.main()
