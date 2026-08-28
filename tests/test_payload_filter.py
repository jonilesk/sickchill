"""
Test sickchill.oldbeard.payload_filter
"""

import unittest

import bencode

from sickchill import settings
from sickchill.oldbeard.payload_filter import blocked_payload_files, nzb_payload_names, torrent_payload_names
from sickchill.providers.result_classes import NZBDataSearchResult, TorrentSearchResult

NZB_TEMPLATE = """<?xml version="1.0" encoding="iso-8859-1" ?>
<nzb xmlns="http://www.newzbin.com/DTD/2003/nzb">
  <file poster="poster@example.com" date="1234567890" subject="[1/2] - &quot;{first}&quot; yEnc (1/42)">
    <groups><group>alt.binaries.test</group></groups>
    <segments><segment bytes="1" number="1">segment@example.com</segment></segments>
  </file>
  <file poster="poster@example.com" date="1234567890" subject="[2/2] - &quot;{second}&quot; yEnc (1/42)">
    <groups><group>alt.binaries.test</group></groups>
    <segments><segment bytes="1" number="1">segment@example.com</segment></segments>
  </file>
</nzb>
"""


def single_file_torrent(name):
    return bencode.encode({"announce": "http://tracker.example.com/announce", "info": {"name": name, "length": 100, "piece length": 16384, "pieces": ""}})


def multi_file_torrent(paths):
    return bencode.encode(
        {
            "announce": "http://tracker.example.com/announce",
            "info": {
                "name": "Show.Name.S01E01.1080p",
                "piece length": 16384,
                "pieces": "",
                "files": [{"length": 100, "path": path} for path in paths],
            },
        }
    )


class PayloadFilterTests(unittest.TestCase):
    """
    Test reading the file list out of a torrent or NZB, and rejecting executables in it.
    """

    def setUp(self):
        settings.BLOCK_EXECUTABLE_FILES = True
        settings.EXECUTABLE_EXTENSIONS = "exe,scr,msi,lnk,ps1"

    def test_torrent_payload_names_single_file(self):
        assert torrent_payload_names(single_file_torrent("Show.Name.S01E01.mkv")) == ["Show.Name.S01E01.mkv"]

    def test_torrent_payload_names_multi_file(self):
        content = multi_file_torrent([["Show.Name.S01E01.mkv"], ["Subs", "Show.Name.S01E01.srt"]])
        assert torrent_payload_names(content) == ["Show.Name.S01E01.mkv", "Subs/Show.Name.S01E01.srt"]

    def test_torrent_payload_names_handles_bytes(self):
        """bencode.py does not guarantee str, and torrent names need not be valid UTF-8."""
        content = multi_file_torrent([[b"Show.Name.S01E01.mkv"], [b"Subs", b"Show.Name.S01E01.srt"]])
        assert torrent_payload_names(content) == ["Show.Name.S01E01.mkv", "Subs/Show.Name.S01E01.srt"]

    def test_torrent_payload_names_bad_data(self):
        """Undecodable data must not raise; it is rejected further down the snatch path."""
        assert torrent_payload_names(b"this is not a torrent") == []
        assert torrent_payload_names(b"") == []
        assert torrent_payload_names(None) == []
        assert torrent_payload_names(bencode.encode({"no": "info dict"})) == []

    def test_nzb_payload_names(self):
        data = NZB_TEMPLATE.format(first="Show.Name.S01E01.mkv", second="Show.Name.S01E01.nfo")
        assert nzb_payload_names(data) == ["Show.Name.S01E01.mkv", "Show.Name.S01E01.nfo"]

    def test_nzb_payload_names_accepts_bytes(self):
        data = NZB_TEMPLATE.format(first="Show.Name.S01E01.mkv", second="Show.Name.S01E01.nfo")
        assert nzb_payload_names(data.encode("utf-8")) == ["Show.Name.S01E01.mkv", "Show.Name.S01E01.nfo"]

    def test_nzb_payload_names_bad_data(self):
        assert nzb_payload_names("<nzb><unclosed>") == []
        assert nzb_payload_names("") == []
        assert nzb_payload_names(None) == []

    def test_clean_torrent_is_allowed(self):
        result = TorrentSearchResult([], provider=None, url="http://example.com/x.torrent")
        result.name = "Show.Name.S01E01.1080p"
        result.content = multi_file_torrent([["Show.Name.S01E01.mkv"], ["Subs", "Show.Name.S01E01.srt"]])
        assert blocked_payload_files(result) == []

    def test_torrent_containing_executable_is_blocked(self):
        result = TorrentSearchResult([], provider=None, url="http://example.com/x.torrent")
        result.name = "Show.Name.S01E01.1080p"
        result.content = multi_file_torrent([["Show.Name.S01E01.mkv"], ["Sample", "setup.exe"]])
        assert blocked_payload_files(result) == ["Sample/setup.exe"]

    def test_torrent_disguised_as_media_is_blocked(self):
        result = TorrentSearchResult([], provider=None, url="http://example.com/x.torrent")
        result.name = "Show.Name.S01E01.1080p"
        result.content = single_file_torrent("Show.Name.S01E01.1080p.mkv.exe")
        assert blocked_payload_files(result) == ["Show.Name.S01E01.1080p.mkv.exe"]

    def test_nzbdata_containing_executable_is_blocked(self):
        result = NZBDataSearchResult([], provider=None, url="http://example.com/x.nzb")
        result.name = "Show.Name.S01E01.1080p"
        result.extraInfo = [NZB_TEMPLATE.format(first="Show.Name.S01E01.mkv", second="Show.Name.S01E01.mkv.exe")]
        assert blocked_payload_files(result) == ["Show.Name.S01E01.mkv.exe"]

    def test_clean_nzbdata_is_allowed(self):
        result = NZBDataSearchResult([], provider=None, url="http://example.com/x.nzb")
        result.name = "Show.Name.S01E01.1080p"
        result.extraInfo = [NZB_TEMPLATE.format(first="Show.Name.S01E01.mkv", second="Show.Name.S01E01.nfo")]
        assert blocked_payload_files(result) == []

    def test_setting_disabled_allows_everything(self):
        settings.BLOCK_EXECUTABLE_FILES = False
        result = TorrentSearchResult([], provider=None, url="http://example.com/x.torrent")
        result.name = "Show.Name.S01E01.1080p"
        result.content = multi_file_torrent([["Sample", "setup.exe"]])
        assert blocked_payload_files(result) == []

    def test_magnet_has_no_payload_to_inspect(self):
        """A magnet cannot be inspected; the name check and post processing cover it instead."""
        result = TorrentSearchResult([], provider=None, url="magnet:?xt=urn:btih:" + "a" * 40)
        result.name = "Show.Name.S01E01.1080p"
        assert blocked_payload_files(result) == []


if __name__ == "__main__":
    unittest.main()
