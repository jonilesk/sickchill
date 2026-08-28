"""
Test that post processing refuses to unpack or keep executables.
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sickchill import settings
from sickchill.oldbeard import processTV
from tests import conftest


class UnrarExecutableTests(unittest.TestCase):
    """
    An archive carrying an executable must never be extracted. This is the last chance to stop
    the payload reaching the filesystem, since extractall() writes every member of the archive.
    """

    def setUp(self):
        settings.BLOCK_EXECUTABLE_FILES = True
        settings.EXECUTABLE_EXTENSIONS = "exe,scr,msi"
        settings.UNPACK = settings.UNPACK_PROCESS_CONTENTS
        settings.UNPACK_DIR = ""

        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def _unrar_with_contents(self, namelist):
        """Drive the real unrar() against a fake archive listing, and report if it extracted."""
        handle = MagicMock()
        handle.needs_password.return_value = False
        handle.namelist.return_value = namelist

        result = processTV.ProcessResult()
        with patch.object(processTV, "RarFile", return_value=handle), patch.object(processTV, "already_processed", return_value=False):
            unpacked = processTV.unrar(self.directory, ["Show.Name.S01E01.rar"], False, result)

        return handle, unpacked, result

    def test_archive_with_executable_is_not_extracted(self):
        handle, unpacked, result = self._unrar_with_contents(["Show.Name.S01E01.mkv", "Sample/setup.exe"])

        handle.extractall.assert_not_called()
        assert unpacked == []
        assert "executable" in result.output

    def test_archive_with_disguised_executable_is_not_extracted(self):
        handle, unpacked, _ = self._unrar_with_contents(["Show.Name.S01E01.1080p.mkv.exe"])

        handle.extractall.assert_not_called()
        assert unpacked == []

    def test_clean_archive_is_still_extracted(self):
        handle, unpacked, _ = self._unrar_with_contents(["Show.Name.S01E01.mkv", "Subs/Show.Name.S01E01.srt"])

        handle.extractall.assert_called_once()
        assert len(unpacked) == 1

    def test_disabled_setting_still_extracts(self):
        settings.BLOCK_EXECUTABLE_FILES = False
        handle, unpacked, _ = self._unrar_with_contents(["Show.Name.S01E01.mkv", "Sample/setup.exe"])

        handle.extractall.assert_called_once()
        assert len(unpacked) == 1


class ProcessDirSweepTests(conftest.SickChillTestDBCase):
    """
    Executables that reach the processing folder are deleted rather than left behind.

    These drive the real process_dir() so the sweep itself is under test, not a copy of it.
    """

    def setUp(self):
        super().setUp()
        settings.BLOCK_EXECUTABLE_FILES = True
        settings.EXECUTABLE_EXTENSIONS = "exe,scr,msi"
        settings.UNPACK = settings.UNPACK_DISABLED
        settings.PROCESS_METHOD = "move"

        self.directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.directory, True)

    def _write(self, *names):
        for name in names:
            with open(os.path.join(self.directory, name), "w") as handle:
                handle.write("x")

    def _process(self):
        # process_media needs a matching show to do anything useful; we only care that the
        # executables are gone by the time it is reached, so let it fail.
        with patch.object(processTV, "process_media"), patch.object(processTV, "delete_folder", return_value=False):
            processTV.process_dir(self.directory, process_method="move", mode="manual")

    def test_executables_are_deleted_and_media_is_kept(self):
        self._write("Show.Name.S01E01.mkv", "setup.exe", "Show.Name.S01E01.1080p.mkv.exe", "Show.Name.S01E01.srt")

        self._process()

        assert sorted(os.listdir(self.directory)) == ["Show.Name.S01E01.mkv", "Show.Name.S01E01.srt"]

    def test_executables_are_deleted_from_a_folder_with_no_media(self):
        """
        The folder that is nothing but malware is the case that matters most, and it is also the
        one validate_dir rejects, so the sweep has to run before that check.
        """
        self._write("Show.Name.S01E01.1080p.mkv.exe", "readme.txt")

        self._process()

        assert os.listdir(self.directory) == ["readme.txt"]

    def test_nothing_is_deleted_when_disabled(self):
        settings.BLOCK_EXECUTABLE_FILES = False
        self._write("Show.Name.S01E01.mkv", "setup.exe")

        self._process()

        assert sorted(os.listdir(self.directory)) == ["Show.Name.S01E01.mkv", "setup.exe"]


if __name__ == "__main__":
    unittest.main()
