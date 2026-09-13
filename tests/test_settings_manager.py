import json
import os
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import settings_manager


class SettingsManagerTests(unittest.TestCase):
    def _workspace_temp_dir(self, name: str) -> Path:
        temp_dir = Path("tests_tmp") / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: __import__("shutil").rmtree(temp_dir, ignore_errors=True))
        return temp_dir

    def test_migrates_legacy_clicker_config_into_profiles(self):
        temp_dir = self._workspace_temp_dir("settings_migrate")
        config_path = temp_dir / "Mconfig.json"
        legacy_path = temp_dir / "config.json"
        default_path = temp_dir / "default.json"
        legacy_path.write_text(json.dumps({
            "clicker": {
                "enabled": True,
                "button": "right",
                "intervalMs": 75,
                "hotkeyToggle": {
                    "modCtrl": False,
                    "modAlt": False,
                    "modShift": False,
                    "modWin": False,
                    "key": "F8",
                },
            }
        }, ensure_ascii=False), encoding="utf-8")

        with mock.patch.object(settings_manager, "CONFIG_PATH", str(config_path)), \
             mock.patch.object(settings_manager, "LEGACY_CONFIG_PATH", str(legacy_path)), \
             mock.patch.object(settings_manager, "CONFIG_DEFAULT_PATH", str(default_path)):
            settings = settings_manager.SettingsManager()

        profiles = settings.data["clickerProfiles"]
        self.assertEqual(len(profiles), 1)
        self.assertEqual(profiles[0]["id"], "default")
        self.assertEqual(profiles[0]["button"], "right")
        self.assertTrue(profiles[0]["enabled"])
        self.assertEqual(profiles[0]["triggers"]["toggleHotkey"]["key"], "F8")
        self.assertEqual(settings.data["activeClickerProfileId"], "default")

    def test_save_prunes_runtime_clicker_mirrors(self):
        temp_dir = self._workspace_temp_dir("settings_save")
        config_path = temp_dir / "Mconfig.json"
        legacy_path = temp_dir / "config.json"
        default_path = temp_dir / "default.json"

        with mock.patch.object(settings_manager, "CONFIG_PATH", str(config_path)), \
             mock.patch.object(settings_manager, "LEGACY_CONFIG_PATH", str(legacy_path)), \
             mock.patch.object(settings_manager, "CONFIG_DEFAULT_PATH", str(default_path)):
            settings = settings_manager.SettingsManager()
            settings.data["clicker"] = {"legacy": True}
            settings.data["clickerActiveProfile"] = {"legacy": True}
            self.assertTrue(settings.save(), msg=settings.last_error)

        payload = json.loads(config_path.read_text(encoding="utf-8"))
        self.assertNotIn("clicker", payload)
        self.assertNotIn("clickerActiveProfile", payload)

    def test_clicker_profile_crud_keeps_valid_active_profile(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {}
        settings._set_defaults()

        self.assertNotIn("clicker", settings.data)
        self.assertNotIn("clickerActiveProfile", settings.data)

        created = settings.create_clicker_profile("测试方案")
        self.assertEqual(len(settings.data["clickerProfiles"]), 2)
        self.assertEqual(settings.data["activeClickerProfileId"], created["id"])
        self.assertNotIn("clicker", settings.data)
        self.assertNotIn("clickerActiveProfile", settings.data)

        remaining = settings.delete_clicker_profile(created["id"])
        self.assertEqual(len(settings.data["clickerProfiles"]), 1)
        self.assertEqual(remaining["id"], "default")
        self.assertEqual(settings.data["activeClickerProfileId"], "default")
        self.assertNotIn("clicker", settings.data)
        self.assertNotIn("clickerActiveProfile", settings.data)

        settings.create_clicker_profile("Another")
        reset = settings.clear_clicker_profiles()
        self.assertEqual(len(settings.data["clickerProfiles"]), 1)
        self.assertEqual(settings.data["activeClickerProfileId"], reset["id"])

    def test_clicker_profile_normalizes_process_blacklist(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {}
        settings._set_defaults()

        saved = settings.upsert_clicker_profile({
            "id": "default",
            "name": "Default",
            "processBlacklist": ["steam.exe", " ", "steamwebhelper"],
        })

        self.assertEqual(saved["processBlacklist"], ["steam.exe", "steamwebhelper"])


    def test_mouse_macros_are_defaulted_and_normalized(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "mouseMacros": {
                "enabled": True,
                "source": "builder",
                "rules": [
                    {
                        "enabled": True,
                        "holdMouseButton": "bad",
                        "pressMouseButton": "left",
                        "actions": [{"type": "mouseClick", "button": "x2"}],
                    }
                ],
            }
        }
        settings._set_defaults()

        macro = settings.data["mouseMacros"]
        self.assertTrue(macro["enabled"])
        self.assertEqual(macro["rules"][0]["holdMouseButton"], "x2")
        self.assertEqual(macro["rules"][0]["actions"][0]["button"], "x2")
        self.assertTrue(macro["rules"][0]["cancelOnHoldRelease"])
        self.assertFalse(macro["rules"][0]["cancelOnPressRelease"])
        self.assertTrue(macro["rules"][0]["interruptible"])
        self.assertEqual(
            macro["panicHotkey"],
            {"modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F12"},
        )

    def test_mouse_macro_normalizes_key_down_up_and_cancel_actions(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "mouseMacros": {
                "enabled": True,
                "source": "builder",
                "rules": [
                    {
                        "enabled": True,
                        "holdMouseButton": "x1",
                        "pressMouseButton": "left",
                        "actions": [
                            {"type": "keyDown", "key": "2", "modCtrl": True},
                            {"type": "keyUp", "key": "2"},
                        ],
                        "onCancel": [{"type": "keyUp", "key": "2"}],
                        "cooldownMs": 250,
                    }
                ],
            }
        }
        settings._set_defaults()

        rule = settings.data["mouseMacros"]["rules"][0]
        self.assertEqual(rule["actions"], [
            {"type": "keyDown", "key": "2"},
            {"type": "keyUp", "key": "2"},
        ])
        self.assertEqual(rule["onCancel"], [{"type": "keyUp", "key": "2"}])
        self.assertEqual(rule["cooldownMs"], 250)
        self.assertEqual(rule["triggerMode"], "hold")

    def test_clicker_profile_normalizes_click_hold_ms(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "clickerProfiles": [
                {
                    "id": "default",
                    "name": "Default",
                    "clickHoldMs": "12",
                }
            ]
}
        settings._set_defaults()

        self.assertEqual(settings.data["clickerProfiles"][0]["clickHoldMs"], 12)

    def test_clicker_profile_defaults_and_normalizes_swap_trigger(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "clickerProfiles": [
                {
                    "id": "default",
                    "name": "Default",
                    "triggers": {
                        "swapMode": "key",
                        "swapKey": {"modCtrl": True, "modShift": False, "key": "F8"},
                        "swapMouseButton": "x2",
                    },
                }
            ]
        }
        settings._set_defaults()

        triggers = settings.data["clickerProfiles"][0]["triggers"]
        self.assertEqual(triggers["swapMode"], "key")
        self.assertEqual(
            triggers["swapKey"],
            {"modCtrl": True, "modAlt": False, "modShift": False, "modWin": False, "key": "F8"},
        )
        self.assertEqual(triggers["swapMouseButton"], "x2")

        # Sanitize an invalid swap mode back to disabled with a fresh key field.
        settings.data["clickerProfiles"][0]["triggers"]["swapMode"] = "bogus"
        settings.data["clickerProfiles"][0]["triggers"]["swapKey"] = {"key": ""}
        settings._ensure_clicker_profiles()
        triggers = settings.data["clickerProfiles"][0]["triggers"]
        self.assertEqual(triggers["swapMode"], "off")
        self.assertEqual(triggers["swapKey"]["key"], "")
        self.assertEqual(triggers["swapMouseButton"], "x2")

    def test_clicker_profile_normalizes_input_backend(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "clickerProfiles": [
                {
                    "id": "default",
                    "name": "Default",
                    "inputBackend": "native-scancode",
                },
                {
                    "id": "second",
                    "name": "Second",
                    "inputBackend": "bad",
                },
            ]
        }
        settings._set_defaults()

        self.assertEqual(settings.data["clickerProfiles"][0]["inputBackend"], "native-sendinput")
        self.assertEqual(settings.data["clickerProfiles"][1]["inputBackend"], "auto")

    def test_mouse_macro_normalizes_advanced_mouse_and_repeat_actions(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "mouseMacros": {
                "enabled": True,
                "source": "builder",
                "rules": [
                    {
                        "enabled": True,
                        "actions": [
                            {
                                "type": "repeat",
                                "count": "2",
                                "actions": [
                                    {"type": "mouseClick", "button": "left", "holdMs": "8"},
                                    {"type": "mouseMoveRelative", "dx": "3", "dy": "-2"},
                                    {"type": "mouseScroll", "dy": "-120"},
                                ],
                            },
                            {"type": "mouseMove", "x": "100", "y": "200"},
                        ],
                    }
                ],
            }
        }
        settings._set_defaults()

        actions = settings.data["mouseMacros"]["rules"][0]["actions"]
        self.assertEqual(actions[0]["count"], 2)
        self.assertEqual(actions[0]["actions"][0], {"type": "mouseClick", "button": "left", "holdMs": 8})
        self.assertEqual(actions[0]["actions"][1], {"type": "mouseMoveRelative", "dx": 3, "dy": -2})
        self.assertEqual(actions[0]["actions"][2], {"type": "mouseScroll", "dx": 0, "dy": -120})
        self.assertEqual(actions[1], {"type": "mouseMove", "x": 100, "y": 200})

    def test_mouse_macro_preserves_advanced_key_loop_fields(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "mouseMacros": {
                "enabled": True,
                "source": "builder",
                "rules": [
                    {
                        "id": "left-hold-repeat-r-toggle-1",
                        "enabled": True,
                        "triggerMode": "toggleLoop",
                        "holdKey": "1",
                        "toggleOnKey": "1",
                        "toggleOffKey": "2",
                        "pressMouseButton": "left",
                        "loopWhilePressHeld": True,
                        "loopIntervalMs": 100,
                        "actions": [{"type": "key", "key": "R"}],
                    }
                ],
            }
        }
        settings._set_defaults()

        rule = settings.data["mouseMacros"]["rules"][0]
        self.assertEqual(rule["holdKey"], "1")
        self.assertEqual(rule["toggleOnKey"], "1")
        self.assertEqual(rule["toggleOffKey"], "2")
        self.assertEqual(rule["pressMouseButton"], "left")
        self.assertTrue(rule["loopWhilePressHeld"])
        self.assertEqual(rule["loopIntervalMs"], 100)

    def test_profile_list_binding_defaults_and_normalizes_frozen_lists(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "windowSpecific": {
                "enabled": True,
                "targetWindows": ["game.exe"],
                "autoLockOnWindowFocus": True,
            },
            "profileListBinding": {
                "followProfile": False,
                "processBlacklist": [" steam.exe ", "", "overlay.exe"],
                "windowSpecific": {
                    "targetWindows": [" tool.exe ", ""],
                    "resumeAfterWindowSwitch": True,
                },
            },
        }
        settings._set_defaults()

        binding = settings.data["profileListBinding"]
        self.assertFalse(binding["followProfile"])
        self.assertEqual(binding["processBlacklist"], ["steam.exe", "overlay.exe"])
        self.assertEqual(binding["windowSpecific"]["targetWindows"], ["tool.exe"])
        self.assertTrue(binding["windowSpecific"]["enabled"])
        self.assertTrue(binding["windowSpecific"]["autoLockOnWindowFocus"])
        self.assertTrue(binding["windowSpecific"]["resumeAfterWindowSwitch"])

    def test_input_backend_aliases_are_canonicalized(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {"inputBackend": "native-scancode", "inputMode": "bad"}
        settings._set_defaults()

        self.assertEqual(settings.data["inputBackend"], "native-sendinput")
        self.assertEqual(settings.data["inputMode"], "scan-code")
        self.assertEqual(settings.data["fallbackBackend"], "native-sendinput")
        self.assertEqual(settings.data["fallbackPolicy"], "auto")

    def test_window_size_settings_default_to_disabled(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {}
        settings._set_defaults()

        self.assertIn("ui", settings.data)
        self.assertFalse(settings.data["ui"]["rememberWindowSize"])
        self.assertEqual(settings.data["ui"]["windowSize"], {"width": 0, "height": 0})

    def test_window_size_settings_are_normalized(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {"ui": {"rememberWindowSize": True, "windowSize": {"width": "960", "height": "720"}}}
        settings._set_defaults()

        self.assertTrue(settings.data["ui"]["rememberWindowSize"])
        self.assertEqual(settings.data["ui"]["windowSize"], {"width": 960, "height": 720})

    def test_virtual_hid_config_preserves_fallback_policy(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {
            "inputBackend": "virtual-hid",
            "fallbackBackend": "python-sendinput",
            "fallbackPolicy": "error",
        }
        settings._set_defaults()

        self.assertEqual(settings.data["inputBackend"], "virtual-hid")
        self.assertEqual(settings.data["fallbackBackend"], "python-sendinput")
        self.assertEqual(settings.data["fallbackPolicy"], "error")

    def test_profile_default_names_follow_language(self):
        settings = settings_manager.SettingsManager.__new__(settings_manager.SettingsManager)
        settings.loaded_from_path = ""
        settings.last_error = ""
        settings.data = {"language": "en"}
        settings._set_defaults()

        self.assertEqual(settings.get_active_clicker_profile()["name"], "Default Profile")
        created = settings.create_clicker_profile("")
        self.assertTrue(created["name"].startswith("New Profile "))


if __name__ == "__main__":
    unittest.main()
