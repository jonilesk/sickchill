"""
Inspect the payload of a search result before it is handed to a download client.

SickChill otherwise only ever filters on the release *name*. A release advertised as an episode
can still contain nothing but an executable, which is a common way to distribute malware, so
these helpers enumerate the filenames inside a .torrent or .nzb and let callers reject the
result before anything is downloaded.
"""

import re
from xml.etree import ElementTree

import bencode

from sickchill import logger
from sickchill.helper.common import find_executable_files

# NZB subjects conventionally look like: [1/9] - "Show.S01E01.mkv" yEnc (1/42)
NZB_SUBJECT_FILENAME = re.compile(r'"([^"]+)"')


def _to_text(value) -> str:
    """
    Coerce a bencode/ElementTree value to text.

    bencode.py does not guarantee whether names come back as ``str`` or ``bytes``, and torrents
    are allowed to carry names that are not valid UTF-8.
    """
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def torrent_payload_names(content) -> list:
    """
    List the filenames contained in a bencoded torrent.

    :param content: Raw .torrent bytes
    :return: The paths inside the torrent, or an empty list if it cannot be decoded
    """
    if not content:
        return []

    try:
        decoded = bencode.decode(content)
        info = decoded["info"]
    except Exception as error:
        # A torrent we cannot decode is rejected later on anyway, by the hash lookup in
        # GenericClient._get_torrent_hash or by TorrentProvider._verify_download.
        logger.debug(f"Unable to read the file list from torrent data: {error}")
        return []

    names = []
    files = info.get("files")
    if files:
        for entry in files:
            path = entry.get("path") or []
            if path:
                names.append("/".join(_to_text(part) for part in path))
    elif info.get("name"):
        names.append(_to_text(info["name"]))

    return names


def nzb_payload_names(data) -> list:
    """
    List the filenames referenced by an NZB.

    :param data: Raw NZB XML, as text or bytes
    :return: The filenames named in each <file> subject, or an empty list if it cannot be parsed
    """
    if not data:
        return []

    try:
        root = ElementTree.XML(data)
    except (ElementTree.ParseError, SyntaxError, ValueError) as error:
        logger.debug(f"Unable to parse NZB data to read its file list: {error}")
        return []

    names = []
    for element in root.iter():
        # Match the namespaced <file> tag the same way nzbSplitter.get_season_nzbs does.
        if not element.tag.endswith("file"):
            continue

        subject = element.get("subject")
        if not subject:
            continue

        match = NZB_SUBJECT_FILENAME.search(subject)
        # Fall back to the whole subject so an unquoted filename is still checked.
        names.append(match.group(1) if match else subject)

    return names


def blocked_payload_files(result) -> list:
    """
    Find executables inside a search result's payload.

    Only inspects payloads SickChill actually holds. A magnet link handed straight to a torrent
    client has no payload to read, so it returns an empty list and the caller falls back to the
    release name check plus the post-processing gates.

    :param result: SearchResult instance to inspect
    :return: The blocked filenames found in the payload
    """
    if result is None:
        return []

    if result.is_torrent:
        return find_executable_files(torrent_payload_names(result.content))

    if result.is_nzbdata:
        return find_executable_files(nzb_payload_names(result.extraInfo and result.extraInfo[0]))

    return []
