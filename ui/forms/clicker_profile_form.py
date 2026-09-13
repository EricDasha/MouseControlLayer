"""
Helpers for mapping clicker profile data to and from the UI form.
"""
from __future__ import annotations

from typing import Any, Dict


PROFILE_FEATURE_KEYS = (
    "recenter",
    "position",
    "windowSpecific",
    "mouseMacros",
    "inputBackend",
    "inputMode",
    "fallbackBackend",
    "fallbackPolicy",
)


def _collect_list_widget_items(widget) -> list[str]:
    """Collect text entries from a QListWidget-like object."""
    return [widget.item(i).text() for i in range(widget.count())]


def collect_clicker_profile_form_data(window) -> Dict[str, Any]:
    """Build a clicker profile dict from the current form controls."""
    active = window._get_active_clicker_profile()
    profile_id = window._selected_profile_id or active.get("id", "default")
    profile_name = window.clickerProfileNameEdit.text().strip() or active.get("name", "默认方案")
    preset = window.clickerPresetCombo.currentData() or "custom"
    interval_ms = window.clickerIntervalSpin.value()
    click_hold_ms = (
        window.clickerHoldMsSpin.value()
        if hasattr(window, "clickerHoldMsSpin")
        else int(active.get("clickHoldMs", 0) or 0)
    )
    feature_settings: Dict[str, Any] = {}
    if hasattr(window, "_current_general_settings_form_data"):
        general_settings = window._current_general_settings_form_data()
        feature_settings = {
            key: general_settings[key]
            for key in PROFILE_FEATURE_KEYS
            if key in general_settings
        }
    return {
        "id": profile_id,
        "name": profile_name,
        "enabled": window.clickerEnabledCheck.isChecked(),
        "button": window.clickerButtonCombo.currentData(),
        "inputBackend": window.clickerInputBackendCombo.currentData() if hasattr(window, "clickerInputBackendCombo") else active.get("inputBackend", "auto"),
        "preset": preset,
        "intervalMs": interval_ms,
        "clickHoldMs": click_hold_ms,
        "sound": {
            "start": {
                "enabled": window.clickerSoundEnabledCheck.isChecked(),
                "preset": window.clickerSoundPresetCombo.currentData() or "systemAsterisk",
                "customFile": window.clickerCustomSoundPathEdit.text().strip(),
            },
            "stop": {
                "enabled": window.clickerStopSoundEnabledCheck.isChecked() if hasattr(window, "clickerStopSoundEnabledCheck") else False,
                "preset": window.clickerStopSoundPresetCombo.currentData() if hasattr(window, "clickerStopSoundPresetCombo") else "systemHand",
                "customFile": window.clickerStopCustomSoundPathEdit.text().strip() if hasattr(window, "clickerStopCustomSoundPathEdit") else "",
            },
        },
"processBlacklist": _collect_list_widget_items(window.clickerProcessBlacklist),
        "triggers": {
            "mode": window.clickerTriggerModeCombo.currentData() or "toggle",
            "toggleHotkey": window.clickerToggleHotkeyCapture.get_hotkey(),
            "holdKey": window.clickerHoldKeyCapture.get_hotkey(),
            "holdMouseButton": window.clickerHoldMouseCombo.currentData() or "middle",
            "swapMode": window.clickerSwapModeCombo.currentData() or "off",
            "swapKey": window.clickerSwapKeyCapture.get_hotkey(),
            "swapMouseButton": window.clickerSwapMouseCombo.currentData() or "x1",
        },
        "featureSettings": feature_settings,
    }


def load_clicker_profile_into_form(window, profile: Dict[str, Any]) -> None:
    """Populate clicker controls from a profile dict."""
    window._begin_form_update()
    try:
        window._selected_profile_id = profile.get("id", "default")
        window.clickerProfileNameEdit.setText(profile.get("name", "默认方案"))
        window.clickerEnabledCheck.setChecked(profile.get("enabled", False))

        for i in range(window.clickerButtonCombo.count()):
            if window.clickerButtonCombo.itemData(i) == profile.get("button", "left"):
                window.clickerButtonCombo.setCurrentIndex(i)
                break
        if hasattr(window, "clickerInputBackendCombo"):
            backend = profile.get("inputBackend", "auto")
            backend = {"sendinput": "native-sendinput", "native-scancode": "native-sendinput", "python-fallback": "python-sendinput"}.get(backend, backend)
            for i in range(window.clickerInputBackendCombo.count()):
                if window.clickerInputBackendCombo.itemData(i) == backend:
                    window.clickerInputBackendCombo.setCurrentIndex(i)
                    break

        preset = profile.get("preset", window._get_clicker_preset_for_interval(profile.get("intervalMs", 100)))
        for i in range(window.clickerPresetCombo.count()):
            if window.clickerPresetCombo.itemData(i) == preset:
                window.clickerPresetCombo.setCurrentIndex(i)
                break
        window.clickerIntervalSpin.setValue(int(profile.get("intervalMs", 100)))
        if hasattr(window, "clickerHoldMsSpin"):
            window.clickerHoldMsSpin.setValue(int(profile.get("clickHoldMs", 0) or 0))

        triggers = profile.get("triggers", {})
        for i in range(window.clickerTriggerModeCombo.count()):
            if window.clickerTriggerModeCombo.itemData(i) == triggers.get("mode", "toggle"):
                window.clickerTriggerModeCombo.setCurrentIndex(i)
                break
        window.clickerToggleHotkeyCapture.set_hotkey(
            triggers.get("toggleHotkey", window.settings.DEFAULT_CLICKER_HOTKEY)
        )
        window.clickerHoldKeyCapture.set_hotkey(
            triggers.get("holdKey", window.settings.DEFAULT_HOLD_KEY)
        )
        for i in range(window.clickerHoldMouseCombo.count()):
            if window.clickerHoldMouseCombo.itemData(i) == triggers.get("holdMouseButton", "middle"):
                window.clickerHoldMouseCombo.setCurrentIndex(i)
                break

        for i in range(window.clickerSwapModeCombo.count()):
            if window.clickerSwapModeCombo.itemData(i) == triggers.get("swapMode", "off"):
                window.clickerSwapModeCombo.setCurrentIndex(i)
                break
        window.clickerSwapKeyCapture.set_hotkey(
            triggers.get("swapKey", window.settings.DEFAULT_SWAP_KEY)
        )
        for i in range(window.clickerSwapMouseCombo.count()):
            if window.clickerSwapMouseCombo.itemData(i) == triggers.get("swapMouseButton", "x1"):
                window.clickerSwapMouseCombo.setCurrentIndex(i)
                break

        sound = profile.get("sound", {})
        start_sound = sound.get("start", sound) if isinstance(sound, dict) else {}
        stop_sound = sound.get("stop", {}) if isinstance(sound, dict) else {}
        window.clickerSoundEnabledCheck.setChecked(start_sound.get("enabled", False))
        for i in range(window.clickerSoundPresetCombo.count()):
            if window.clickerSoundPresetCombo.itemData(i) == start_sound.get("preset", "systemAsterisk"):
                window.clickerSoundPresetCombo.setCurrentIndex(i)
                break
        window.clickerCustomSoundPathEdit.setText(start_sound.get("customFile", ""))
        if hasattr(window, "clickerStopSoundEnabledCheck"):
            window.clickerStopSoundEnabledCheck.setChecked(stop_sound.get("enabled", False))
            for i in range(window.clickerStopSoundPresetCombo.count()):
                if window.clickerStopSoundPresetCombo.itemData(i) == stop_sound.get("preset", "systemHand"):
                    window.clickerStopSoundPresetCombo.setCurrentIndex(i)
                    break
            window.clickerStopCustomSoundPathEdit.setText(stop_sound.get("customFile", ""))
        window.clickerProcessBlacklist.clear()
        for process_name in profile.get("processBlacklist", []):
            window.clickerProcessBlacklist.addItem(process_name)
        window._sync_clicker_interval_controls()
        window._sync_clicker_trigger_controls()
        window._sync_clicker_sound_controls()
        window._profile_dirty = False
    finally:
        window._end_form_update()
