"""
Test snatching
"""

import unittest
from unittest.mock import patch

import bencode

import sickchill.oldbeard.helpers
from sickchill import settings
from sickchill.oldbeard import common as common, search as search
from sickchill.providers.result_classes import TorrentSearchResult
from sickchill.tv import TVEpisode, TVShow
from tests import conftest

# from unittest.mock import patch, PropertyMock


TESTS_DATA = {
    "Dexter": {
        "id": 1,
        "active": 1,
        "quality": common.HD,
        "season": 5,
        "episodes": [7],
        "best_result": "Dexter.S05E07.720p.BluRay.X264-REWARD",
        "results": ["Dexter.S05E07.720p.BluRay.X264-REWARD", "Dexter.S05E07.720p.X264-REWARD"],
    },
    "House": {
        "id": 2,
        "active": 1,
        "quality": common.HD,
        "season": 4,
        "episodes": [5],
        "best_result": "House.4x5.720p.BluRay.X264-REWARD",
        "results": ["Dexter.S05E04.720p.X264-REWARD", "House.4x5.720p.BluRay.X264-REWARD"],
    },
    "Hells Kitchen": {
        "id": 3,
        "active": 1,
        "quality": common.SD,
        "season": 6,
        "episodes": [14, 15],
        "best_result": "Hells.Kitchen.s6e14e15.HDTV.XviD-ASAP",
        "results": ["Hells.Kitchen.S06E14.HDTV.XviD-ASAP", "Hells.Kitchen.6x14.HDTV.XviD-ASAP", "Hells.Kitchen.s6e14e15.HDTV.XviD-ASAP"],
    },
}


def _create_fake_xml(items):
    """
    Create fake xml

    :param items:
    :return:
    """
    xml = '<?xml version="1.0" encoding="UTF-8" ?><rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="https://www.newznab.com/DTD/2010/feeds/attributes/" encoding="utf-8"><channel>'
    for item in items:
        xml += "<item><title>" + item + "</title>\n"
        xml += "<link>https://www.newznab.com/" + item + "</link></item>"
    xml += "</channel></rss>"
    return xml


search_items = []


class SearchTest(conftest.SickChillTestDBCase):
    """
    Perform search tests
    """

    # patch_get_url = None
    # patch_is_active = None

    @staticmethod
    def _fake_get_url(url, headers=None):
        """
        Fake requesting url

        :param url:
        :param headers:
        :return:
        """
        _ = url, headers
        return _create_fake_xml(search_items)

    # @classmethod
    # def setUpClass(cls):
    #     mock_true = PropertyMock(return_value=True)
    #     cls.patch_is_active = patch("sickchill.providers.GenericProvider.GenericProvider.is_active", mock_true)
    #     cls.patch_is_active.start()
    #     cls.addClassCleanup(cls.patch_is_active.stop)
    #
    #     cls.patch_get_url = patch("sickchill.providers.GenericProvider.GenericProvider.get_url", cls._fake_get_url)
    #     cls.patch_get_url.start()
    #     cls.addClassCleanup(cls.patch_get_url.stop)

    @unittest.expectedFailure
    def test_search(self):
        settings.USE_TORRENTS = True
        settings.USE_NZBS = True

        for provider in sickchill.oldbeard.providers.sorted_provider_list():
            provider.get_url = self._fake_get_url
            provider.enabled = True

        for show_name, data in TESTS_DATA.items():
            if not data["active"]:
                continue

            show = TVShow(1, data["id"])

            show.name = show_name
            show.quality = data["quality"]
            show.save_to_db()

            settings.show_list.append(show)

            for episode in data["episodes"]:
                episode_object = TVEpisode(show, data["season"], episode)
                episode_object.status = common.WANTED

                related_episodes = data["episodes"]
                related_episodes.remove(episode)
                episode_object.related_episodes = related_episodes

                episode_object.save_to_db()

            for force in (True, False):
                with self.subTest(f"Test Snatch selection with {show_name} - {force}"):
                    best_result = search.search_providers(show, data["episodes"], force)
                    if not best_result:
                        self.assertEqual(data["best_result"], best_result)

                    self.assertEqual(data["best_result"], best_result.name)  # first is expected, second is chosen one


class SnatchExecutableTest(unittest.TestCase):
    """
    Refuse to snatch releases that carry executables.
    """

    def setUp(self):
        settings.BLOCK_EXECUTABLE_FILES = True
        settings.EXECUTABLE_EXTENSIONS = "exe,scr,msi,lnk,ps1"
        settings.ALLOW_HIGH_PRIORITY = False
        settings.TORRENT_METHOD = "qbittorrent"

    @staticmethod
    def _torrent_result(name, paths):
        result = TorrentSearchResult([], provider=None, url="http://example.com/x.torrent")
        result.name = name
        result.content = bencode.encode(
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
        return result

    def test_executable_release_name_is_not_snatched(self):
        result = self._torrent_result("Show.Name.S01E01.1080p.mkv.exe", [["Show.Name.S01E01.mkv"]])
        with patch("sickchill.oldbeard.clients.getClientInstance") as get_client:
            assert search.snatch_episode(result) is False
            get_client.assert_not_called()

    def test_executable_inside_torrent_is_not_snatched(self):
        result = self._torrent_result("Show.Name.S01E01.1080p.HDTV.x264-GROUP", [["Show.Name.S01E01.mkv"], ["Sample", "setup.exe"]])
        with patch("sickchill.oldbeard.clients.getClientInstance") as get_client:
            assert search.snatch_episode(result) is False
            get_client.assert_not_called()

    def test_clean_torrent_reaches_the_client(self):
        """The same result without the executable must still be handed to the client."""
        result = self._torrent_result("Show.Name.S01E01.1080p.HDTV.x264-GROUP", [["Show.Name.S01E01.mkv"], ["Subs", "Show.Name.S01E01.srt"]])
        with patch("sickchill.oldbeard.clients.getClientInstance") as get_client:
            get_client.return_value.return_value.sendTORRENT.return_value = False
            search.snatch_episode(result)
            get_client.assert_called_once()

    def test_disabled_setting_lets_it_through(self):
        settings.BLOCK_EXECUTABLE_FILES = False
        result = self._torrent_result("Show.Name.S01E01.1080p.HDTV.x264-GROUP", [["Sample", "setup.exe"]])
        with patch("sickchill.oldbeard.clients.getClientInstance") as get_client:
            get_client.return_value.return_value.sendTORRENT.return_value = False
            search.snatch_episode(result)
            get_client.assert_called_once()


if __name__ == "__main__":
    print("==================")
    print("STARTING - Snatch TESTS")
    print("==================")
    print("######################################################################")

    suite = unittest.TestLoader().loadTestsFromTestCase(SearchTest)
    unittest.TextTestRunner(verbosity=2).run(suite)
