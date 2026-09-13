import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from ui.forms.settings_form import (
    apply_general_settings_form_data,
    collect_general_settings_form_data,
)
from ui.forms.clicker_profile_form import collect_clicker_profile_form_data


class _ValueWidget:
    def __init__(self, value):
        self._value = value

    def value(self):
        return self._value


class _CheckWidget:
    def __init__(self, checked):
        self._checked = checked

    def isChecked(self):
        return self._checked


class _ComboWidget:
    def __init__(self, data):
        self._data = data

    def currentData(self):
        return self._data


class _HotkeyWidget:
    def __init__(self, spec):
        self._spec = spec

    def get_hotkey(self):
        return self._spec


class _LineEditWidget:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class _ListItem:
    def __init__(self, text):
        self._text = text

    def text(self):
        return self._text


class _ListWidget:
    def __init__(self, items):
        self._items = [_ListItem(item) for item in items]

    def count(self):
        return len(self._items)

    def item(self, index):
        return self._items[index]


class SettingsFormTests(unittest.TestCase):
    def test_collect_and_apply_general_settings_form_data(self):
        window = types.SimpleNamespace(
            lockHotkeyCapture=_HotkeyWidget({"modCtrl": True, "modAlt": True, "modShift": False, "modWin": False, "key": "F9"}),
            unlockHotkeyCapture=_HotkeyWidget({"modCtrl": True, "modAlt": True, "modShift": False, "modWin": False, "key": "F10"}),
            toggleHotkeyCapture=_HotkeyWidget({"modCtrl": True, "modAlt": False, "modShift": False, "modWin": False, "key": "K"}),
            recenterCheck=_CheckWidget(True),
            recenterSpin=_ValueWidget(250),
            posCombo=_ComboWidget("custom"),
            customXSpin=_ValueWidget(123),
            customYSpin=_ValueWidget(456),
            windowSpecificCheck=_CheckWidget(True),
            targetList=_ListWidget(["game.exe", "Minecraft"]),
            autoLockCheck=_CheckWidget(True),
            resumeAfterSwitchCheck=_CheckWidget(False),
            langCombo=_ComboWidget("zh-Hant"),
            themeCombo=_ComboWidget("dark"),
            startupCheck=_CheckWidget(True),
        )
        settings = types.SimpleNamespace(data={})

        form_data = collect_general_settings_form_data(window)
        apply_general_settings_form_data(settings, form_data)

        self.assertEqual(settings.data["hotkeys"]["lock"]["key"], "F9")
        self.assertEqual(settings.data["recenter"]["intervalMs"], 250)
        self.assertEqual(settings.data["position"]["customX"], 123)
        self.assertEqual(settings.data["windowSpecific"]["targetWindows"], ["game.exe", "Minecraft"])
        self.assertEqual(settings.data["language"], "zh-Hant")
        self.assertTrue(settings.data["startup"]["launchOnBoot"])

    def test_collect_and_apply_profile_list_binding_freezes_current_lists(self):
        window = types.SimpleNamespace(
            settings=types.SimpleNamespace(data={"profileListBinding": {"followProfile": True}}),
            lockHotkeyCapture=_HotkeyWidget({"key": "F9"}),
            unlockHotkeyCapture=_HotkeyWidget({"key": "F10"}),
            toggleHotkeyCapture=_HotkeyWidget({"key": "K"}),
            recenterCheck=_CheckWidget(True),
            recenterSpin=_ValueWidget(250),
            posCombo=_ComboWidget("virtualCenter"),
            customXSpin=_ValueWidget(0),
            customYSpin=_ValueWidget(0),
            windowSpecificCheck=_CheckWidget(True),
            targetList=_ListWidget(["game.exe", "tool.exe"]),
            autoLockCheck=_CheckWidget(True),
            resumeAfterSwitchCheck=_CheckWidget(False),
            profileListFollowCheck=_CheckWidget(False),
            clickerProcessBlacklist=_ListWidget(["steam.exe", "overlay.exe"]),
            langCombo=_ComboWidget("zh-Hans"),
            themeCombo=_ComboWidget("dark"),
            startupCheck=_CheckWidget(False),
        )
        settings = types.SimpleNamespace(data={})

        form_data = collect_general_settings_form_data(window)
        apply_general_settings_form_data(settings, form_data)

        binding = settings.data["profileListBinding"]
        self.assertFalse(binding["followProfile"])
        self.assertEqual(binding["processBlacklist"], ["steam.exe", "overlay.exe"])
        self.assertEqual(binding["windowSpecific"]["targetWindows"], ["game.exe", "tool.exe"])
        self.assertTrue(binding["windowSpecific"]["enabled"])

    def test_collect_clicker_profile_includes_process_blacklist(self):
        window = types.SimpleNamespace(
            _get_active_clicker_profile=lambda: {"id": "default", "name": "默认方案"},
            _selected_profile_id="default",
            clickerProfileNameEdit=_LineEditWidget("Steam Safe"),
            clickerEnabledCheck=_CheckWidget(True),
            clickerButtonCombo=_ComboWidget("left"),
            clickerInputBackendCombo=_ComboWidget("window-message"),
            clickerPresetCombo=_ComboWidget("efficient"),
            clickerIntervalSpin=_ValueWidget(100),
            clickerSoundEnabledCheck=_CheckWidget(False),
            clickerSoundPresetCombo=_ComboWidget("systemAsterisk"),
            clickerCustomSoundPathEdit=_LineEditWidget(""),
            clickerProcessBlacklist=_ListWidget(["steam.exe", "steamwebhelper.exe"]),
clickerTriggerModeCombo=_ComboWidget("holdMouseButton"),
            clickerToggleHotkeyCapture=_HotkeyWidget({"key": "F6"}),
            clickerHoldKeyCapture=_HotkeyWidget({"key": "F7"}),
            clickerHoldMouseCombo=_ComboWidget("x1"),
            clickerSwapModeCombo=_ComboWidget("mouseButton"),
            clickerSwapKeyCapture=_HotkeyWidget({"key": "F8"}),
            clickerSwapMouseCombo=_ComboWidget("x2"),
            _current_general_settings_form_data=lambda: {
                "mouseMacros": {"enabled": True},
                "recenter": {"enabled": False, "intervalMs": 500},
                "startup": {"launchOnBoot": True},
            },
)

        profile = collect_clicker_profile_form_data(window)

        self.assertEqual(profile["processBlacklist"], ["steam.exe", "steamwebhelper.exe"])
        self.assertEqual(profile["inputBackend"], "window-message")
        self.assertEqual(profile["triggers"]["holdMouseButton"], "x1")
        self.assertEqual(profile["triggers"]["swapMode"], "mouseButton")
        self.assertEqual(profile["triggers"]["swapKey"], {"key": "F8"})
        self.assertEqual(profile["triggers"]["swapMouseButton"], "x2")
        self.assertEqual(profile["featureSettings"]["mouseMacros"], {"enabled": True})
        self.assertNotIn("startup", profile["featureSettings"])


if __name__ == "__main__":
    unittest.main()
