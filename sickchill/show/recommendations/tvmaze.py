"""
Upcoming show premieres, sourced from TVmaze.

TVmaze needs no API key, no registration and no OAuth, which is the reason this exists: the Trakt
lists it replaces stopped working when Trakt began requiring every application to supply its own
key, and SickChill's was hardcoded with no way to change it.

The data is CC BY-SA 4.0, so attribution is a licence condition rather than a courtesy. Every row
carries the show's public TVmaze url and the templates link to it.

One request to /schedule/full gets every future episode TVmaze knows about, worldwide. That is
around 12 MB, so it is fetched at most once a day and the filtered premieres are kept in cache.db;
every page view after the first is a local query.
"""

import datetime
import html
import re
import time
from typing import List

import requests

from sickchill import logger, settings
from sickchill.helper.common import USER_AGENT
from sickchill.oldbeard import db, helpers
from sickchill.oldbeard.network_timezones import sc_now

TVMAZE_SCHEDULE_FULL = "https://api.tvmaze.com/schedule/full"

# Everything further out than this is too speculative to be worth a row, and it bounds the table.
HORIZON_DAYS = 365

# TVmaze allows at least 20 calls per 10 seconds per IP and answers 429 above that.
RETRY_DELAY_SECONDS = 5

# TVmaze summaries are HTML fragments (<p>, <b>, <i>). Strip them once here rather than in every
# consumer, so what lands in the database is plain text.
HTML_TAG = re.compile(r"<[^>]+>")

SERIES = "series"
SEASON = "season"

KINDS = (SERIES, SEASON)

_COLUMNS = (
    "episode_id",
    "tvmaze_id",
    "tvdb_id",
    "imdb_id",
    "name",
    "kind",
    "season",
    "airstamp",
    "airdate",
    "network",
    "channel_kind",
    "country",
    "language",
    "genres",
    "runtime",
    "rating",
    "weight",
    "image_url",
    "summary",
    "tvmaze_url",
    "status",
)


def strip_html(text: str) -> str:
    """
    :param text: an HTML fragment, or None
    :return: the same text with tags removed and entities decoded
    """
    if not text:
        return ""

    return " ".join(html.unescape(HTML_TAG.sub(" ", text)).split())


def get_session() -> requests.Session:
    """
    A plain session, deliberately not helpers.make_session().

    make_session wraps the session in CacheControl backed by an in-memory dict, which would pin the
    ~12 MB schedule body in RAM for the life of the process. The daily throttle below already does
    the caching job.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Encoding": "gzip,deflate"})
    session.verify = settings.SSL_VERIFY
    return session


def should_refresh(list_name: str) -> bool:
    """
    :param list_name: the cached list to check
    :return: True if the cached copy is older than a day, or was never fetched
    """
    seconds_per_day = 24 * 60 * 60

    cache_db_con = db.DBConnection("cache.db")
    rows = cache_db_con.select("SELECT last_refreshed FROM tvmaze_refresh WHERE list = ?", [list_name])
    if rows:
        last_refresh = int(rows[0]["last_refreshed"])
        return int(time.mktime(sc_now().timetuple())) > last_refresh + seconds_per_day

    return True


def set_last_refresh(list_name: str) -> None:
    """
    :param list_name: the cached list to stamp as refreshed now
    """
    cache_db_con = db.DBConnection("cache.db")
    cache_db_con.upsert("tvmaze_refresh", {"last_refreshed": int(time.mktime(sc_now().timetuple()))}, {"list": list_name})


def _fetch_schedule(session: requests.Session = None) -> list:
    """
    Fetch the full future schedule, retrying once on failure.

    getURL swallows the exception and returns "" for every failure mode, so a 429 is not
    distinguishable from a timeout here. One blind retry after a short pause covers both, which is
    what TVmaze asks for on 429 anyway.
    """
    session = session or get_session()

    for attempt in (1, 2):
        data = helpers.getURL(TVMAZE_SCHEDULE_FULL, session=session, returns="json", timeout=120)
        if isinstance(data, list) and data:
            return data

        if attempt == 1:
            logger.debug(f"No usable response from {TVMAZE_SCHEDULE_FULL}, retrying in {RETRY_DELAY_SECONDS}s")
            time.sleep(RETRY_DELAY_SECONDS)

    return []


def _parse_episode(episode: dict, horizon: datetime.datetime, now: datetime.datetime) -> dict:
    """
    Turn one /schedule/full entry into a row, or return None if it is not a premiere we can use.

    :param episode: a single episode object with its show embedded
    :param horizon: latest airstamp we are willing to store
    :param now: current time, timezone aware
    """
    if not isinstance(episode, dict) or episode.get("number") != 1:
        return None

    show = (episode.get("_embedded") or {}).get("show") or {}
    externals = show.get("externals") or {}

    # No TheTVDB id means the show cannot be added: tv_shows is keyed on a TVDB indexer_id.
    tvdb_id = externals.get("thetvdb")
    if not tvdb_id:
        return None

    episode_id, tvmaze_id = episode.get("id"), show.get("id")
    name, tvmaze_url = show.get("name"), show.get("url")
    if not all((episode_id, tvmaze_id, name, tvmaze_url)):
        return None

    # airstamp is the only timezone-correct field; airdate and airtime are local to the network.
    airstamp = episode.get("airstamp")
    if not airstamp:
        return None

    try:
        when = datetime.datetime.fromisoformat(airstamp)
    except (TypeError, ValueError):
        return None

    if when.tzinfo is None:
        when = when.replace(tzinfo=datetime.timezone.utc)

    if not now <= when <= horizon:
        return None

    # network and webChannel are mutually exclusive: traditional broadcaster versus streaming.
    channel = show.get("network") or {}
    channel_kind = "network"
    if not channel:
        channel = show.get("webChannel") or {}
        channel_kind = "web"

    rating = (show.get("rating") or {}).get("average")
    image = show.get("image") or {}

    return {
        "episode_id": int(episode_id),
        "tvmaze_id": int(tvmaze_id),
        "tvdb_id": int(tvdb_id),
        "imdb_id": externals.get("imdb"),
        "name": name,
        "kind": SERIES if episode.get("season") == 1 else SEASON,
        "season": episode.get("season"),
        "airstamp": airstamp,
        "airdate": episode.get("airdate"),
        "network": channel.get("name"),
        "channel_kind": channel_kind,
        "country": ((channel.get("country") or {}).get("code")),
        "language": show.get("language"),
        "genres": ", ".join(show.get("genres") or []),
        "runtime": show.get("averageRuntime") or show.get("runtime"),
        "rating": rating,
        "weight": show.get("weight"),
        "image_url": image.get("medium") or image.get("original"),
        "summary": strip_html(show.get("summary")),
        "tvmaze_url": tvmaze_url,
        "status": show.get("status"),
    }


def refresh_premieres(force: bool = False, session: requests.Session = None) -> int:
    """
    Refresh the cached premieres if the copy on hand is stale.

    :param force: refresh even if the throttle says the cache is still fresh
    :return: number of rows stored, or 0 if nothing was done
    """
    if not force and not should_refresh("premieres"):
        return 0

    logger.info("Checking TVmaze for upcoming show premieres")

    schedule = _fetch_schedule(session)
    if not schedule:
        # Leave whatever is already cached alone: a stale page beats an empty one.
        logger.info("TVmaze returned no schedule data, keeping the previously cached premieres")
        return 0

    now = sc_now()
    horizon = now + datetime.timedelta(days=HORIZON_DAYS)

    rows = []
    for episode in schedule:
        row = _parse_episode(episode, horizon, now)
        if row:
            rows.append(row)

    if not rows:
        logger.info("TVmaze schedule held no usable premieres, keeping the previously cached ones")
        return 0

    placeholders = ", ".join("?" for _ in _COLUMNS)
    insert = f"INSERT OR REPLACE INTO tvmaze_premieres ({', '.join(_COLUMNS)}) VALUES ({placeholders});"

    # One transaction, so a failure part way through cannot leave the table half emptied.
    queries = [["DELETE FROM tvmaze_premieres;"]]
    queries.extend([insert, [row[column] for column in _COLUMNS]] for row in rows)

    cache_db_con = db.DBConnection("cache.db")
    cache_db_con.mass_action(queries)

    set_last_refresh("premieres")

    logger.info(f"Cached {len(rows)} upcoming premieres from TVmaze")
    return len(rows)


def get_premieres(kind: str = SERIES) -> List[dict]:
    """
    :param kind: "series" for brand new shows, "season" for returning ones
    :return: cached premieres, soonest first
    """
    if kind not in KINDS:
        kind = SERIES

    cache_db_con = db.DBConnection("cache.db")
    return cache_db_con.select("SELECT * FROM tvmaze_premieres WHERE kind = ? ORDER BY airstamp ASC", [kind])
