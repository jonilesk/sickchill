from sickchill import logger, settings
from sickchill.helper.common import find_executable_files, try_int
from sickchill.oldbeard import payload_filter
from sickchill.providers.GenericProvider import GenericProvider
from sickchill.providers.result_classes import NZBSearchResult, TorrentSearchResult


class NZBProvider(GenericProvider):
    def __init__(self, name):
        super().__init__(name)

        self.provider_type = GenericProvider.NZB
        self.torznab = False

    @property
    def is_active(self):
        return bool(settings.USE_NZBS) and self.is_enabled

    def _get_result(self, episodes, provider, url):
        result = NZBSearchResult(episodes, provider, url)
        if result.is_torrent:
            result.result_type = GenericProvider.TORRENT

        return result

    def _get_size(self, item):
        try:
            size = item.get("links")[1].get("length", -1)
        except (AttributeError, IndexError, TypeError):
            size = -1

        if not size:
            logger.debug("The size was not found in the provider response")

        return try_int(size, -1)

    def _get_storage_dir(self):
        return settings.NZB_DIR

    def _verify_download(self, filename):
        """
        GenericProvider accepts anything it managed to download. Check the NZB we just wrote to
        the blackhole directory for executables; returning False makes download_result remove it.
        """
        with open(filename, "rb") as nzb_file:
            blocked = find_executable_files(payload_filter.nzb_payload_names(nzb_file.read()))

        if blocked:
            logger.warning(f"Refusing to download {filename}, it contains executable files: {', '.join(blocked)}")
            return False

        return True
