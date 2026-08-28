from __future__ import annotations

from urllib.parse import quote

from sickchill import logger
from sickchill.oldbeard import helpers

TVMAZE_SEARCH = "https://api.tvmaze.com/search/shows?q="


def search(name: str) -> list[dict]:
    """
    Search TVmaze for shows by name.

    Returns a list of show dicts that contain a valid 'externals.thetvdb' ID.
    Empty list on failure or no usable results.
    """
    if not name or not str(name).strip():
        return []

    try:
        url = TVMAZE_SEARCH + quote(str(name).strip())
        # Through helpers rather than requests.get directly, so this honours SSL_VERIFY, the
        # configured proxy and the shared User-Agent like every other outbound call.
        data = helpers.getURL(url, session=helpers.make_indexer_session(), returns="json", timeout=10)
    except Exception as e:
        logger.debug(f"TVmaze search failed for '{name}': {e}")
        return []

    results = []
    if not isinstance(data, list):
        return results

    for item in data:
        if not isinstance(item, dict):
            continue
        show = item.get("show") or {}
        externals = show.get("externals") or {}
        if externals.get("thetvdb"):
            results.append(show)
    return results
