"""
Application settings loading, migration, and persistence.
"""
from __future__ import annotations

import copy
import json
import uuid
from typing import Any, Dict, List, Optional

from app_logging import log_exception
from app_paths import APP_DIR, RUN_DIR
from services.input_backends import (
    BACKEND_NATIVE_SENDINPUT,
    INPUT_BACKENDS,
    INPUT_BACKEND_ALIASES,
    normalize_fallback_policy,
)
from services.sound_service import SYSTEM_SOUND_PRESETS, normalize_sound_config
from services.macro_schema import (
    MOUSE_BUTTONS,
    MOUSE_MACRO_ACTION_TYPES,
    normalize_macro_trigger_mode,
    normalize_mouse_button,
)

import os

CONFIG_DEFAULT_PATH = os.path.join(APP_DIR, "Mconfig.json")
CONFIG_EXAMPLE_PATH = os.path.join(APP_DIR, "Mconfig.example.json")
CONFIG_PATH = os.path.join(RUN_DIR, "Mconfig.json")
LEGACY_CONFIG_PATH = os.path.join(RUN_DIR, "config.json")

CLICKER_PRESETS = {
    "custom": None,
    "efficient": 100,
    "extreme": 10,
}

CLICKER_SOUND_PRESETS = SYSTEM_SOUND_PRESETS

CLICKER_TRIGGER_MODES = {
    "toggle": "clicker.trigger.toggle",
    "holdKey": "clicker.trigger.holdKey",
    "holdMouseButton": "clicker.trigger.holdMouseButton",
}

# Swap sources: keep the clicker button as-is, swap it while a keyboard
# shortcut or a mouse button is held, or disable the feature entirely.
CLICKER_SWAP_MODES = ("off", "key", "mouseButton")
DEFAULT_CLICKER_SWAP_MOUSE_BUTTON = "x1"

DEFAULT_PROFILE_NAMES = {
    "en": "Default Profile",
    "zh-Hans": "默认方案",
    "zh-Hant": "預設方案",
    "ja": "既定プロファイル",
    "ko": "기본 프로필",
}

NEW_PROFILE_BASE_NAMES = {
    "en": "New Profile",
    "zh-Hans": "新方案",
    "zh-Hant": "新方案",
    "ja": "新しいプロファイル",
    "ko": "새 프로필",
}


def load_json(path: str, default: Any) -> Any:
    """Load JSON from file, returning default on error."""
    try:
        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default


def deep_copy(data: Any) -> Any:
    """Return a detached copy of nested config data."""
    return copy.deepcopy(data)


def normalize_hotkey(config: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize hotkey dictionaries to the expected shape."""
    data = config if isinstance(config, dict) else {}
    normalized = deep_copy(fallback)
    for field in ["modCtrl", "modAlt", "modShift", "modWin", "key"]:
        if field == "key":
            normalized[field] = str(data.get(field, normalized[field]) or "")
        else:
            normalized[field] = bool(data.get(field, normalized[field]))
    return normalized


def bounded_int(value: Any, default: int = 0, minimum: int = 0, maximum: int = 60000) -> int:
    """Parse and clamp an integer config value."""
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(minimum, min(maximum, parsed))


class SettingsManager:
    """Manages application settings including loading, validation, and saving."""

    DEFAULT_HOTKEYS = {
        "lock": {"modCtrl": True, "modAlt": True, "modShift": False, "modWin": False, "key": "F9"},
        "unlock": {"modCtrl": True, "modAlt": True, "modShift": False, "modWin": False, "key": "F10"},
        "toggle": {"modCtrl": True, "modAlt": True, "modShift": False, "modWin": False, "key": "K"},
    }
    DEFAULT_CLICKER_HOTKEY = {
        "modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F6",
    }
    DEFAULT_HOLD_KEY = {
        "modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F7",
    }
    DEFAULT_SWAP_KEY = {
        "modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F8",
    }
    DEFAULT_MOUSE_MACRO_PANIC_HOTKEY = {
        "modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F12",
    }
    DEFAULT_CLICKER_SOUND = {
        "start": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
        "stop": {"enabled": False, "preset": "systemHand", "customFile": ""},
    }

    def __init__(self):
        self.loaded_from_path = ""
        self.last_error = ""
        data = None
        for candidate in [CONFIG_PATH, LEGACY_CONFIG_PATH, CONFIG_DEFAULT_PATH, CONFIG_EXAMPLE_PATH]:
            loaded = load_json(candidate, None)
            if isinstance(loaded, dict):
                self.loaded_from_path = candidate
                data = loaded
                break
        if data is None:
            data = {}

        self.data: Dict[str, Any] = data if isinstance(data, dict) else {}
        self._set_defaults()

    def _set_defaults(self):
        """Ensure all required settings have default values."""
        self.data.setdefault("language", "zh-Hans")
        self.data.setdefault("theme", "dark")
        self.data.setdefault("hotkeys", self.DEFAULT_HOTKEYS.copy())
        self._ensure_clicker_profiles()

        for key in ["lock", "unlock", "toggle"]:
            if key not in self.data["hotkeys"]:
                self.data["hotkeys"][key] = self.DEFAULT_HOTKEYS[key].copy()
            else:
                for field in ["modCtrl", "modAlt", "modShift", "modWin", "key"]:
                    self.data["hotkeys"][key].setdefault(
                        field,
                        self.DEFAULT_HOTKEYS[key].get(field, False if field != "key" else ""),
                    )

        self.data.setdefault("recenter", {"enabled": True, "intervalMs": 250})
        self.data.setdefault("position", {"mode": "virtualCenter", "customX": 0, "customY": 0})
        window_specific = self.data.setdefault("windowSpecific", {})
        if "targetWindow" in window_specific and "targetWindows" not in window_specific:
            value = window_specific.pop("targetWindow")
            window_specific["targetWindows"] = [value] if value else []

        window_specific.setdefault("enabled", False)
        window_specific.setdefault("targetWindows", [])
        window_specific.setdefault("targetWindowHandle", 0)
        window_specific.setdefault("autoLockOnWindowFocus", False)
        window_specific.setdefault("resumeAfterWindowSwitch", False)
        list_binding = self.data.setdefault("profileListBinding", {})
        if not isinstance(list_binding, dict):
            list_binding = {}
        frozen_window_specific = list_binding.get("windowSpecific", {})
        if not isinstance(frozen_window_specific, dict):
            frozen_window_specific = {}
        frozen_blacklist = list_binding.get("processBlacklist", [])
        if not isinstance(frozen_blacklist, list):
            frozen_blacklist = []
        self.data["profileListBinding"] = {
            "followProfile": bool(list_binding.get("followProfile", True)),
            "processBlacklist": [
                str(item).strip()
                for item in frozen_blacklist
                if str(item).strip()
            ],
            "windowSpecific": {
                "enabled": bool(frozen_window_specific.get("enabled", window_specific.get("enabled", False))),
                "targetWindows": [
                    str(item).strip()
                    for item in frozen_window_specific.get("targetWindows", window_specific.get("targetWindows", []))
                    if str(item).strip()
                ],
                "targetWindowHandle": 0,
                "autoLockOnWindowFocus": bool(
                    frozen_window_specific.get("autoLockOnWindowFocus", window_specific.get("autoLockOnWindowFocus", False))
                ),
                "resumeAfterWindowSwitch": bool(
                    frozen_window_specific.get("resumeAfterWindowSwitch", window_specific.get("resumeAfterWindowSwitch", False))
                ),
            },
        }
        self.data.setdefault("startup", {"launchOnBoot": False})
        self.data.setdefault("closeAction", "ask")
        taskbar_settings = self.data.setdefault("taskbar", {})
        if not isinstance(taskbar_settings, dict):
            taskbar_settings = {}
        try:
            flash_ms = max(100, min(10000, int(taskbar_settings.get("stateFlashMs", 1000) or 1000)))
        except Exception:
            flash_ms = 1000
        self.data["taskbar"] = {
            "stateFlashEnabled": bool(taskbar_settings.get("stateFlashEnabled", True)),
            "stateFlashMs": flash_ms,
        }
        ui_settings = self.data.setdefault("ui", {})
        if not isinstance(ui_settings, dict):
            ui_settings = {}
        remember_window_size = bool(ui_settings.get("rememberWindowSize", False))
        window_size = ui_settings.get("windowSize", {})
        if not isinstance(window_size, dict):
            window_size = {}
        try:
            width = max(0, int(window_size.get("width", 0) or 0))
            height = max(0, int(window_size.get("height", 0) or 0))
        except Exception:
            width = 0
            height = 0
        self.data["ui"] = {
            "rememberWindowSize": remember_window_size,
            "windowSize": {"width": width, "height": height},
        }
        backend = str(self.data.get("inputBackend", "auto") or "auto").strip().lower()
        backend = INPUT_BACKEND_ALIASES.get(backend, backend)
        self.data["inputBackend"] = backend if backend in INPUT_BACKENDS else "auto"
        fallback_backend = str(self.data.get("fallbackBackend", BACKEND_NATIVE_SENDINPUT) or BACKEND_NATIVE_SENDINPUT).strip().lower()
        fallback_backend = INPUT_BACKEND_ALIASES.get(fallback_backend, fallback_backend)
        self.data["fallbackBackend"] = fallback_backend if fallback_backend in INPUT_BACKENDS - {"auto"} else BACKEND_NATIVE_SENDINPUT
        self.data["fallbackPolicy"] = normalize_fallback_policy(self.data.get("fallbackPolicy", "auto"))
        input_mode = str(self.data.get("inputMode", "scan-code") or "scan-code").strip().lower()
        self.data["inputMode"] = input_mode if input_mode in ("virtual-key", "scan-code", "unicode") else "scan-code"
        self._ensure_mouse_macros()

    def _language_code(self) -> str:
        """Return the current settings language or a safe fallback."""
        lang_code = str(self.data.get("language", "zh-Hans") or "zh-Hans")
        return lang_code if lang_code in DEFAULT_PROFILE_NAMES else "en"

    def _default_profile_name(self) -> str:
        """Return the localized default clicker profile name."""
        return DEFAULT_PROFILE_NAMES[self._language_code()]

    def _new_profile_base_name(self) -> str:
        """Return the localized base name used for new clicker profiles."""
        return NEW_PROFILE_BASE_NAMES[self._language_code()]

    def _default_clicker_profile(self) -> Dict[str, Any]:
        """Return the default clicker profile template."""
        return {
            "id": "default",
            "name": self._default_profile_name(),
            "enabled": False,
            "button": "left",
            "inputBackend": "auto",
            "intervalMs": 100,
            "clickHoldMs": 0,
            "preset": "efficient",
            "sound": deep_copy(self.DEFAULT_CLICKER_SOUND),
            "processBlacklist": [],
            "triggers": {
                "mode": "toggle",
                "toggleHotkey": deep_copy(self.DEFAULT_CLICKER_HOTKEY),
                "holdKey": deep_copy(self.DEFAULT_HOLD_KEY),
                "holdMouseButton": "middle",
                "swapMode": "off",
                "swapKey": deep_copy(self.DEFAULT_SWAP_KEY),
                "swapMouseButton": DEFAULT_CLICKER_SWAP_MOUSE_BUTTON,
            },
        }

    def _normalize_clicker_profile(self, profile: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
        """Normalize a clicker profile from config."""
        base = self._default_clicker_profile()
        source = profile if isinstance(profile, dict) else {}

        normalized = deep_copy(base)
        normalized["id"] = str(source.get("id") or f"profile-{index + 1}")
        normalized["name"] = str(source.get("name") or base["name"])
        normalized["enabled"] = bool(source.get("enabled", False))
        normalized["button"] = source.get("button", "left") if source.get("button") in ("left", "right", "middle") else "left"
        backend = str(source.get("inputBackend", "auto") or "auto").strip().lower()
        backend = INPUT_BACKEND_ALIASES.get(backend, backend)
        normalized["inputBackend"] = backend if backend in INPUT_BACKENDS else "auto"
        normalized["intervalMs"] = max(1, int(source.get("intervalMs", 100)))
        normalized["clickHoldMs"] = bounded_int(
            source.get("clickHoldMs", base["clickHoldMs"]),
            base["clickHoldMs"],
            0,
            1000,
        )
        preset = source.get("preset")
        normalized["preset"] = preset if preset in CLICKER_PRESETS else self._resolve_preset(normalized["intervalMs"])

        normalized["sound"] = normalize_sound_config(source.get("sound", normalized["sound"]))

        process_blacklist = source.get("processBlacklist", [])
        if not isinstance(process_blacklist, list):
            process_blacklist = []
        normalized["processBlacklist"] = [
            str(item).strip()
            for item in process_blacklist
            if str(item).strip()
        ]

        triggers = source.get("triggers", {})
        legacy_toggle = source.get("hotkeyToggle", {})
        normalized["triggers"]["mode"] = triggers.get("mode", "toggle")
        if normalized["triggers"]["mode"] not in CLICKER_TRIGGER_MODES:
            normalized["triggers"]["mode"] = "toggle"
        normalized["triggers"]["toggleHotkey"] = normalize_hotkey(
            triggers.get("toggleHotkey", legacy_toggle), self.DEFAULT_CLICKER_HOTKEY
        )
        normalized["triggers"]["holdKey"] = normalize_hotkey(
            triggers.get("holdKey", {}), self.DEFAULT_HOLD_KEY
        )
        normalized["triggers"]["holdMouseButton"] = normalize_mouse_button(triggers.get("holdMouseButton", "middle"), "middle")
        swap_mode = str(triggers.get("swapMode", "off") or "off").strip()
        normalized["triggers"]["swapMode"] = swap_mode if swap_mode in CLICKER_SWAP_MODES else "off"
        normalized["triggers"]["swapKey"] = normalize_hotkey(
            triggers.get("swapKey", {}), self.DEFAULT_SWAP_KEY
        )
        normalized["triggers"]["swapMouseButton"] = normalize_mouse_button(
            triggers.get("swapMouseButton", DEFAULT_CLICKER_SWAP_MOUSE_BUTTON),
            DEFAULT_CLICKER_SWAP_MOUSE_BUTTON,
        )
        feature_settings = source.get("featureSettings", {})
        normalized["featureSettings"] = deep_copy(feature_settings) if isinstance(feature_settings, dict) else {}
        return normalized


    def _default_mouse_macro_config(self) -> Dict[str, Any]:
        """Return the default mouse macro configuration."""
        return {
            "enabled": False,
            "source": "builder",
            "configFile": "",
            "panicHotkey": deep_copy(self.DEFAULT_MOUSE_MACRO_PANIC_HOTKEY),
            "sound": deep_copy(self.DEFAULT_CLICKER_SOUND),
            "rules": [
                {
                    "id": "x2-left-default",
                    "name": "X2 + Left",
                    "enabled": False,
                    "triggerMode": "hold",
                    "holdMouseButton": "x2",
                    "pressMouseButton": "left",
                    "cancelOnHoldRelease": True,
                    "cancelOnPressRelease": False,
                    "cancelOnFocusLost": False,
                    "cooldownMs": 0,
                    "interruptible": True,
                    "actions": [
                        {
                            "type": "hotkey",
                            "modCtrl": True,
                            "modAlt": False,
                            "modShift": False,
                            "modWin": False,
                            "key": "C",
                        }
                    ],
                }
            ],
        }

    def _normalize_macro_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a macro action from config."""
        source = action if isinstance(action, dict) else {}
        action_type = str(source.get("type", "hotkey") or "hotkey")
        if action_type not in MOUSE_MACRO_ACTION_TYPES:
            action_type = "hotkey"
        normalized: Dict[str, Any] = {"type": action_type}
        if action_type == "hotkey":
            normalized.update(normalize_hotkey(source, {"modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": ""}))
        elif action_type in ("key", "keyDown", "keyUp"):
            normalized["key"] = str(source.get("key", "") or "")
        elif action_type in ("mouseDown", "mouseUp", "mouseClick"):
            normalized["button"] = normalize_mouse_button(source.get("button", "left"), "left")
            if action_type == "mouseClick":
                normalized["holdMs"] = bounded_int(source.get("holdMs", 0), 0, 0, 5000)
        elif action_type == "mouseMove":
            normalized["x"] = bounded_int(source.get("x", 0), 0, -100000, 100000)
            normalized["y"] = bounded_int(source.get("y", 0), 0, -100000, 100000)
        elif action_type == "mouseMoveRelative":
            normalized["dx"] = bounded_int(source.get("dx", 0), 0, -32767, 32767)
            normalized["dy"] = bounded_int(source.get("dy", 0), 0, -32767, 32767)
        elif action_type == "mouseScroll":
            normalized["dx"] = bounded_int(source.get("dx", 0), 0, -12000, 12000)
            normalized["dy"] = bounded_int(source.get("dy", source.get("amount", 0)), 0, -12000, 12000)
        elif action_type == "text":
            normalized["text"] = str(source.get("text", "") or "")
        elif action_type == "delay":
            normalized["ms"] = bounded_int(source.get("ms", 0), 0, 0, 60000)
        elif action_type == "repeat":
            nested_actions = source.get("actions", [])
            if not isinstance(nested_actions, list):
                nested_actions = []
            normalized["count"] = bounded_int(source.get("count", 1), 1, 0, 1000)
            normalized["actions"] = [self._normalize_macro_action(action) for action in nested_actions[:32]]
        return normalized

    def _normalize_macro_rule(self, rule: Dict[str, Any], index: int = 0) -> Dict[str, Any]:
        """Normalize a mouse macro rule."""
        source = rule if isinstance(rule, dict) else {}
        hold = normalize_mouse_button(source.get("holdMouseButton", "x2"), "x2")
        press = normalize_mouse_button(source.get("pressMouseButton", "left"), "left")
        trigger_mode = normalize_macro_trigger_mode(source.get("triggerMode", "hold"), "hold")
        actions = source.get("actions", [])
        if not isinstance(actions, list) or not actions:
            actions = [{"type": "hotkey", "modCtrl": True, "key": "C"}]
        on_cancel = source.get("onCancel", [])
        if not isinstance(on_cancel, list):
            on_cancel = []
        normalized_rule = {
            "id": str(source.get("id") or f"macro-{index + 1}"),
            "name": str(source.get("name") or f"Macro {index + 1}"),
            "enabled": bool(source.get("enabled", False)),
            "triggerMode": trigger_mode,
            "holdMouseButton": hold if hold in MOUSE_BUTTONS else "x2",
            "pressMouseButton": press if press in MOUSE_BUTTONS else "left",
            "cancelOnHoldRelease": bool(source.get("cancelOnHoldRelease", True)),
            "cancelOnPressRelease": bool(source.get("cancelOnPressRelease", False)),
            "cancelOnFocusLost": bool(source.get("cancelOnFocusLost", False)),
            "cooldownMs": max(0, min(60000, int(source.get("cooldownMs", 0) or 0))),
            "loopIntervalMs": max(1, min(60000, int(source.get("loopIntervalMs", source.get("cooldownMs", 1)) or 1))),
            "loopWhilePressHeld": bool(source.get("loopWhilePressHeld", False)),
            "interruptible": bool(source.get("interruptible", True)),
            "actions": [self._normalize_macro_action(action) for action in actions[:32]],
            "onCancel": [self._normalize_macro_action(action) for action in on_cancel[:16]],
        }
        if "holdKey" in source:
            normalized_rule["holdKey"] = str(source.get("holdKey", "") or "")
        if "pressKey" in source:
            normalized_rule["pressKey"] = str(source.get("pressKey", "") or "")
        if "toggleOnKey" in source:
            normalized_rule["toggleOnKey"] = str(source.get("toggleOnKey", "") or "")
        if "toggleOffKey" in source:
            normalized_rule["toggleOffKey"] = str(source.get("toggleOffKey", "") or "")
        if "toggleOnMouseButton" in source:
            raw = str(source.get("toggleOnMouseButton", "") or "").strip()
            normalized_rule["toggleOnMouseButton"] = normalize_mouse_button(raw, "left") if raw else ""
        if "toggleOffMouseButton" in source:
            raw = str(source.get("toggleOffMouseButton", "") or "").strip()
            normalized_rule["toggleOffMouseButton"] = normalize_mouse_button(raw, "left") if raw else ""
        return normalized_rule

    def _ensure_mouse_macros(self) -> None:
        """Normalize mouse macro configuration."""
        default = self._default_mouse_macro_config()
        source = self.data.get("mouseMacros", {})
        if not isinstance(source, dict):
            source = {}
        rules = source.get("rules", default["rules"])
        if not isinstance(rules, list):
            rules = default["rules"]
        normalized_rules = [self._normalize_macro_rule(rule, idx) for idx, rule in enumerate(rules)]
        if not normalized_rules:
            normalized_rules = [self._normalize_macro_rule(default["rules"][0], 0)]
        source_mode = str(source.get("source", "builder") or "builder")
        self.data["mouseMacros"] = {
            "enabled": bool(source.get("enabled", False)),
            "source": source_mode if source_mode in ("builder", "file") else "builder",
            "configFile": str(source.get("configFile", "") or ""),
            "panicHotkey": normalize_hotkey(
                source.get("panicHotkey", {}),
                self.DEFAULT_MOUSE_MACRO_PANIC_HOTKEY,
            ),
            "sound": normalize_sound_config(source.get("sound", default["sound"])),
            "rules": normalized_rules,
        }

    def _resolve_preset(self, interval_ms: int) -> str:
        """Resolve a click interval to its preset label."""
        normalized = max(1, int(interval_ms))
        for preset_key, preset_interval in CLICKER_PRESETS.items():
            if preset_interval == normalized:
                return preset_key
        return "custom"

    def _ensure_clicker_profiles(self):
        """Migrate legacy clicker config and normalize clicker profile storage."""
        profiles = self.data.get("clickerProfiles")
        if not isinstance(profiles, list) or not profiles:
            legacy_clicker = self.data.get("clicker", {})
            profile = self._default_clicker_profile()
            if isinstance(legacy_clicker, dict):
                legacy_profile = {
                    "id": "default",
                    "name": self._default_profile_name(),
                    "enabled": legacy_clicker.get("enabled", False),
                    "button": legacy_clicker.get("button", "left"),
                    "intervalMs": legacy_clicker.get("intervalMs", 100),
                    "preset": legacy_clicker.get("preset", self._resolve_preset(legacy_clicker.get("intervalMs", 100))),
                    "triggers": {
                        "mode": "toggle",
                        "toggleHotkey": legacy_clicker.get("hotkeyToggle", self.DEFAULT_CLICKER_HOTKEY),
                        "holdKey": self.DEFAULT_HOLD_KEY,
                        "holdMouseButton": "middle",
                    },
                }
                profile = self._normalize_clicker_profile(legacy_profile)
            profiles = [profile]
            self.data["clickerProfiles"] = profiles

        normalized_profiles: List[Dict[str, Any]] = []
        seen_ids = set()
        for index, profile in enumerate(profiles):
            normalized = self._normalize_clicker_profile(profile, index)
            if normalized["id"] in seen_ids:
                normalized["id"] = f"{normalized['id']}-{index + 1}"
            seen_ids.add(normalized["id"])
            normalized_profiles.append(normalized)

        if not normalized_profiles:
            normalized_profiles = [self._default_clicker_profile()]

        self.data["clickerProfiles"] = normalized_profiles
        active_id = str(self.data.get("activeClickerProfileId") or normalized_profiles[0]["id"])
        if not any(profile["id"] == active_id for profile in normalized_profiles):
            active_id = normalized_profiles[0]["id"]
        self.data["activeClickerProfileId"] = active_id
        self.data.pop("clickerActiveProfile", None)
        self.data.pop("clicker", None)

    def get_clicker_profiles(self) -> List[Dict[str, Any]]:
        """Return deep-copied clicker profiles."""
        return [deep_copy(profile) for profile in self.data.get("clickerProfiles", [])]

    def get_active_clicker_profile(self) -> Dict[str, Any]:
        """Return the active clicker profile."""
        active_id = self.data.get("activeClickerProfileId")
        for profile in self.data.get("clickerProfiles", []):
            if profile.get("id") == active_id:
                return deep_copy(profile)
        first = self.data.get("clickerProfiles", [self._default_clicker_profile()])[0]
        return deep_copy(first)

    def set_active_clicker_profile(self, profile_id: str) -> Dict[str, Any]:
        """Set the active clicker profile by id."""
        for profile in self.data.get("clickerProfiles", []):
            if profile.get("id") == profile_id:
                self.data["activeClickerProfileId"] = profile_id
                return deep_copy(profile)
        return self.get_active_clicker_profile()

    def upsert_clicker_profile(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        """Create or update a clicker profile and make it active."""
        normalized = self._normalize_clicker_profile(profile, len(self.data.get("clickerProfiles", [])))
        profiles = self.data.setdefault("clickerProfiles", [])
        for index, existing in enumerate(profiles):
            if existing.get("id") == normalized["id"]:
                profiles[index] = normalized
                break
        else:
            if any(existing.get("id") == normalized["id"] for existing in profiles):
                normalized["id"] = uuid.uuid4().hex[:8]
            profiles.append(normalized)
        return self.set_active_clicker_profile(normalized["id"])

    def create_clicker_profile(self, name: str, base_profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new clicker profile from the provided base."""
        profile = self._normalize_clicker_profile(base_profile or self.get_active_clicker_profile())
        profile["id"] = uuid.uuid4().hex[:8]
        profile["name"] = name.strip() or self._generate_profile_name()
        return self.upsert_clicker_profile(profile)

    def delete_clicker_profile(self, profile_id: str) -> Dict[str, Any]:
        """Delete a clicker profile while preserving at least one profile."""
        profiles = self.data.get("clickerProfiles", [])
        if len(profiles) <= 1:
            remaining = self._normalize_clicker_profile(profiles[0] if profiles else self._default_clicker_profile())
            remaining["id"] = "default"
            remaining["name"] = self._default_profile_name()
            self.data["clickerProfiles"] = [remaining]
            return self.set_active_clicker_profile(remaining["id"])

        self.data["clickerProfiles"] = [profile for profile in profiles if profile.get("id") != profile_id]
        if not self.data["clickerProfiles"]:
            self.data["clickerProfiles"] = [self._default_clicker_profile()]
        default_target = self.data["clickerProfiles"][0]["id"]
        return self.set_active_clicker_profile(default_target)

    def clear_clicker_profiles(self) -> Dict[str, Any]:
        """Reset saved clicker profiles to a single default profile."""
        profile = self._default_clicker_profile()
        self.data["clickerProfiles"] = [profile]
        self.data["activeClickerProfileId"] = profile["id"]
        return deep_copy(profile)

    def _generate_profile_name(self) -> str:
        """Generate a readable default profile name."""
        existing_names = {str(profile.get("name", "")) for profile in self.data.get("clickerProfiles", [])}
        base = self._new_profile_base_name()
        index = 1
        while True:
            candidate = f"{base} {index}"
            if candidate not in existing_names:
                return candidate
            index += 1

    def save(self) -> bool:
        """Save settings to file. Returns True if successful."""
        try:
            self.last_error = ""
            payload = deep_copy(self.data)
            payload.pop("clickerActiveProfile", None)
            payload.pop("clicker", None)
            with open(CONFIG_PATH, "w", encoding="utf-8") as file:
                json.dump(payload, file, ensure_ascii=False, indent=2)
            return True
        except Exception as exc:
            self.last_error = str(exc)
            log_exception("Failed to save settings", exc)
            return False
