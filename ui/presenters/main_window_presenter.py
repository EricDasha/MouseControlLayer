"""
Presentation helpers for main-window status and summary text.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple

from win_api import format_hotkey_display


def resolve_clicker_preset(interval_ms: int, clicker_presets: Dict[str, Any]) -> str:
    """Resolve the current interval to a preset key when possible."""
    normalized = max(1, int(interval_ms))
    for preset_key, preset_interval in clicker_presets.items():
        if preset_interval == normalized:
            return preset_key
    return "custom"


def describe_clicker_preset(i18n, preset_key: str) -> str:
    """Return a short descriptive label for the clicker preset."""
    if preset_key == "efficient":
        return i18n.t("clicker.preset.desc.efficient", "100 ms per click (10 clicks/sec)")
    if preset_key == "extreme":
        return i18n.t("clicker.preset.desc.extreme", "10 ms per click (100 clicks/sec)")
    return i18n.t("clicker.preset.desc.custom", "Manually set the click interval")


def describe_clicker_swap_source(i18n, triggers: Dict[str, Any]) -> str:
    """Return a readable label for the configured swap source, or empty when off."""
    mode = str(triggers.get("swapMode", "off") or "off")
    if mode == "key":
        key_display = format_hotkey_display(triggers.get("swapKey", {}))
        if not key_display or key_display == "?":
            return ""
        return key_display
    if mode == "mouseButton":
        button = str(triggers.get("swapMouseButton", "") or "")
        if not button:
            return ""
        return i18n.t(f"clicker.mouse.{button}", button)
    return ""


def build_status_badge_presentation(
    i18n,
    *,
    locked: bool,
    is_force_lock: bool,
    auto_lock_suspended: bool,
    window_specific: Dict[str, Any],
) -> Tuple[str, str]:
    """Build status badge text and stylesheet."""
    if locked:
        text = (
            i18n.t("status.locked.manual", "LOCKED (Manual)")
            if is_force_lock
            else i18n.t("status.locked.auto", "LOCKED (Auto)")
        )
        style = """
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #1e5631, stop:1 #2d7a4a);
            color: #c8facc;
            border: 1px solid #2d7a4a;
            border-radius: 14px;
            font-weight: 600;
            font-size: 16px;
            padding: 4px;
        """
        return text, style

    is_auto_enabled = window_specific.get("enabled", False) and window_specific.get("autoLockOnWindowFocus", False)
    if is_auto_enabled and not auto_lock_suspended:
        text = i18n.t("status.waiting", "WAITING (Auto-lock enabled)")
        style = """
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #8a6d3b, stop:1 #c9a961);
            color: #fff8e1;
            border: 1px solid #c9a961;
            border-radius: 14px;
            font-weight: 600;
            font-size: 16px;
            padding: 4px;
        """
        return text, style

    text = (
        i18n.t("status.unlocked.suspended", "UNLOCKED (Auto-lock paused)")
        if auto_lock_suspended
        else i18n.t("status.unlocked", "UNLOCKED")
    )
    style = """
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #5c1e1e, stop:1 #8a2929);
        color: #ffdede;
        border: 1px solid #8a2929;
        border-radius: 14px;
        font-weight: 600;
        font-size: 16px;
        padding: 4px;
    """
    return text, style


def build_simple_info_text(
    i18n,
    *,
    settings_data: Dict[str, Any],
    clicker: Dict[str, Any],
    clicker_running: bool,
    clicker_presets: Dict[str, Any],
    clicker_trigger_modes: Dict[str, str],
) -> Tuple[str, str]:
    """Build the simple-page configuration and hotkey text."""
    rec = settings_data.get("recenter", {})
    pos = settings_data.get("position", {})
    ws = settings_data.get("windowSpecific", {})
    hotkeys = settings_data.get("hotkeys", {})

    config_parts = []
    mode = pos.get("mode", "virtualCenter")
    if mode == "primaryCenter":
        pos_text = i18n.t("position.primaryCenter", "Primary screen center")
    elif mode == "custom":
        pos_text = f"{i18n.t('position.custom', 'Custom')} ({pos.get('customX', 0)}, {pos.get('customY', 0)})"
    else:
        pos_text = i18n.t("position.virtualCenter", "Virtual screen center")
    config_parts.append(f"{i18n.t('simple.position', 'Position')}: {pos_text}")

    rec_enabled = bool(rec.get("enabled", True))
    rec_status = i18n.t("simple.enabled", "Enabled") if rec_enabled else i18n.t("simple.disabled", "Disabled")
    rec_text = f"{i18n.t('simple.recenter', 'Auto-Recenter')}: {rec_status}"
    if rec_enabled:
        rec_text += f" ({int(rec.get('intervalMs', 250))}ms)"
    config_parts.append(rec_text)

    ws_enabled = bool(ws.get("enabled", False))
    ws_status = i18n.t("simple.enabled", "Enabled") if ws_enabled else i18n.t("simple.disabled", "Disabled")
    ws_text = f"{i18n.t('simple.window', 'Window Lock')}: {ws_status}"
    if ws_enabled:
        targets = ws.get("targetWindows", [])
        auto_focus = bool(ws.get("autoLockOnWindowFocus", False))
        if targets:
            if len(targets) == 1:
                ws_text += f"\n  Target: {targets[0]}"
            else:
                ws_text += f"\n  Target: {i18n.t('simple.window.count', '{0} windows').format(len(targets))}"
        if auto_focus:
            ws_text += f" ({i18n.t('window.specific.autoLock', 'Auto')})"
        if auto_focus and bool(ws.get("resumeAfterWindowSwitch", False)):
            ws_text += f"\n  {i18n.t('window.specific.resumeAfterSwitch', 'Auto re-lock after window switch')}"
    config_parts.append(ws_text)

    clicker_enabled = bool(clicker.get("enabled", False))
    clicker_status = i18n.t("simple.enabled", "Enabled") if clicker_enabled else i18n.t("simple.disabled", "Disabled")
    clicker_runtime = i18n.t("simple.on", "On") if clicker_running else i18n.t("simple.off", "Off")
    button_name = clicker.get("button", "left")
    if button_name == "right":
        button_key = "clicker.button.right"
    elif button_name == "middle":
        button_key = "clicker.button.middle"
    else:
        button_key = "clicker.button.left"
    preset_key = clicker.get("preset", resolve_clicker_preset(clicker.get("intervalMs", 100), clicker_presets))
    preset_label_key = f"clicker.preset.{preset_key}" if preset_key in clicker_presets else "clicker.preset.custom"
    clicker_text = (
        f"{i18n.t('simple.clicker', 'Auto Clicker')}: {clicker_status}"
        f" ({i18n.t('clicker.runtime', 'Running')}: {clicker_runtime})"
    )
    if clicker_enabled:
        trigger_mode = clicker.get("triggers", {}).get("mode", "toggle")
        clicker_text += (
            f"\n  {i18n.t(button_key, 'Left Click')} | "
            f"{i18n.t(preset_label_key, 'Custom')} @ {int(clicker.get('intervalMs', 100))}ms | "
            f"{i18n.t(clicker_trigger_modes.get(trigger_mode, ''), trigger_mode)}"
        )
        swap_source = describe_clicker_swap_source(i18n, clicker.get("triggers", {}))
        if swap_source:
            clicker_text += f"\n  {i18n.t('simple.swap', 'Swap Button')}: {swap_source}"
    config_parts.append(clicker_text)

    hotkey_parts = []
    hotkey_parts.append(f"{i18n.t('hotkey.lock', 'Lock')}: {format_hotkey_display(hotkeys.get('lock', {}))}")
    hotkey_parts.append(f"{i18n.t('hotkey.unlock', 'Unlock')}: {format_hotkey_display(hotkeys.get('unlock', {}))}")
    hotkey_parts.append(f"{i18n.t('hotkey.toggle', 'Toggle')}: {format_hotkey_display(hotkeys.get('toggle', {}))}")
    triggers = clicker.get("triggers", {})
    trigger_mode = triggers.get("mode", "toggle")
    if trigger_mode == "toggle":
        trigger_text = format_hotkey_display(triggers.get("toggleHotkey", {}))
    elif trigger_mode == "holdKey":
        trigger_text = format_hotkey_display(triggers.get("holdKey", {}))
    else:
        trigger_text = i18n.t(
            f"clicker.mouse.{triggers.get('holdMouseButton', 'middle')}",
            triggers.get("holdMouseButton", "middle"),
        )
    hotkey_parts.append(
        f"{i18n.t('clicker.trigger.mode', 'Trigger Mode')}: "
        f"{i18n.t(clicker_trigger_modes.get(trigger_mode, ''), trigger_mode)}"
    )
    hotkey_parts.append(f"{i18n.t('clicker.hotkey', 'Auto Clicker Toggle')}: {trigger_text}")

    return "\n".join(config_parts), "\n".join(hotkey_parts)


def build_toggle_button_text(i18n, *, locked: bool, hotkeys: Dict[str, Any]) -> str:
    """Build the lock toggle button text."""
    if locked:
        text = i18n.t("btn.unlock", "Unlock")
        keys = f"({format_hotkey_display(hotkeys['unlock'])} / {format_hotkey_display(hotkeys['toggle'])})"
    else:
        text = i18n.t("btn.lock", "Lock to center")
        keys = f"({format_hotkey_display(hotkeys['lock'])} / {format_hotkey_display(hotkeys['toggle'])})"
    return f"{text} {keys}"


def build_clicker_button_presentation(i18n, *, clicker: Dict[str, Any], clicker_running: bool) -> Tuple[str, bool]:
    """Build the clicker button text and enabled state."""
    triggers = clicker.get("triggers", {})
    mode = triggers.get("mode", "toggle")
    if mode == "toggle":
        hotkey = format_hotkey_display(triggers.get("toggleHotkey", {}))
    elif mode == "holdKey":
        hotkey = format_hotkey_display(triggers.get("holdKey", {}))
    else:
        hotkey = i18n.t(
            f"clicker.mouse.{triggers.get('holdMouseButton', 'middle')}",
            triggers.get("holdMouseButton", "middle"),
        )

    text = (
        i18n.t("btn.clicker.stop", "Stop Auto Clicker")
        if clicker_running
        else i18n.t("btn.clicker.start", "Start Auto Clicker")
    )
    if hotkey and hotkey != "?":
        text = f"{text} ({hotkey})"
    return text, bool(clicker.get("enabled", False))
