import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtGui, QtWidgets

from widgets import HotkeyCapture


def _key_event(key):
    return QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, QtCore.Qt.NoModifier)


class HotkeyCaptureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def test_allow_simple_skips_bare_key_warning(self):
        capture = HotkeyCapture(allow_simple=True)
        capture._start_capture()
        with mock.patch.object(QtWidgets.QMessageBox, "warning") as warn:
            capture.keyPressEvent(_key_event(QtCore.Qt.Key_F8))
            warn.assert_not_called()
        self.assertEqual(capture.get_hotkey()["key"], "F8")

    def test_default_asks_before_accepting_bare_key(self):
        capture = HotkeyCapture()
        capture._start_capture()
        with mock.patch.object(QtWidgets.QMessageBox, "warning", return_value=QtWidgets.QMessageBox.Yes) as warn:
            capture.keyPressEvent(_key_event(QtCore.Qt.Key_F8))
            warn.assert_called_once()
        self.assertEqual(capture.get_hotkey()["key"], "F8")

    def test_default_reject_keeps_old_key(self):
        capture = HotkeyCapture()
        capture._start_capture()
        with mock.patch.object(QtWidgets.QMessageBox, "warning", return_value=QtWidgets.QMessageBox.No):
            capture.keyPressEvent(_key_event(QtCore.Qt.Key_F8))
        self.assertEqual(capture.get_hotkey()["key"], "")


if __name__ == "__main__":
    unittest.main()