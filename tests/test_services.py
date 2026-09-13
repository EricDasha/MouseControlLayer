import os
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6 import QtCore, QtWidgets

from services.clicker_service import ClickerService
from services.input_backends import get_backend_status, all_backend_statuses
from services.input_service import InputService
from services.lock_service import LockService
from services.macro_schema import normalize_macro_trigger_mode, normalize_mouse_button
from services.macro_service import MouseMacroService
from services.tray_service import TrayService


class _FakeInputListener:
    def __init__(self, **_kwargs):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True
        return True

    def stop(self):
        self.stopped = True


class _FakeInputService:
    def __init__(self):
        self.clicks = []
        self.keys = []
        self.hotkeys = []
        self.texts = []
        self.key_downs = []
        self.key_ups = []
        self.moves = []
        self.scrolls = []

    def click_mouse(self, button="left"):
        self.clicks.append(button)

    def mouse_click(self, button="left", hold_ms=0):
        if int(hold_ms or 0) > 0:
            self.mouse_down(button)
            self.mouse_up(button)
            return
        self.click_mouse(button)

    def mouse_down(self, button="left"):
        self.clicks.append(f"{button}:down")

    def mouse_up(self, button="left"):
        self.clicks.append(f"{button}:up")

    def mouse_move(self, x, y):
        self.moves.append((x, y))

    def mouse_move_relative(self, dx, dy):
        self.moves.append(("relative", dx, dy))

    def mouse_scroll(self, *, dx=0, dy=0):
        self.scrolls.append((dx, dy))

    def press_key(self, key):
        self.keys.append(key)

    def key_down(self, key):
        self.key_downs.append(key)

    def key_up(self, key):
        self.key_ups.append(key)

    def press_hotkey(self, action):
        self.hotkeys.append(action)

    def type_text(self, text):
        self.texts.append(text)


class ServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


    def test_input_service_prefers_rust_backend_for_sendinput_clicks(self):
        service = InputService(get_backend=lambda: "sendinput")

        with mock.patch("services.input_service.native_input.mouse_down", return_value=True) as native_down, \
             mock.patch("services.input_service.native_input.mouse_up", return_value=True) as native_up, \
             mock.patch("services.input_service.sendinput_mouse_down") as python_down, \
             mock.patch("services.input_service.sendinput_mouse_up") as python_up, \
             mock.patch("services.input_service.time.sleep"):
            service.click_mouse("right")

        native_down.assert_called_once_with("right")
        native_up.assert_called_once_with("right")
        python_down.assert_not_called()
        python_up.assert_not_called()

    def test_input_service_falls_back_when_rust_backend_unavailable(self):
        service = InputService(get_backend=lambda: "native-sendinput")

        with mock.patch("services.input_service.native_input.press_vk", return_value=False) as native_press, \
             mock.patch("services.input_service.key_to_vk", return_value=0x41), \
             mock.patch("services.input_service.sendinput_press_vk") as python_press:
            service.press_key("A")

        native_press.assert_called_once_with(0x41)
        python_press.assert_called_once_with(0x41)

    def test_input_service_key_down_up_use_native_then_python_fallback(self):
        service = InputService(get_backend=lambda: "native-sendinput")

        with mock.patch("services.input_service.key_to_vk", return_value=0x32), \
             mock.patch("services.input_service.native_input.key_down_vk", return_value=True) as native_down, \
             mock.patch("services.input_service.native_input.key_up_vk", return_value=False) as native_up, \
             mock.patch("services.input_service.key_down_vk") as python_down, \
             mock.patch("services.input_service.key_up_vk") as python_up:
            service.key_down("2")
            service.key_up("2")

        native_down.assert_called_once_with(0x32)
        native_up.assert_called_once_with(0x32)
        python_down.assert_not_called()
        python_up.assert_called_once_with(0x32)

    def test_input_service_mouse_down_up_use_native_then_python_fallback(self):
        service = InputService(get_backend=lambda: "native-sendinput")

        with mock.patch("services.input_service.native_input.mouse_down", return_value=True) as native_down, \
             mock.patch("services.input_service.native_input.mouse_up", return_value=False) as native_up, \
             mock.patch("services.input_service.sendinput_mouse_down") as python_down, \
             mock.patch("services.input_service.sendinput_mouse_up") as python_up:
            service.mouse_down("left")
            service.mouse_up("left")

        native_down.assert_called_once_with("left")
        native_up.assert_called_once_with("left")
        python_down.assert_not_called()
        python_up.assert_called_once_with("left")

    def test_input_service_mouse_click_can_hold_before_release(self):
        service = InputService(get_backend=lambda: "python-sendinput")

        with mock.patch.object(service, "mouse_down") as mouse_down, \
             mock.patch.object(service, "mouse_up") as mouse_up, \
             mock.patch("services.input_service.time.sleep") as sleep:
            service.mouse_click("left", hold_ms=12)

        mouse_down.assert_called_once_with("left")
        sleep.assert_called_once_with(0.012)
        mouse_up.assert_called_once_with("left")

    def test_input_service_mouse_click_zero_uses_compatibility_hold(self):
        service = InputService(get_backend=lambda: "native-sendinput")

        with mock.patch.object(service, "mouse_down") as mouse_down, \
             mock.patch.object(service, "mouse_up") as mouse_up, \
             mock.patch("services.input_service.time.sleep") as sleep:
            service.mouse_click("left", hold_ms=0)

        mouse_down.assert_called_once_with("left")
        sleep.assert_called_once_with(0.02)
        mouse_up.assert_called_once_with("left")

    def test_clicker_auto_hold_uses_half_of_100ms_period(self):
        profile = {"intervalMs": 100, "clickHoldMs": 0}
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            input_listener_factory=_FakeInputListener,
        )

        self.assertEqual(service._effective_click_hold_ms(profile), 50)
        self.assertEqual(service._effective_click_hold_ms({"intervalMs": 20, "clickHoldMs": 0}), 10)
        self.assertEqual(service._effective_click_hold_ms({"intervalMs": 100, "clickHoldMs": 25}), 25)

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_input_service_supports_mouse_move_and_scroll_actions(self):
        service = InputService(get_backend=lambda: "python-sendinput")

        with mock.patch("services.input_service.set_cursor_to") as set_cursor, \
             mock.patch("services.input_service.sendinput_mouse_move_relative") as move_relative, \
             mock.patch("services.input_service.sendinput_mouse_scroll") as scroll:
            service.mouse_move(100, 200)
            service.mouse_move_relative(3, -4)
            service.mouse_scroll(dx=120, dy=-240)

        set_cursor.assert_called_once_with(100, 200)
        move_relative.assert_called_once_with(3, -4)
        self.assertEqual(scroll.mock_calls, [
            mock.call(-240, horizontal=False),
            mock.call(120, horizontal=True),
        ])

    def test_macro_schema_normalizes_buttons_and_trigger_modes(self):
        self.assertEqual(normalize_mouse_button("Back"), "x1")
        self.assertEqual(normalize_mouse_button("button5"), "x2")
        self.assertEqual(normalize_mouse_button("unknown", "middle"), "middle")

        self.assertEqual(normalize_macro_trigger_mode("holdLoop"), "holdLoop")
        self.assertEqual(normalize_macro_trigger_mode("holdloop"), "holdLoop")
        self.assertEqual(normalize_macro_trigger_mode("toggle-loop"), "toggleLoop")
        self.assertEqual(normalize_macro_trigger_mode("bad", "toggle"), "toggle")

    def test_input_service_python_sendinput_skips_rust_backend(self):
        service = InputService(get_backend=lambda: "python-sendinput")

        with mock.patch("services.input_service.native_input.mouse_down", return_value=True) as native_down, \
             mock.patch("services.input_service.native_input.mouse_up", return_value=True) as native_up, \
             mock.patch("services.input_service.sendinput_mouse_down") as python_down, \
             mock.patch("services.input_service.sendinput_mouse_up") as python_up, \
             mock.patch("services.input_service.time.sleep"):
            service.click_mouse("left")

        native_down.assert_not_called()
        native_up.assert_not_called()
        python_down.assert_called_once_with("left")
        python_up.assert_called_once_with("left")

    def test_input_service_virtual_hid_reserved_falls_back_to_native_path(self):
        service = InputService(
            get_backend=lambda: "virtual-hid",
            get_fallback_backend=lambda: "native-sendinput",
            get_fallback_policy=lambda: "auto",
        )

        with mock.patch("services.input_service.native_input.mouse_down", return_value=True) as native_down, \
             mock.patch("services.input_service.native_input.mouse_up", return_value=True) as native_up, \
             mock.patch("services.input_service.time.sleep"):
            service.click_mouse("left")

        native_down.assert_called_once_with("left")
        native_up.assert_called_once_with("left")

    def test_input_service_virtual_hid_error_policy_does_not_silent_fallback(self):
        service = InputService(
            get_backend=lambda: "virtual-hid",
            get_fallback_backend=lambda: "native-sendinput",
            get_fallback_policy=lambda: "error",
        )

        with mock.patch("services.input_service.native_input.click_mouse", return_value=True) as native_click, \
             mock.patch("services.input_service.sendinput_click_mouse") as python_click:
            service.click_mouse("left")

        native_click.assert_not_called()
        python_click.assert_not_called()

    def test_input_backend_registry_reports_virtual_hid_unavailable(self):
        status = get_backend_status("virtual-hid")
        self.assertEqual(status.name, "virtual-hid")
        self.assertFalse(status.available)
        self.assertIn(status.reason, {"driver_not_installed", "unsupported_os"})
        self.assertTrue(status.capabilities.supportsKeyboard)
        self.assertIn("virtual-hid", all_backend_statuses())

    def test_input_service_prefers_rust_unicode_text(self):
        service = InputService(get_backend=lambda: "sendinput")

        with mock.patch("services.input_service.native_input.type_text", return_value=True) as native_type, \
             mock.patch("services.input_service.user32.VkKeyScanW") as vk_scan:
            service.type_text("Hello 玄")

        native_type.assert_called_once_with("Hello 玄")
        vk_scan.assert_not_called()

    def test_input_service_falls_back_text_per_character(self):
        service = InputService(get_backend=lambda: "sendinput")

        with mock.patch("services.input_service.native_input.type_text", return_value=False), \
             mock.patch("services.input_service.user32.VkKeyScanW", return_value=0x41), \
             mock.patch("services.input_service.native_input.press_vk", return_value=False), \
             mock.patch("services.input_service.sendinput_press_vk") as python_press:
            service.type_text("A")

        python_press.assert_called_once_with(0x41)


    def test_mouse_macro_service_alias_and_repeated_press_edges(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "back-left",
                    "enabled": True,
                    "holdMouseButton": "back",
                    "pressMouseButton": "left",
                    "actions": [{"type": "mouseClick", "button": "right"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        service._on_global_input_event("mouse", "x1", True)
        service._on_global_input_event("mouse", "left", True)
        service._on_global_input_event("mouse", "left", True)
        self.assertEqual(input_service.clicks, ["right"])

        service._on_global_input_event("mouse", "left", False)
        service._on_global_input_event("mouse", "left", True)
        self.assertEqual(input_service.clicks, ["right", "right"])

        service.stop()

    def test_mouse_macro_service_disabled_does_not_install_hooks_or_fire_rules(self):
        config = {
            "enabled": False,
            "source": "builder",
            "rules": [
                {
                    "enabled": True,
                    "holdMouseButton": "x2",
                    "pressMouseButton": "left",
                    "actions": [{"type": "mouseClick", "button": "right"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )

        self.assertFalse(service._input_listener.started)
        service._emit_mouse_event("x2", True)
        service._on_global_input_event("mouse", "left", True)
        self.assertEqual(input_service.clicks, [])

        service.stop()

    def test_mouse_macro_service_stops_hooks_when_disabled(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "enabled": True,
                    "pressMouseButton": "left",
                    "actions": [{"type": "mouseClick", "button": "right"}],
                }
            ],
        }
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=_FakeInputService(),
        )

        self.assertTrue(service._input_listener.started)
        config["enabled"] = False
        service.sync_runtime()
        self.assertTrue(service._input_listener.stopped)
        self.assertFalse(service._hook_mode_active)

        service.stop()

    def test_mouse_macro_cancel_on_hold_release_ignores_press_release_by_default(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "hold-left",
                    "enabled": True,
                    "holdMouseButton": "x1",
                    "pressMouseButton": "left",
                    "cancelOnHoldRelease": True,
                    "actions": [{"type": "key", "key": "2"}],
                }
            ],
        }
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=_FakeInputService(),
        )
        service._poll_timer.stop()

        try:
            rule = config["rules"][0]
            service._current_rule = rule
            self.assertFalse(service._current_rule_cancel_matches("mouse", "left"))
            self.assertTrue(service._current_rule_cancel_matches("mouse", "x1"))
            rule["cancelOnPressRelease"] = True
            self.assertTrue(service._current_rule_cancel_matches("mouse", "left"))
        finally:
            service.stop()

    def test_mouse_macro_service_honors_cooldown_between_triggers(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "x1-switch",
                    "enabled": True,
                    "pressMouseButton": "x1",
                    "cooldownMs": 300,
                    "actions": [{"type": "key", "key": "2"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        try:
            with mock.patch('services.macro_service.time.monotonic', side_effect=[1.0, 1.05, 1.10, 1.40, 1.41]):
                service._on_global_input_event('mouse', 'x1', True)
                service._on_global_input_event('mouse', 'x1', False)
                service._on_global_input_event('mouse', 'x1', True)
                service._on_global_input_event('mouse', 'x1', False)
                service._on_global_input_event('mouse', 'x1', True)

            self.assertEqual(input_service.keys, ["2", "2"])
        finally:
            service.stop()

    def test_mouse_macro_service_supports_press_only_mouse_rule(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "x1-switch",
                    "enabled": True,
                    "pressMouseButton": "x1",
                    "actions": [
                        {"type": "keyDown", "key": "2"},
                        {"type": "keyUp", "key": "2"},
                    ],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        try:
            service._on_global_input_event("mouse", "x1", True)
            self.assertEqual(input_service.key_downs, ["2"])
            self.assertEqual(input_service.key_ups, ["2"])
        finally:
            service.stop()

    def test_mouse_macro_service_supports_key_down_up_actions(self):
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: {"enabled": True, "source": "builder", "rules": []},
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        try:
            service._execute_actions([
                {"type": "keyDown", "key": "2"},
                {"type": "delay", "ms": 0},
                {"type": "keyDown", "key": "1"},
                {"type": "keyUp", "key": "2"},
                {"type": "keyUp", "key": "1"},
            ], rule={"interruptible": True}, rule_key="test:mouse:left")

            self.assertEqual(input_service.key_downs, ["2", "1"])
            self.assertEqual(input_service.key_ups, ["2", "1"])
            self.assertEqual(service._held_output_keys, [])
        finally:
            service.stop()

    def test_mouse_macro_service_supports_toggle_arm_and_fire(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "toggle-left",
                    "enabled": True,
                    "triggerMode": "toggle",
                    "holdMouseButton": "x1",
                    "pressMouseButton": "left",
                    "actions": [{"type": "key", "key": "2"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        try:
            service._on_global_input_event("mouse", "x1", True)
            service._on_global_input_event("mouse", "x1", False)
            service._on_global_input_event("mouse", "left", True)
            self.assertEqual(input_service.keys, ["2"])

            service._on_global_input_event("mouse", "x1", True)
            service._on_global_input_event("mouse", "x1", False)
            service._on_global_input_event("mouse", "left", True)
            self.assertEqual(input_service.keys, ["2"])
        finally:
            service.stop()

    def test_mouse_macro_service_supports_hold_loop_until_release(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "hold-loop",
                    "enabled": True,
                    "triggerMode": "holdLoop",
                    "holdMouseButton": "x1",
                    "actions": [{"type": "key", "key": "2"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()
        service._loop_timer.stop()

        try:
            service._on_global_input_event("mouse", "x1", True)
            service._run_loop_tick()
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["2", "2"])

            service._on_global_input_event("mouse", "x1", False)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["2", "2"])
        finally:
            service.stop()

    def test_mouse_macro_service_supports_toggle_loop_until_second_press(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "toggle-loop",
                    "enabled": True,
                    "triggerMode": "toggleLoop",
                    "holdMouseButton": "x1",
                    "actions": [{"type": "key", "key": "1"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()
        service._loop_timer.stop()

        try:
            service._on_global_input_event("mouse", "x1", True)
            service._run_loop_tick()
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["1", "1"])

            service._on_global_input_event("mouse", "x1", False)
            service._on_global_input_event("mouse", "x1", True)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["1", "1"])
        finally:
            service.stop()

    def test_mouse_macro_toggle_loop_can_wait_for_press_held(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "left-hold-repeat-r-toggle-1",
                    "enabled": True,
                    "triggerMode": "toggleLoop",
                    "holdKey": "1",
                    "pressMouseButton": "left",
                    "loopWhilePressHeld": True,
                    "loopIntervalMs": 100,
                    "actions": [{"type": "key", "key": "R"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()
        service._loop_timer.stop()

        try:
            service._on_global_input_event("key", "1", True)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, [])

            service._on_global_input_event("mouse", "left", True)
            service._run_loop_tick()
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R"])

            service._on_global_input_event("mouse", "left", False)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R"])
        finally:
            service.stop()

    def test_mouse_macro_toggle_loop_supports_strict_on_off_keys(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "left-hold-repeat-r-on-1-off-2",
                    "enabled": True,
                    "triggerMode": "toggleLoop",
                    "toggleOnKey": "1",
                    "toggleOffKey": "2",
                    "pressMouseButton": "left",
                    "loopWhilePressHeld": True,
                    "loopIntervalMs": 100,
                    "actions": [{"type": "key", "key": "R"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()
        service._loop_timer.stop()

        try:
            service._on_global_input_event("key", "1", True)
            service._on_global_input_event("key", "1", False)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, [])
            self.assertIn("left-hold-repeat-r-on-1-off-2", service._toggled_rule_ids)

            service._on_global_input_event("key", "1", True)
            service._on_global_input_event("key", "1", False)
            service._run_loop_tick()
            self.assertIn("left-hold-repeat-r-on-1-off-2", service._toggled_rule_ids)
            self.assertEqual(input_service.keys, [])

            service._on_global_input_event("mouse", "left", True)
            service._run_loop_tick()
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R"])

            service._on_global_input_event("mouse", "left", False)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R"])
            self.assertIn("left-hold-repeat-r-on-1-off-2", service._toggled_rule_ids)

            service._on_global_input_event("mouse", "left", True)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R", "R"])

            service._on_global_input_event("key", "2", True)
            service._on_global_input_event("key", "2", False)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R", "R"])
            self.assertNotIn("left-hold-repeat-r-on-1-off-2", service._toggled_rule_ids)
        finally:
            service.stop()

    def test_mouse_macro_toggle_loop_on_off_keys_can_repeat_without_press_gate(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "repeat-r-on-1-off-2",
                    "enabled": True,
                    "triggerMode": "toggleLoop",
                    "toggleOnKey": "1",
                    "toggleOffKey": "2",
                    "loopIntervalMs": 100,
                    "actions": [{"type": "key", "key": "R"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()
        service._loop_timer.stop()

        try:
            service._on_global_input_event("key", "1", True)
            service._on_global_input_event("key", "1", False)
            service._run_loop_tick()
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R"])
            self.assertIn("repeat-r-on-1-off-2", service._toggled_rule_ids)

            service._on_global_input_event("key", "2", True)
            service._on_global_input_event("key", "2", False)
            service._run_loop_tick()
            self.assertEqual(input_service.keys, ["R", "R"])
            self.assertNotIn("repeat-r-on-1-off-2", service._toggled_rule_ids)
        finally:
            service.stop()

    def test_mouse_macro_service_supports_mouse_down_up_actions(self):
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: {"enabled": True, "source": "builder", "rules": []},
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        try:
            service._execute_actions([
                {"type": "mouseDown", "button": "left"},
                {"type": "delay", "ms": 10},
                {"type": "mouseUp", "button": "left"},
            ], rule={"interruptible": True}, rule_key="test:mouse:left")

            self.assertEqual(input_service.clicks, ["left:down", "left:up"])
        finally:
            service.stop()

    def test_mouse_macro_service_supports_repeat_move_scroll_and_click_hold(self):
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: {"enabled": True, "source": "builder", "rules": []},
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        try:
            with mock.patch("services.input_service.time.sleep"):
                service._execute_actions([
                    {
                        "type": "repeat",
                        "count": 2,
                        "actions": [
                            {"type": "mouseClick", "button": "left", "holdMs": 5},
                            {"type": "mouseMoveRelative", "dx": 2, "dy": -1},
                        ],
                    },
                    {"type": "mouseMove", "x": 100, "y": 200},
                    {"type": "mouseScroll", "dy": -120},
                ], rule={"interruptible": True}, rule_key="test:macro:advanced")

            self.assertEqual(input_service.clicks, ["left:down", "left:up", "left:down", "left:up"])
            self.assertEqual(input_service.moves, [("relative", 2, -1), ("relative", 2, -1), (100, 200)])
            self.assertEqual(input_service.scrolls, [(0, -120)])
        finally:
            service.stop()

    def test_mouse_macro_service_releases_key_down_on_cleanup(self):
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: {"enabled": True, "source": "builder", "rules": []},
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        try:
            service._execute_actions([
                {"type": "keyDown", "key": "2"},
            ], rule={"interruptible": True}, rule_key="test:mouse:left")

            self.assertEqual(input_service.key_downs, ["2"])
            self.assertEqual(input_service.key_ups, ["2"])
            self.assertEqual(service._held_output_keys, [])
        finally:
            service.stop()


    def test_mouse_macro_panic_hotkey_force_cancels_and_releases_outputs(self):
        config = {
            "enabled": True,
            "source": "builder",
            "panicHotkey": {"modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F12"},
            "rules": [],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )
        service._poll_timer.stop()

        def sleep_and_panic(_seconds):
            service._on_global_input_event("key", "F12", True)

        try:
            with mock.patch("services.macro_service.user32.GetAsyncKeyState", return_value=0), \
                 mock.patch("services.macro_service.time.sleep", side_effect=sleep_and_panic):
                service._execute_actions(
                    [
                        {"type": "keyDown", "key": "2"},
                        {"type": "mouseDown", "button": "left"},
                        {"type": "delay", "ms": 50},
                        {"type": "keyDown", "key": "1"},
                    ],
                    rule={"interruptible": False},
                    rule_key="panic:test",
                )

            self.assertEqual(input_service.key_downs, ["2"])
            self.assertEqual(input_service.key_ups, ["2"])
            self.assertEqual(input_service.clicks, ["left:down", "left:up"])
            self.assertEqual(service._held_output_keys, [])
            self.assertEqual(service._held_output_mouse_buttons, [])
        finally:
            service.stop()


    def test_mouse_macro_service_loads_external_json_rules(self):
        import json
        import tempfile
        import os

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as file:
            json.dump({
                "rules": [{
                    "id": "external-middle-left",
                    "enabled": True,
                    "holdMouseButton": "middle",
                    "pressMouseButton": "left",
                    "actions": [{"type": "key", "key": "2"}],
                }]
            }, file)
            path = file.name

        config = {"enabled": True, "source": "file", "configFile": path, "rules": []}
        service = MouseMacroService(get_config=lambda: config, input_listener_factory=_FakeInputListener)
        service._poll_timer.stop()

        try:
            with mock.patch.object(service, "_send_key") as send_key:
                service._on_global_input_event("mouse", "middle", True)
                service._on_global_input_event("mouse", "left", True)
                send_key.assert_called_once_with("2")
        finally:
            service.stop()
            os.unlink(path)

    def test_mouse_macro_service_supports_hold_key_press_mouse(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "alt-left",
                    "enabled": True,
                    "holdKey": "Alt",
                    "pressMouseButton": "left",
                    "actions": [{"type": "key", "key": "1"}],
                }
            ],
        }
        service = MouseMacroService(get_config=lambda: config, input_listener_factory=_FakeInputListener)
        service._poll_timer.stop()

        with mock.patch.object(service, "_send_key") as send_key:
            service._on_global_input_event("key", "Alt", True)
            service._on_global_input_event("mouse", "left", True)
            send_key.assert_called_once_with("1")

            service._on_global_input_event("mouse", "left", False)
            service._on_global_input_event("mouse", "left", True)
            self.assertEqual(send_key.call_count, 2)

        service.stop()

    def test_mouse_macro_service_supports_hold_key_press_key_repeat(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "a-b",
                    "enabled": True,
                    "holdKey": "A",
                    "pressKey": "B",
                    "actions": [{"type": "key", "key": "1"}],
                }
            ],
        }
        service = MouseMacroService(get_config=lambda: config, input_listener_factory=_FakeInputListener)
        service._poll_timer.stop()

        with mock.patch.object(service, "_send_key") as send_key:
            service._on_global_input_event("key", "A", True)
            service._on_global_input_event("key", "B", True)
            service._on_global_input_event("key", "B", True)
            send_key.assert_called_once_with("1")

            service._on_global_input_event("key", "B", False)
            service._on_global_input_event("key", "B", True)
            self.assertEqual(send_key.call_count, 2)

        service.stop()

    def test_mouse_macro_service_executes_delay_between_actions(self):
        config = {"enabled": True, "source": "builder", "rules": []}
        service = MouseMacroService(get_config=lambda: config, input_listener_factory=_FakeInputListener)
        service._poll_timer.stop()

        with mock.patch.object(service, "_send_key") as send_key, \
             mock.patch("services.macro_service.time.sleep") as sleep:
            service._execute_actions([
                {"type": "key", "key": "A"},
                {"type": "delay", "ms": 50},
                {"type": "key", "key": "B"},
            ])

        self.assertEqual(send_key.mock_calls, [mock.call("A"), mock.call("B")])
        self.assertEqual(sleep.mock_calls, [mock.call(0.025), mock.call(0.025)])
        service.stop()

    def test_mouse_macro_service_interruptible_rule_can_cancel_scheduler(self):
        config = {"enabled": True, "source": "builder", "rules": []}
        service = MouseMacroService(get_config=lambda: config, input_listener_factory=_FakeInputListener)
        service._poll_timer.stop()
        with mock.patch.object(service, "_send_key") as send_key, \
             mock.patch.object(service, "_should_cancel_actions", return_value=True):
            service._execute_actions(
                [{"type": "key", "key": "A"}],
                rule={"interruptible": True, "cancelOnHoldRelease": True},
                rule_key="cancel:key:a",
            )

        send_key.assert_not_called()
        service.stop()

    def test_mouse_macro_service_runs_combo_rule_once_until_release(self):
        config = {
            "enabled": True,
            "source": "builder",
            "rules": [
                {
                    "id": "copy",
                    "enabled": True,
                    "holdMouseButton": "x2",
                    "pressMouseButton": "left",
                    "actions": [{"type": "mouseClick", "button": "right"}],
                }
            ],
        }
        input_service = _FakeInputService()
        service = MouseMacroService(
            get_config=lambda: config,
            input_listener_factory=_FakeInputListener,
            input_service=input_service,
        )

        service._on_global_input_event("mouse", "x2", True)
        service._on_global_input_event("mouse", "left", True)
        service._on_global_input_event("mouse", "left", True)
        self.assertEqual(input_service.clicks, ["right"])

        service._on_global_input_event("mouse", "left", False)
        service._on_global_input_event("mouse", "left", True)
        self.assertEqual(input_service.clicks, ["right", "right"])

        service.stop()

    def test_clicker_service_start_stop_and_sync(self):
        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {"mode": "toggle", "toggleHotkey": {"key": "F6"}},
        }
        state_changes = []
        started = []
        stopped = []

        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: state_changes.append("changed"),
            on_notify_started=lambda p: started.append(p["button"]),
            on_notify_stopped=lambda p: stopped.append(p["button"]),
            input_listener_factory=_FakeInputListener,
        )

        self.assertEqual(service.clicker_timer.timerType(), QtCore.Qt.TimerType.PreciseTimer)

        service.start(show_message=True, immediate_click=False)
        self.assertTrue(service.is_running)
        self.assertEqual(started, ["left"])

        profile["enabled"] = False
        service.sync_runtime()
        self.assertFalse(service.is_running)
        self.assertGreaterEqual(len(state_changes), 2)

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_does_not_install_hold_hooks_for_toggle_profile(self):
        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {"mode": "toggle", "toggleHotkey": {"key": "F6"}},
        }
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            input_listener_factory=_FakeInputListener,
        )

        self.assertFalse(service._input_listener.started)
        self.assertFalse(service._hook_mode_active)

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_stops_hold_hooks_when_profile_disabled(self):
        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {"mode": "holdMouseButton", "holdMouseButton": "x1"},
        }
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            input_listener_factory=_FakeInputListener,
        )

        self.assertTrue(service._input_listener.started)
        self.assertTrue(service._hook_mode_active)
        profile["enabled"] = False
        service.sync_runtime()
        self.assertTrue(service._input_listener.stopped)
        self.assertFalse(service._hook_mode_active)

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_hold_key_starts_and_stops_immediately(self):
        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "holdKey",
                "holdKey": {
                    "modCtrl": True,
                    "modAlt": False,
                    "modShift": False,
                    "modWin": False,
                    "key": "F7",
                },
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FakeInputListener,
        )

        service._on_global_input_event("key", "ctrl", True)
        service._on_global_input_event("key", "f7", True)
        self.assertTrue(service.is_running)
        click_mouse.assert_called_once_with("left")

        service._on_global_input_event("key", "f7", False)
        self.assertFalse(service.is_running)

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_hold_mouse_button_starts_and_stops(self):
        profile = {
            "enabled": True,
            "button": "middle",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "holdMouseButton",
                "holdMouseButton": "x1",
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FakeInputListener,
        )

        service._on_global_input_event("mouse", "x1", True)
        self.assertTrue(service.is_running)
        click_mouse.assert_called_once_with("middle")

        service._on_global_input_event("mouse", "x1", False)
        self.assertFalse(service.is_running)

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_can_hold_mouse_down_for_compatibility(self):
        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "clickHoldMs": 10,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {"mode": "toggle"},
        }
        input_service = _FakeInputService()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            input_service=input_service,
            input_listener_factory=_FakeInputListener,
        )

        service.start(show_message=False, immediate_click=True)
        self.assertEqual(input_service.clicks, ["left:down"])
        self.assertTrue(service.click_release_timer.isActive())
        service._on_clicker_tick()
        self.assertEqual(input_service.clicks, ["left:down"])
        service.stop(show_message=False)
        self.assertEqual(input_service.clicks, ["left:down", "left:up"])
        self.assertFalse(service.click_release_timer.isActive())

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_process_blacklist_blocks_side_button_trigger(self):
        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "processBlacklist": ["steam.exe"],
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "holdMouseButton",
                "holdMouseButton": "x1",
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FakeInputListener,
        )

        try:
            with mock.patch("services.clicker_service.get_active_window_info", return_value=(123, "Steam")), \
                 mock.patch("services.clicker_service.get_window_process_name", return_value="steam.exe"):
                service._on_global_input_event("mouse", "x1", True)
                self.assertFalse(service.is_running)
                click_mouse.assert_not_called()
        finally:
            service.hold_state_timer.stop()
            service.clicker_timer.stop()

    def test_clicker_service_swap_key_swaps_click_button_while_held(self):
        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "toggle",
                "swapMode": "key",
                "swapKey": {
                    "modCtrl": False,
                    "modAlt": False,
                    "modShift": False,
                    "modWin": False,
                    "key": "F8",
                },
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FakeInputListener,
        )

        self.assertTrue(service._input_listener.started)
        self.assertTrue(service._hook_mode_active)

        service.start(show_message=False, immediate_click=True)
        click_mouse.assert_called_once_with("left")

        service._on_global_input_event("key", "f8", True)
        service._click_once(profile)
        click_mouse.assert_called_with("right")

        service._on_global_input_event("key", "f8", False)
        service._click_once(profile)
        click_mouse.assert_called_with("left")

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_swap_mouse_button_swaps_while_held(self):
        profile = {
            "enabled": True,
            "button": "right",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "toggle",
                "swapMode": "mouseButton",
                "swapMouseButton": "x1",
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FakeInputListener,
        )

        service.start(show_message=False, immediate_click=True)
        click_mouse.assert_called_once_with("right")

        service._on_global_input_event("mouse", "x1", True)
        service._click_once(profile)
        click_mouse.assert_called_with("left")

        service._on_global_input_event("mouse", "x1", False)
        service._click_once(profile)
        click_mouse.assert_called_with("right")

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_swap_keeps_middle_button_unaffected(self):
        profile = {
            "enabled": True,
            "button": "middle",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "toggle",
                "swapMode": "key",
                "swapKey": {"modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F8"},
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FakeInputListener,
        )

        service.start(show_message=False, immediate_click=True)
        service._on_global_input_event("key", "f8", True)
        service._click_once(profile)
        click_mouse.assert_any_call("middle")

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_swap_falls_back_to_polling_when_hook_unavailable(self):
        class _FailedInputListener(_FakeInputListener):
            def start(self):
                self.started = True
                return False

        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "toggle",
                "swapMode": "key",
                "swapKey": {
                    "modCtrl": False,
                    "modAlt": False,
                    "modShift": False,
                    "modWin": False,
                    "key": "F8",
                },
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FailedInputListener,
        )

        self.assertTrue(service.hold_state_timer.isActive())
        self.assertFalse(service._hook_mode_active)

        f8_held = {"value": False}

        def fake_modifier_pressed(vk):
            return bool(vk == 0x77 and f8_held["value"])

        with mock.patch.object(service, "_modifier_pressed", side_effect=fake_modifier_pressed):
            service.start(show_message=False, immediate_click=True)
            click_mouse.assert_called_once_with("left")

            f8_held["value"] = True
            service._poll_hold_trigger_state()
            service._click_once(profile)
            click_mouse.assert_called_with("right")

            f8_held["value"] = False
            service._poll_hold_trigger_state()
            service._click_once(profile)
            click_mouse.assert_called_with("left")

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_clicker_service_falls_back_to_polling_when_hook_unavailable(self):
        class _FailedInputListener(_FakeInputListener):
            def start(self):
                self.started = True
                return False

        profile = {
            "enabled": True,
            "button": "left",
            "intervalMs": 25,
            "sound": {"enabled": False, "preset": "systemAsterisk", "customFile": ""},
            "triggers": {
                "mode": "holdKey",
                "holdKey": {
                    "modCtrl": False,
                    "modAlt": False,
                    "modShift": False,
                    "modWin": False,
                    "key": "F7",
                },
            },
        }
        click_mouse = mock.Mock()
        service = ClickerService(
            get_profile=lambda: profile,
            on_state_changed=lambda: None,
            on_notify_started=lambda _profile: None,
            on_notify_stopped=lambda _profile: None,
            click_mouse_func=click_mouse,
            input_listener_factory=_FailedInputListener,
        )

        self.assertTrue(service.hold_state_timer.isActive())
        with mock.patch.object(service, "_modifier_pressed", side_effect=lambda vk: vk == 0x76):
            service._poll_hold_trigger_state()
            self.assertTrue(service.is_running)
            click_mouse.assert_called_once_with("left")

        service.hold_state_timer.stop()
        service.clicker_timer.stop()

    def test_lock_service_window_matching_and_target_position(self):
        settings = {
            "windowSpecific": {
                "enabled": False,
                "autoLockOnWindowFocus": False,
                "targetWindows": [],
                "resumeAfterWindowSwitch": False,
            },
            "position": {"mode": "custom", "customX": 321, "customY": 654},
            "recenter": {"enabled": True, "intervalMs": 250},
        }
        changes = []
        service = LockService(
            get_settings=lambda: settings,
            on_state_changed=lambda: changes.append("changed"),
            on_notify_locked=lambda: changes.append("locked"),
            on_notify_unlocked=lambda: changes.append("unlocked"),
            on_error=lambda op, exc: changes.append(f"error:{op}"),
        )

        self.assertEqual(service._get_target_position(), (321, 654))
        self.assertTrue(service._check_match("QQ Chat", "qq.exe", ["qq.exe"]))
        self.assertTrue(service._check_match("Minecraft 1.20", "javaw.exe", ["javaw"]))
        self.assertTrue(service._check_match("Minecraft 1.20", "javaw.exe", ["minecraft"]))
        self.assertFalse(service._check_match("Notepad", "notepad.exe", ["qq.exe"]))

        service.window_focus_timer.stop()
        service.recenter_timer.stop()

    def test_lock_service_manual_lock_respects_window_specific_gate(self):
        settings = {
            "windowSpecific": {
                "enabled": True,
                "autoLockOnWindowFocus": False,
                "targetWindows": ["game.exe"],
                "resumeAfterWindowSwitch": False,
            },
            "position": {"mode": "custom", "customX": 111, "customY": 222},
            "recenter": {"enabled": True, "intervalMs": 250},
        }
        service = LockService(
            get_settings=lambda: settings,
            on_state_changed=lambda: None,
            on_notify_locked=lambda: None,
            on_notify_unlocked=lambda: None,
            on_error=lambda op, exc: None,
        )
        try:
            with mock.patch.object(service, "_should_lock_for_window", return_value=False), \
                 mock.patch("services.lock_service.set_cursor_to") as set_cursor, \
                 mock.patch("services.lock_service.clip_cursor_to_point") as clip_cursor:
                service.lock(manual=True)
                self.assertFalse(service.is_locked)
                set_cursor.assert_not_called()
                clip_cursor.assert_not_called()
        finally:
            service.window_focus_timer.stop()
            service.recenter_timer.stop()

    def test_lock_service_manual_lock_in_target_is_released_outside_target(self):
        settings = {
            "windowSpecific": {
                "enabled": True,
                "autoLockOnWindowFocus": False,
                "targetWindows": ["game.exe"],
                "resumeAfterWindowSwitch": False,
            },
            "position": {"mode": "custom", "customX": 111, "customY": 222},
            "recenter": {"enabled": False, "intervalMs": 250},
        }
        service = LockService(
            get_settings=lambda: settings,
            on_state_changed=lambda: None,
            on_notify_locked=lambda: None,
            on_notify_unlocked=lambda: None,
            on_error=lambda op, exc: None,
        )
        try:
            with mock.patch.object(service, "_should_lock_for_window", return_value=True), \
                 mock.patch("services.lock_service.set_cursor_to"), \
                 mock.patch("services.lock_service.clip_cursor_to_point"):
                service.lock(manual=True)
                self.assertTrue(service.is_locked)
                self.assertFalse(service.is_force_lock)

            with mock.patch("services.lock_service.get_active_window_info", return_value=(303, "Notepad")), \
                 mock.patch("services.lock_service.get_window_process_name", return_value="notepad.exe"), \
                 mock.patch("services.lock_service.unclip_cursor") as unclip_cursor:
                service._check_window_focus()
                self.assertFalse(service.is_locked)
                unclip_cursor.assert_called_once()
        finally:
            service.window_focus_timer.stop()
            service.recenter_timer.stop()

    def test_lock_service_suspends_recenter_while_target_window_moves(self):
        settings = {
            "windowSpecific": {
                "enabled": True,
                "autoLockOnWindowFocus": False,
                "targetWindows": ["game.exe"],
                "resumeAfterWindowSwitch": False,
            },
            "position": {"mode": "custom", "customX": 111, "customY": 222},
            "recenter": {"enabled": True, "intervalMs": 250},
        }
        service = LockService(
            get_settings=lambda: settings,
            on_state_changed=lambda: None,
            on_notify_locked=lambda: None,
            on_notify_unlocked=lambda: None,
            on_error=lambda op, exc: None,
        )
        try:
            service._locked = True
            service._last_target_position = (100, 100)
            with mock.patch.object(service, "_should_lock_for_window", return_value=True), \
                 mock.patch.object(service, "_get_target_position", return_value=(200, 200)), \
                 mock.patch("services.lock_service.is_primary_mouse_button_pressed", return_value=True), \
                 mock.patch("services.lock_service.unclip_cursor") as unclip_cursor, \
                 mock.patch("services.lock_service.set_cursor_to") as set_cursor, \
                 mock.patch("services.lock_service.clip_cursor_to_point") as clip_cursor:
                service._on_recenter_tick()
                unclip_cursor.assert_called_once()
                set_cursor.assert_not_called()
                clip_cursor.assert_not_called()
                self.assertEqual(service._last_target_position, (200, 200))
        finally:
            service.window_focus_timer.stop()
            service.recenter_timer.stop()

    def test_lock_service_auto_lock_tracks_window_changes_by_hwnd_and_process(self):
        settings = {
            "windowSpecific": {
                "enabled": True,
                "autoLockOnWindowFocus": True,
                "targetWindows": ["Minecraft"],
                "resumeAfterWindowSwitch": False,
            },
            "position": {"mode": "custom", "customX": 111, "customY": 222},
            "recenter": {"enabled": False, "intervalMs": 250},
        }
        service = LockService(
            get_settings=lambda: settings,
            on_state_changed=lambda: None,
            on_notify_locked=lambda: None,
            on_notify_unlocked=lambda: None,
            on_error=lambda op, exc: None,
        )
        try:
            with mock.patch.object(
                service,
                "lock",
                side_effect=lambda manual=False: setattr(service, "_locked", True),
            ) as lock_mock, mock.patch.object(
                service,
                "unlock",
                side_effect=lambda manual=False: setattr(service, "_locked", False),
            ) as unlock_mock, mock.patch(
                "services.lock_service.get_active_window_info",
                side_effect=[
                    (101, "Notepad"),
                    (202, "Minecraft"),
                    (303, "Notepad"),
                ],
            ), mock.patch(
                "services.lock_service.get_window_process_name",
                side_effect=["notepad.exe", "javaw.exe", "notepad.exe"],
            ):
                service._check_window_focus()
                service._check_window_focus()
                service._check_window_focus()

            lock_mock.assert_called_once_with(manual=False)
            unlock_mock.assert_called_once_with(manual=False)
        finally:
            service.window_focus_timer.stop()
            service.recenter_timer.stop()

    def test_tray_service_refreshes_state_and_clicker_text(self):
        profile = {
            "id": "default",
            "name": "默认方案",
            "enabled": True,
            "triggers": {"toggleHotkey": {"modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F6"}},
        }
        alternate_profile = {
            "id": "rapid",
            "name": "快速方案",
            "enabled": False,
            "triggers": {},
        }
        selected_profiles = []
        service = TrayService(
            parent=None,
            dynamic_icon_factory=lambda locked, status: self.app.windowIcon(),
            i18n=type("I18nStub", (), {"t": staticmethod(lambda _key, fallback="": fallback or _key)})(),
            get_locked=lambda: True,
            get_clicker_running=lambda: False,
            get_status=lambda: "lock",
            get_clicker_profile=lambda: profile,
            get_clicker_profiles=lambda: [profile, alternate_profile],
            get_active_profile_id=lambda: "default",
            get_hotkeys=lambda: {"toggle": {"modCtrl": True, "modAlt": True, "modShift": False, "modWin": False, "key": "K"}},
            on_toggle_lock=lambda: None,
            on_lock=lambda: None,
            on_unlock=lambda: None,
            on_toggle_clicker=lambda: None,
            on_select_profile=selected_profiles.append,
            on_show_window=lambda: None,
            on_quit=lambda: None,
        )
        try:
            service.refresh()
            self.assertIn("Locked", service.state_action.text())
            self.assertIn("默认方案", service.state_action.text())
            self.assertIn("Ctrl+Alt+K", service.hk_info_action.text())
            self.assertIn("Start Auto Clicker", service.clicker_action.text())
            profile_actions = service.profile_menu.actions()
            self.assertEqual(["默认方案", "快速方案"], [action.text() for action in profile_actions])
            self.assertTrue(profile_actions[0].isChecked())
            self.assertFalse(profile_actions[1].isChecked())
            profile_actions[1].trigger()
            self.assertEqual(["rapid"], selected_profiles)
        finally:
            service.tray.hide()
            service.tray.setContextMenu(None)
            service.menu.deleteLater()
            service.tray.deleteLater()
            service.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
