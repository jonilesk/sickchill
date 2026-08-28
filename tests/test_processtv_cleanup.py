"""
Test that process_dir cleans up the junk a release ships with, and only that.

Regression cover for the inverted filter introduced in 783a05613 (2017-03-01), which built the
deletion list as `x in video_files + rar_files` — selecting exactly the files that must be kept.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from sickchill import settings
from sickchill.oldbeard import processTV
from tests import conftest


class ProcessDirCleanupTests(conftest.SickChillTestDBCase):
    """
    Exercise the real process_dir() so the deletion list itself is under test.

    Each test processes a release folder underneath the download directory, which is the normal
    layout. delete_folder is stubbed out because it would otherwise rmtree the whole release
    folder on the next line, hiding what delete_files did or did not remove.
    """

    def setUp(self):
        super().setUp()
        settings.UNPACK = settings.UNPACK_DISABLED
        settings.PROCESS_METHOD = "move"
        # Keep the executable sweep out of the way; it is covered by test_executable_processing.
        settings.BLOCK_EXECUTABLE_FILES = False

        self.download_root = tempfile.mkdtemp()
        self.directory = os.path.join(self.download_root, "Show.Name.S01E01.1080p-GROUP")
        os.mkdir(self.directory)

        settings.TV_DOWNLOAD_DIR = self.download_root
        self.addCleanup(shutil.rmtree, self.download_root, True)
        self.addCleanup(setattr, settings, "TV_DOWNLOAD_DIR", "")
        self.addCleanup(setattr, settings, "BLOCK_EXECUTABLE_FILES", True)

    def _write(self, *names, directory=None):
        for name in names:
            with open(os.path.join(directory or self.directory, name), "w") as handle:
                handle.write("x")

    def _write_rar(self, name):
        """is_rar_file sniffs content for files that exist, so the signature has to be real."""
        with open(os.path.join(self.directory, name), "wb") as handle:
            handle.write(b"Rar!\x1a\x07\x00")

    def _process(self, path=None, moves_video=True, **kwargs):
        def fake_process_media(process_path, video_files, *args, **inner):
            # The real one moves the episode out of the folder before the deletion list is built.
            if moves_video:
                for video_file in video_files:
                    os.remove(os.path.join(process_path, video_file))

        options = {"process_method": "move", "delete_on": True, "mode": "auto"}
        options.update(kwargs)

        with (
            patch.object(processTV, "process_media", side_effect=fake_process_media),
            patch.object(processTV, "validate_dir", return_value=True),
            patch.object(processTV, "delete_folder", return_value=False),
        ):
            processTV.process_dir(path or self.directory, **options)

        return sorted(os.listdir(path or self.directory))

    def test_junk_is_deleted(self):
        self._write("Show.Name.S01E01.mkv", "promo.nfo", "readme.txt", "screens.jpg")

        assert self._process() == []

    def test_media_files_are_never_deleted(self):
        """
        The inverted filter targeted exactly these. It was harmless only because process_media
        had usually moved them away first; when it has not, the episode was deleted.
        """
        self._write("Show.Name.S01E01.mkv", "readme.txt")

        assert self._process(moves_video=False) == ["Show.Name.S01E01.mkv"]

    def test_rar_files_are_left_for_the_dedicated_rar_cleanup(self):
        """
        Rars are deleted further down, and only once the extracted directory processed cleanly.
        """
        self._write("Show.Name.S01E01.mkv", "readme.txt")
        self._write_rar("Show.Name.S01E01.rar")

        assert self._process() == ["Show.Name.S01E01.rar"]

    def test_syncthing_marker_survives(self):
        """The pre-2017 code protected .stfolder explicitly; the inversion flipped it too."""
        self._write("Show.Name.S01E01.mkv", ".stfolder", "readme.txt")

        assert self._process() == [".stfolder"]

    def test_download_directory_itself_is_never_swept(self):
        """
        The download root is routinely shared with the torrent client and other tools, so loose
        files in it are not ours to delete. delete_folder already refuses to remove it; this is
        the same protection for delete_files.
        """
        self._write("Show.Name.S01E01.mkv", "unrelated-download.zip", "notes.txt", directory=self.download_root)

        remaining = self._process(path=self.download_root)

        assert "unrelated-download.zip" in remaining
        assert "notes.txt" in remaining

    def test_nothing_is_deleted_for_manual_mode_without_delete(self):
        """The guard above the deletion list must still short-circuit."""
        self._write("Show.Name.S01E01.mkv", "readme.txt")

        assert self._process(moves_video=False, delete_on=False, mode="manual") == ["Show.Name.S01E01.mkv", "readme.txt"]

    def test_nothing_is_deleted_when_not_moving(self):
        """Copy/hardlink leave the source in place, so nothing may be removed."""
        self._write("Show.Name.S01E01.mkv", "readme.txt")

        assert self._process(moves_video=False, process_method="copy") == ["Show.Name.S01E01.mkv", "readme.txt"]


if __name__ == "__main__":
    unittest.main()
