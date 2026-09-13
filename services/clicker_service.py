"""
Clicker runtime service for MCL.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Dict, Optional, Set

from PySide6 import QtCore

from win_api import (
    GlobalInputListener,
    get_active_window_info,
    get_window_process_name,
    key_to_vk,
    user32,
)
from services.macro_runtime import MacroActionExecutor
from services.sound_service import SoundPlayer


class ClickerService(QtCore.QObject):
    """Own the auto-clicker runtime, timers, and hold-trigger polling."""

    AUTO_HOLD_MIN_MS = 8
    AUTO_HOLD_MAX_MS = 50

    inputEvent = QtCore.Signal(str, str, bool)

    def __init__(
        self,
        *,
        get_profile: Callable[[], Dict[str, Any]],
        on_state_changed: Callable[[], None],
        on_notify_started: Callable[[Dict[str, Any]], None],
        on_notify_stopped: Callable[[Dict[str, Any]], None],
        input_service=None,
        click_mouse_func: Optional[Callable[[str], None]] = None,
        input_listener_factory: Callable[..., GlobalInputListener] = GlobalInputListener,
        parent=None,
    ):
        super().__init__(parent)
        self._get_profile = get_profile
        self._on_state_changed = on_state_changed
        self._on_notify_started = on_notify_started
        self._on_notify_stopped = on_notify_stopped
        self._running = False
        self._hold_trigger_pressed = False
        self._swap_active = False
        self._pressed_keys: Set[str] = set()
        self._pressed_mouse_buttons: Set[str] = set()
        self._action_executor = MacroActionExecutor(
            input_service=input_service,
            click_mouse_func=click_mouse_func,
        )
        self._sound_player = SoundPlayer(self)

        self.clicker_timer = QtCore.QTimer(self)
        self.clicker_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.clicker_timer.timeout.connect(self._on_clicker_tick)

        self._click_button_down: Optional[str] = None
        self.click_release_timer = QtCore.QTimer(self)
        self.click_release_timer.setSingleShot(True)
        self.click_release_timer.setTimerType(QtCore.Qt.TimerType.PreciseTimer)
        self.click_release_timer.timeout.connect(self._release_click_button)

        self._input_listener = input_listener_factory(
            on_key_event=self._emit_key_event,
            on_mouse_event=self._emit_mouse_event,
        )
        self.inputEvent.connect(self._on_global_input_event)

        self.hold_state_timer = QtCore.QTimer(self)
        self.hold_state_timer.timeout.connect(self._poll_hold_trigger_state)
        self._hook_mode_active = False
        self._sync_hold_detection_mode(self._get_profile())

    @property
    def is_running(self) -> bool:
        """Return whether the clicker is currently running."""
        return self._running

    @property
    def is_swapped(self) -> bool:
        """Return whether the swap source is currently held."""
        return self._swap_active

    def play_sound_preview(self, sound_config: Dict[str, Any]) -> None:
        """Preview a sound selection."""
        self._sound_player.play_event(sound_config)

    def sync_runtime(self) -> None:
        """Apply the current settings to runtime timers."""
        profile = self._get_profile()
        self._sync_hold_detection_mode(profile)
        if not profile.get("enabled", False):
            self.stop(show_message=False)
            return
        self._evaluate_hold_trigger_state(profile, fallback_allowed=not self._hook_mode_active)
        self._apply_clicker_timer()
        self._on_state_changed()

    def start(self, show_message: bool = True, immediate_click: bool = False) -> None:
        """Start the auto clicker."""
        profile = self._get_profile()
        if self._running or not profile.get("enabled", False) or self._is_active_process_blocked(profile):
            return

        self._running = True
        if immediate_click:
            self._click_once(profile)
        self._apply_clicker_timer()
        self._sound_player.play_event(profile.get("sound", {}).get("start", {}))
        self._on_state_changed()
        if show_message:
            self._on_notify_started(profile)

    def stop(self, show_message: bool = True) -> None:
        """Stop the auto clicker."""
        if not self._running:
            self._release_click_button()
            return

        self._running = False
        self._apply_clicker_timer()
        self._release_click_button()
        self._sound_player.play_event(self._get_profile().get("sound", {}).get("stop", {}))
        self._on_state_changed()
        if show_message:
            self._on_notify_stopped(self._get_profile())

    def toggle(self) -> None:
        """Toggle the auto clicker."""
        profile = self._get_profile()
        if profile.get("triggers", {}).get("mode") != "toggle":
            if not self._running:
                self.start(immediate_click=True)
            else:
                self.stop()
            return
        if self._running:
            self.stop()
        else:
            self.start()

    def _apply_clicker_timer(self) -> None:
        """Start or stop the clicker timer based on state and settings."""
        profile = self._get_profile()
        if self._running and profile.get("enabled", False):
            interval = max(1, int(profile.get("intervalMs", 100)))
            if self.clicker_timer.interval() != interval or not self.clicker_timer.isActive():
                self.clicker_timer.start(interval)
        else:
            self.clicker_timer.stop()

    def _check_process_match(self, process: str, targets: list[str]) -> bool:
        """Check whether a process name matches any configured target."""
        process_lower = (process or "").lower()
        process_stem = Path(process_lower).stem
        for target in targets:
            target_lower = str(target or "").strip().lower()
            if not target_lower:
                continue
            target_stem = Path(target_lower).stem
            if target_lower in (process_lower, process_stem):
                return True
            if target_stem and target_stem in (process_lower, process_stem):
                return True
            if target_lower in process_lower or (process_stem and target_lower in process_stem):
                return True
        return False

    def _is_active_process_blocked(self, profile: Dict[str, Any]) -> bool:
        """Return whether the foreground process is blacklisted for this profile."""
        blacklist = profile.get("processBlacklist", [])
        if not blacklist:
            return False
        hwnd, _title = get_active_window_info()
        process = get_window_process_name(hwnd) if hwnd else ""
        return self._check_process_match(process or "", blacklist)

    def _configured_click_button(self, profile: Dict[str, Any]) -> str:
        """Return the button configured for this profile."""
        return str(profile.get("button", "left") or "left").lower()

    def _effective_click_button(self, profile: Dict[str, Any]) -> str:
        """Return the button to click, swapping left/right while swap is held."""
        button = self._configured_click_button(profile)
        if not self._swap_active:
            return button
        return {"left": "right", "right": "left"}.get(button, button)

    def _swap_mode(self, profile: Dict[str, Any]) -> str:
        """Return the normalized swap source mode for this profile."""
        mode = str(profile.get("triggers", {}).get("swapMode", "off") or "off").strip()
        return mode if mode in ("off", "key", "mouseButton") else "off"

    def _swap_configured(self, profile: Dict[str, Any]) -> bool:
        """Return whether this profile has a usable swap source."""
        triggers = profile.get("triggers", {})
        mode = self._swap_mode(profile)
        if mode == "key":
            return bool(str(triggers.get("swapKey", {}).get("key", "") or "").strip())
        if mode == "mouseButton":
            return bool(str(triggers.get("swapMouseButton", "") or "").strip())
        return False

    def _swap_source_pressed(self, profile: Dict[str, Any], *, fallback_allowed: bool) -> bool:
        """Return whether the configured swap source is currently held."""
        triggers = profile.get("triggers", {})
        mode = self._swap_mode(profile)
        if mode == "key":
            swap_key = triggers.get("swapKey", {})
            if self._hook_mode_active:
                return self._hold_hotkey_matches_events(swap_key)
            if fallback_allowed:
                return self._hold_hotkey_matches(swap_key)
            return self._swap_active
        if mode == "mouseButton":
            button = str(triggers.get("swapMouseButton", "") or "").lower()
            if not button:
                return False
            if self._hook_mode_active:
                return button in self._pressed_mouse_buttons
            if fallback_allowed:
                return self._mouse_button_pressed(button)
            return self._swap_active
        return False

    def _update_swap_state(self, profile: Dict[str, Any], *, fallback_allowed: bool) -> None:
        """Refresh the cached swap state used by the click timer."""
        self._swap_active = self._swap_source_pressed(profile, fallback_allowed=fallback_allowed)

    def _click_once(self, profile: Dict[str, Any]) -> None:
        """Click once unless the active process is blacklisted."""
        if self._is_active_process_blocked(profile):
            if self._running:
                self.stop(show_message=False)
            return
        self._update_swap_state(profile, fallback_allowed=not self._hook_mode_active)
        button = self._effective_click_button(profile)
        configured_hold_ms = profile.get("clickHoldMs")
        if configured_hold_ms is None:
            # Compatibility for callers that inject the legacy click function.
            self._action_executor.click_mouse(button)
            return
        if self._click_button_down is not None:
            return
        effective_hold_ms = self._effective_click_hold_ms(profile)
        self._action_executor.mouse_down(button)
        self._click_button_down = button
        self.click_release_timer.start(effective_hold_ms)

    def _effective_click_hold_ms(self, profile: Dict[str, Any]) -> int:
        """Resolve the DOWN width; auto mode uses half of the click period."""
        try:
            configured_hold_ms = max(0, min(1000, int(profile.get("clickHoldMs", 0) or 0)))
        except Exception:
            configured_hold_ms = 0
        if configured_hold_ms > 0:
            return configured_hold_ms
        try:
            interval_ms = max(1, int(profile.get("intervalMs", 100) or 100))
        except Exception:
            interval_ms = 100
        return max(
            self.AUTO_HOLD_MIN_MS,
            min(self.AUTO_HOLD_MAX_MS, interval_ms // 2),
        )

    def _release_click_button(self) -> None:
        """Release a pending click pulse, including stop/profile-change paths."""
        if self.click_release_timer.isActive():
            self.click_release_timer.stop()
        button = self._click_button_down
        self._click_button_down = None
        if button:
            self._action_executor.mouse_up(button)

    def _modifier_pressed(self, vk: int) -> bool:
        """Return whether a modifier virtual key is currently pressed."""
        return bool(user32.GetAsyncKeyState(vk) & 0x8000)

    def _hold_hotkey_matches(self, hold_key: Dict[str, Any]) -> bool:
        """Check whether the configured hold hotkey is currently pressed."""
        vk = key_to_vk(hold_key.get("key", ""))
        if vk is None or not self._modifier_pressed(vk):
            return False

        modifier_map = [
            ("modCtrl", 0x11),
            ("modAlt", 0x12),
            ("modShift", 0x10),
            ("modWin", 0x5B),
        ]
        for flag_name, modifier_vk in modifier_map:
            expected = bool(hold_key.get(flag_name, False))
            pressed = self._modifier_pressed(modifier_vk)
            if expected != pressed:
                return False
        return True

    def _mouse_button_pressed(self, button_name: str) -> bool:
        """Return whether a mouse button is currently pressed."""
        vk_map = {
            "left": 0x01,
            "right": 0x02,
            "middle": 0x04,
            "x1": 0x05,
            "x2": 0x06,
        }
        vk = vk_map.get((button_name or "").lower())
        return bool(vk and self._modifier_pressed(vk))

    def _poll_hold_trigger_state(self) -> None:
        """Poll keyboard/mouse hold state so hold triggers work without low-level hooks."""
        profile = self._get_profile()
        self._evaluate_hold_trigger_state(profile, fallback_allowed=True)

    def _emit_key_event(self, key_name: str, is_pressed: bool) -> None:
        """Bridge low-level key events into the Qt thread."""
        if not self._input_detection_required(self._get_profile()):
            return
        self.inputEvent.emit("key", key_name, is_pressed)

    def _emit_mouse_event(self, button_name: str, is_pressed: bool) -> None:
        """Bridge low-level mouse events into the Qt thread."""
        if not self._input_detection_required(self._get_profile()):
            return
        self.inputEvent.emit("mouse", button_name, is_pressed)

    def _on_global_input_event(self, event_type: str, name: str, is_pressed: bool) -> None:
        """Update pressed-state tracking from low-level input events."""
        normalized = str(name or "").strip()
        if not normalized:
            return

        if event_type == "key":
            target_set = self._pressed_keys
            normalized = normalized.lower()
        else:
            target_set = self._pressed_mouse_buttons
            normalized = normalized.lower()

        if is_pressed:
            target_set.add(normalized)
        else:
            target_set.discard(normalized)

        if self._hook_mode_active:
            self._evaluate_hold_trigger_state(self._get_profile(), fallback_allowed=False)

    def _input_detection_required(self, profile: Dict[str, Any]) -> bool:
        """Return whether this profile needs low-level input detection.

        Hold triggers and the button-swap source both rely on the same
        keyboard/mouse state tracking.
        """
        if not profile.get("enabled", False):
            return False
        if self._swap_configured(profile):
            return True
        mode = profile.get("triggers", {}).get("mode")
        return mode in ("holdKey", "holdMouseButton")

    def _sync_hold_detection_mode(self, profile: Dict[str, Any]) -> None:
        """Enable the polling fallback only when hook mode is unavailable."""
        detection_mode = self._input_detection_required(profile)

        if detection_mode and not self._hook_mode_active:
            self._hook_mode_active = self._input_listener.start()
            if not self._hook_mode_active:
                self._input_listener.stop()

        if not detection_mode:
            self._input_listener.stop()
            self._hook_mode_active = False

        if self._hook_mode_active:
            if self.hold_state_timer.isActive():
                self.hold_state_timer.stop()
        else:
            if detection_mode:
                if not self.hold_state_timer.isActive():
                    self.hold_state_timer.start(12)
            elif self.hold_state_timer.isActive():
                self.hold_state_timer.stop()
        if not detection_mode:
            self._pressed_keys.clear()
            self._pressed_mouse_buttons.clear()
            self._swap_active = False

    def _modifier_name_map(self) -> Dict[str, str]:
        """Map config modifier flags to tracked key names."""
        return {
            "modCtrl": "ctrl",
            "modAlt": "alt",
            "modShift": "shift",
            "modWin": "win",
        }

    def _hold_hotkey_matches_events(self, hold_key: Dict[str, Any]) -> bool:
        """Check hold-key state using tracked low-level input events."""
        main_key = str(hold_key.get("key", "") or "").strip().lower()
        if not main_key or main_key not in self._pressed_keys:
            return False

        for flag_name, key_name in self._modifier_name_map().items():
            expected = bool(hold_key.get(flag_name, False))
            pressed = key_name in self._pressed_keys
            if expected != pressed:
                return False
        return True

    def _evaluate_hold_trigger_state(self, profile: Dict[str, Any], *, fallback_allowed: bool) -> None:
        """Start or stop the clicker based on the active hold-trigger state."""
        triggers = profile.get("triggers", {})
        if not profile.get("enabled", False):
            self._swap_active = False
            if self._hold_trigger_pressed:
                self._hold_trigger_pressed = False
                self.stop(show_message=False)
            return
        if self._is_active_process_blocked(profile):
            self._swap_active = False
            if self._hold_trigger_pressed:
                self._hold_trigger_pressed = False
            self.stop(show_message=False)
            return

        self._update_swap_state(profile, fallback_allowed=fallback_allowed)

        mode = triggers.get("mode")
        if mode == "holdKey":
            if self._hook_mode_active:
                is_pressed = self._hold_hotkey_matches_events(triggers.get("holdKey", {}))
            elif fallback_allowed:
                is_pressed = self._hold_hotkey_matches(triggers.get("holdKey", {}))
            else:
                return
        elif mode == "holdMouseButton":
            if self._hook_mode_active:
                is_pressed = str(triggers.get("holdMouseButton", "middle") or "middle").lower() in self._pressed_mouse_buttons
            elif fallback_allowed:
                is_pressed = self._mouse_button_pressed(triggers.get("holdMouseButton", "middle"))
            else:
                return
        else:
            if self._hold_trigger_pressed:
                self._hold_trigger_pressed = False
                self.stop(show_message=False)
            return

        if is_pressed and not self._hold_trigger_pressed:
            self._hold_trigger_pressed = True
            self.start(show_message=False, immediate_click=True)
        elif not is_pressed and self._hold_trigger_pressed:
            self._hold_trigger_pressed = False
            self.stop(show_message=False)

    def _on_clicker_tick(self) -> None:
        """Perform a click on each timer tick."""
        if not self._running:
            return
        profile = self._get_profile()
        if not profile.get("enabled", False):
            self.stop(show_message=False)
            return
        self._click_once(profile)
