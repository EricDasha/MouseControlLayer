"""
MCL main window.
"""
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

from PySide6 import QtCore, QtGui, QtWidgets
from app_logging import get_log_path, is_logging_enabled, log_message
from app_paths import APP_DIR, ASSETS_DIR, RUN_DIR

from win_api import (
    release_single_instance,
    format_hotkey_display, register_hotkeys, unregister_hotkeys,
    is_startup_enabled, set_startup_enabled, enumerate_visible_windows
)
from services.clicker_service import ClickerService
from services.clicker_profile_controller import ClickerProfileController
from services.input_service import InputService
from services.lock_service import LockService
from services.macro_service import MouseMacroService
from services.macro_service import resolve_macro_config_path
from services.taskbar_status_service import TaskbarStatusService
from services.settings_apply_controller import SettingsApplyController
from services.theme_service import ThemeService
from services.tray_service import TrayService
from i18n_manager import I18n
from settings_manager import (
    SettingsManager,
    CLICKER_PRESETS,
    CLICKER_TRIGGER_MODES,
)
from ui.pages.simple_page import build_simple_page
from ui.pages.advanced_page import build_advanced_page
from ui.forms.clicker_profile_form import (
    collect_clicker_profile_form_data,
    load_clicker_profile_into_form,
)
from ui.forms.settings_form import (
    apply_general_settings_form_data,
    collect_general_settings_form_data,
)
from ui.presenters.main_window_presenter import (
    build_clicker_button_presentation,
    build_simple_info_text,
    build_status_badge_presentation,
    build_toggle_button_text,
    describe_clicker_preset,
    resolve_clicker_preset,
)
from widgets import ProcessPickerDialog, CloseActionDialog, WindowResizeDialog


class MainWindow(QtWidgets.QMainWindow):
    """Main application window."""

    _BASE_SCREEN_SIZE = (1920, 1080)
    _BASE_WINDOW_SIZE = (600, 800)
    _MIN_WINDOW_SIZE = (450, 500)
    _WINDOW_DISPLAY_TITLE = "鼠标中心锁定"
    
    def __init__(self, settings: SettingsManager, i18n: I18n):
        super().__init__()
        self.settings = settings
        self.i18n = i18n
        
        self._custom_icon: Optional[QtGui.QIcon] = None
        self._tray_service: Optional[TrayService] = None
        self._taskbar_status_service = TaskbarStatusService()
        self._selected_profile_id = self.settings.data.get("activeClickerProfileId", "default")
        self._profile_dirty = False
        self._suspend_live_apply = 0
        self._live_apply_timer = QtCore.QTimer(self)
        self._live_apply_timer.setSingleShot(True)
        self._live_apply_timer.timeout.connect(self._apply_live_settings)
        self._taskbar_flash_timer = QtCore.QTimer(self)
        self._taskbar_flash_timer.setSingleShot(True)
        self._taskbar_flash_timer.timeout.connect(self._update_taskbar_status)
        self._macro_input_service = InputService(
            get_backend=lambda: self.settings.data.get("inputBackend", "auto"),
            get_fallback_backend=lambda: self.settings.data.get("fallbackBackend", "native-sendinput"),
            get_fallback_policy=lambda: self.settings.data.get("fallbackPolicy", "auto"),
        )
        self._clicker_input_service = InputService(
            get_backend=lambda: self._get_active_clicker_profile().get("inputBackend", "auto"),
            get_fallback_backend=lambda: self.settings.data.get("fallbackBackend", "native-sendinput"),
            get_fallback_policy=lambda: self.settings.data.get("fallbackPolicy", "auto"),
        )
        self._clicker_service = ClickerService(
            get_profile=self._get_active_clicker_profile,
            on_state_changed=self._on_clicker_runtime_changed,
            on_notify_started=self._notify_clicker_started,
            on_notify_stopped=self._notify_clicker_stopped,
            input_service=self._clicker_input_service,
            parent=self,
        )
        self._macro_service = MouseMacroService(
            get_config=lambda: self.settings.data.get("mouseMacros", {}),
            input_service=self._macro_input_service,
            parent=self,
        )
        self._macro_service.stateChanged.connect(self._on_macro_runtime_changed)
        self._lock_service = LockService(
            get_settings=lambda: self.settings.data,
            on_state_changed=self._on_lock_state_changed,
            on_notify_locked=self._notify_locked,
            on_notify_unlocked=self._notify_unlocked,
            on_error=self._handle_lock_service_error,
            parent=self,
        )
        self._theme_service = ThemeService()
        self._clicker_profile_controller = ClickerProfileController(
            settings=self.settings,
            save_settings=self._save_settings_or_warn,
            notify=self._notify,
            stop_clicker=self.stop_clicker,
            sync_clicker_runtime=self._clicker_service.sync_runtime,
            refresh_form=self._load_profile_into_form,
            refresh_profile_list=self._populate_clicker_profiles,
            refresh_ui=self._refresh_clicker_ui,
            tooltip_saved=self._show_saved_tooltip,
            i18n=self.i18n,
        )
        self._settings_apply_controller = SettingsApplyController(
            settings=self.settings,
            collect_general_form_data=self._current_general_settings_form_data,
            collect_clicker_profile_data=self._current_profile_form_data,
            apply_general_form_data=apply_general_settings_form_data,
            set_startup=self._set_startup_or_warn,
            get_startup_enabled=is_startup_enabled,
            save_settings=self._save_settings_or_warn,
            sync_lock_runtime=self._lock_service.sync_runtime,
            get_active_clicker_profile=self._get_active_clicker_profile,
            stop_clicker=self.stop_clicker,
            sync_clicker_runtime=self._clicker_service.sync_runtime,
            sync_macro_runtime=self._macro_service.sync_runtime,
            unregister_hotkeys=unregister_hotkeys,
            register_hotkeys=register_hotkeys,
            on_hotkey_conflict=self._register_hotkeys_or_warn,
            apply_theme=self._apply_theme,
            refresh_ui=self._refresh_all_runtime_ui,
            refresh_profiles=self._populate_clicker_profiles,
            show_saved_feedback=self._show_saved_tooltip,
        )
        
        self._setup_window()
        self._setup_timers()
        self._build_ui()
        self._apply_theme()
        self._create_tray()
        self._update_taskbar_status()
    
    @property
    def locked(self) -> bool:
        return self._lock_service.is_locked
    
    @locked.setter
    def locked(self, value: bool):
        if value:
            self._lock_service.lock(manual=False)
        else:
            self._lock_service.unlock(manual=False)

    @property
    def clicker_running(self) -> bool:
        return self._clicker_service.is_running

    def _get_visual_status(self) -> str:
        """Return the strongest runtime state for UI indicators."""
        if getattr(self, "_macro_service", None) is not None and self._macro_service.is_active:
            return "macro"
        if self.locked:
            return "lock"
        if self.clicker_running:
            return "clicker"
        return ""

    def _runtime_title_suffix(self) -> str:
        """Return the full taskbar/window title for active automation state."""
        if self.clicker_running:
            return self.i18n.t("taskbar.title.clicker", "Mouse auto-clicker started")
        if getattr(self, "_macro_service", None) is not None and self._macro_service.is_active:
            return self.i18n.t("taskbar.title.macro", "Mouse macro started")
        return ""

    def _update_window_runtime_title(self) -> None:
        """Update taskbar/window text to expose active automation state."""
        runtime_title = self._runtime_title_suffix()
        title = runtime_title or self._WINDOW_DISPLAY_TITLE
        if self.windowTitle() != title:
            self.setWindowTitle(title)

    def _get_active_clicker_profile(self) -> Dict[str, Any]:
        """Return the active clicker profile, applying frozen list overlay if enabled."""
        profile = self.settings.get_active_clicker_profile()
        if not self._profile_lists_follow_profile():
            profile["processBlacklist"] = self._frozen_process_blacklist()
        return profile

    def _get_raw_active_clicker_profile(self) -> Dict[str, Any]:
        """Return the active clicker profile exactly as stored in settings."""
        return self.settings.get_active_clicker_profile()

    def _profile_list_binding(self) -> Dict[str, Any]:
        """Return normalized profile list binding config."""
        binding = self.settings.data.setdefault("profileListBinding", {})
        if not isinstance(binding, dict):
            binding = {}
            self.settings.data["profileListBinding"] = binding
        binding.setdefault("followProfile", True)
        binding.setdefault("processBlacklist", [])
        binding.setdefault("windowSpecific", {})
        return binding

    def _profile_lists_follow_profile(self) -> bool:
        """Return whether blacklist/target-window lists should follow profile switches."""
        return bool(self._profile_list_binding().get("followProfile", True))

    def _frozen_process_blacklist(self) -> list[str]:
        """Return the frozen auto-clicker process blacklist."""
        items = self._profile_list_binding().get("processBlacklist", [])
        if not isinstance(items, list):
            return []
        return [str(item).strip() for item in items if str(item).strip()]

    def _frozen_window_specific(self) -> Dict[str, Any]:
        """Return the frozen target-window lock settings."""
        value = self._profile_list_binding().get("windowSpecific", {})
        if not isinstance(value, dict):
            value = {}
        current = self.settings.data.get("windowSpecific", {}) if isinstance(self.settings.data.get("windowSpecific", {}), dict) else {}
        targets = value.get("targetWindows", current.get("targetWindows", []))
        if not isinstance(targets, list):
            targets = []
        return {
            "enabled": bool(value.get("enabled", current.get("enabled", False))),
            "targetWindows": [str(item).strip() for item in targets if str(item).strip()],
            "targetWindowHandle": 0,
            "autoLockOnWindowFocus": bool(value.get("autoLockOnWindowFocus", current.get("autoLockOnWindowFocus", False))),
            "resumeAfterWindowSwitch": bool(value.get("resumeAfterWindowSwitch", current.get("resumeAfterWindowSwitch", False))),
        }

    def _snapshot_profile_lists_from_form(self) -> Dict[str, Any]:
        """Capture currently effective blacklist and target-window whitelist from UI."""
        process_blacklist = []
        if hasattr(self, "clickerProcessBlacklist"):
            process_blacklist = [
                self.clickerProcessBlacklist.item(i).text()
                for i in range(self.clickerProcessBlacklist.count())
            ]
        window_specific = {
            "enabled": self.windowSpecificCheck.isChecked() if hasattr(self, "windowSpecificCheck") else False,
            "targetWindows": [
                self.targetList.item(i).text()
                for i in range(self.targetList.count())
            ] if hasattr(self, "targetList") else [],
            "targetWindowHandle": 0,
            "autoLockOnWindowFocus": self.autoLockCheck.isChecked() if hasattr(self, "autoLockCheck") else False,
            "resumeAfterWindowSwitch": self.resumeAfterSwitchCheck.isChecked() if hasattr(self, "resumeAfterSwitchCheck") else False,
        }
        return {
            "processBlacklist": [str(item).strip() for item in process_blacklist if str(item).strip()],
            "windowSpecific": window_specific,
        }

    def _apply_frozen_lists_to_runtime_and_form(self) -> None:
        """Apply frozen blacklist/target-window lists without touching saved profile copies."""
        if self._profile_lists_follow_profile():
            return
        snapshot = self._profile_list_binding()
        frozen_window = self._frozen_window_specific()
        self.settings.data["windowSpecific"] = json.loads(json.dumps(frozen_window))
        if hasattr(self, "clickerProcessBlacklist"):
            self.clickerProcessBlacklist.clear()
            for process_name in self._frozen_process_blacklist():
                self.clickerProcessBlacklist.addItem(process_name)
        if hasattr(self, "windowSpecificCheck"):
            self.windowSpecificCheck.setChecked(bool(frozen_window.get("enabled", False)))
        if hasattr(self, "targetList"):
            self.targetList.clear()
            for win_title in frozen_window.get("targetWindows", []):
                self.targetList.addItem(str(win_title))
        if hasattr(self, "autoLockCheck"):
            self.autoLockCheck.setChecked(bool(frozen_window.get("autoLockOnWindowFocus", False)))
        if hasattr(self, "resumeAfterSwitchCheck"):
            self.resumeAfterSwitchCheck.setChecked(bool(frozen_window.get("resumeAfterWindowSwitch", False)))
        snapshot["processBlacklist"] = self._frozen_process_blacklist()
        snapshot["windowSpecific"] = frozen_window

    def _on_clicker_runtime_changed(self) -> None:
        """Refresh UI elements affected by clicker runtime state."""
        self._update_simple_info()
        self._update_clicker_button()
        self._update_tray_meta()
        self._update_taskbar_status()

    def _on_macro_runtime_changed(self) -> None:
        """Refresh UI elements affected by macro runtime state."""
        self._update_tray_icon()
        self._update_tray_meta()
        self._update_taskbar_status()

    def _notify_clicker_started(self, profile: Dict[str, Any]) -> None:
        """Show the clicker-started notification."""
        mode_text = self.i18n.t(
            CLICKER_TRIGGER_MODES.get(profile.get("triggers", {}).get("mode", "toggle"), ""),
            profile.get("triggers", {}).get("mode", "toggle"),
        )
        self._notify(
            self.i18n.t("clicker.started.detail", "Auto clicker started: {0} ({1})").format(
                profile.get("name", ""),
                mode_text,
            )
        )

    def _notify_clicker_stopped(self, profile: Dict[str, Any]) -> None:
        """Show the clicker-stopped notification."""
        self._notify(
            self.i18n.t("clicker.stopped.detail", "Auto clicker stopped: {0}").format(
                profile.get("name", "")
            )
        )

    def _notify_locked(self) -> None:
        """Show the locked notification."""
        self._notify(self.i18n.t("locked.message", "Locked to screen center"))

    def _notify_unlocked(self) -> None:
        """Show the unlocked notification."""
        self._notify(self.i18n.t("unlocked.message", "Unlocked"))
        self._flash_taskbar_state("unlocked")

    def _handle_lock_service_error(self, operation: str, exc: BaseException) -> None:
        """Surface lock-service errors through the GUI."""
        title = self.i18n.t("error", "Error")
        if operation == "lock":
            message = self.i18n.t("lock.failed", "Failed to lock: {}").format(str(exc))
        else:
            message = self.i18n.t("unlock.failed", "Failed to unlock: {}").format(str(exc))
        QtWidgets.QMessageBox.critical(self, title, message)

    def _build_hotkey_conflict_details(self, errors: list[str]) -> str:
        """Build a diagnostic message for hotkey registration conflicts."""
        lines = [
            self.i18n.t("hotkey.register.fail", "Some hotkeys could not be registered:"),
            self.i18n.t(
                "hotkey.conflict.which",
                "The following hotkeys are conflicting:"
            ),
        ]
        lines.extend(errors)
        lines.append("")
        lines.append(self.i18n.t(
            "hotkey.conflict.help",
            "Windows cannot directly tell which app owns a conflicting global hotkey. The list below shows visible apps you can try closing or changing hotkeys for:"
        ))

        seen_processes = set()
        for _hwnd, title, process_name in enumerate_visible_windows():
            key = (process_name or "", title or "")
            if key in seen_processes:
                continue
            seen_processes.add(key)
            if len(seen_processes) > 30:
                break
            lines.append(f"- {process_name or 'unknown.exe'} | {title or '(untitled)'}")
        return "\n".join(lines)

    def _notify(self, message: str, timeout_ms: int = 2000) -> None:
        """Show a Windows notification using the configured fallback chain."""
        if self._tray_service is not None:
            self._tray_service.show_notification(
                self.i18n.t("app.title", "MCL - Mouse Control Layer"),
                message,
                QtWidgets.QSystemTrayIcon.Information,
                timeout_ms,
            )
        elif hasattr(self, "_tray_service") and self._tray_service is not None:
            self._tray_service.tray.showMessage(
                self.i18n.t("app.title", "MCL - Mouse Control Layer"),
                message,
                QtWidgets.QSystemTrayIcon.Information,
                timeout_ms,
            )

    def _show_operation_error(self, title: str, message: str, details: Optional[str] = None) -> None:
        """Show a visible error dialog and append the details to the runtime log."""
        full_message = message if not details else f"{message}\n\n{details}"
        log_message(f"{title}: {full_message}")
        QtWidgets.QMessageBox.critical(self, title, full_message)

    def _append_log_path_if_enabled(self, details: str) -> str:
        """Append the current log path only when runtime logging is enabled."""
        if not is_logging_enabled():
            return details
        return f"{details}\n{get_log_path()}"

    def _save_settings_or_warn(self, context: str) -> bool:
        """Persist settings and show/log a clear error if writing fails."""
        if self.settings.save():
            return True
        details = self.settings.last_error or self.i18n.t("error.unknown", "Unknown error")
        self._show_operation_error(
            self.i18n.t("error", "Error"),
            self.i18n.t("settings.save.failed", "Failed to save settings."),
            self._append_log_path_if_enabled(f"{context}\n{details}"),
        )
        return False

    def _set_startup_or_warn(self, enabled: bool) -> bool:
        """Apply startup registration and surface failures immediately."""
        success, error = set_startup_enabled(enabled)
        if success:
            return True
        self._show_operation_error(
            self.i18n.t("error", "Error"),
            self.i18n.t("startup.update.failed", "Failed to update startup registration."),
            self._append_log_path_if_enabled(
                error or self.i18n.t("error.unknown", "Unknown error")
            ),
        )
        return False

    def _register_hotkeys_or_warn(self, errors: list[str]) -> None:
        """Show and log hotkey registration failures."""
        detail = self._build_hotkey_conflict_details(errors)
        log_message(f"Hotkey registration failed:\n{detail}")
        QtWidgets.QMessageBox.warning(
            self,
            self.i18n.t("hotkey.conflict", "Hotkey Conflict"),
            detail,
        )

    def activate_from_external_request(self) -> None:
        """Bring the existing window to the front when another instance requests activation."""
        if self.isMinimized():
            self.showNormal()
        if not self.isVisible():
            self.show()
        self.raise_()
        self.activateWindow()
        self.setWindowState((self.windowState() & ~QtCore.Qt.WindowMinimized) | QtCore.Qt.WindowActive)
        self._update_taskbar_status()

    def _setup_window(self):
        """Configure window properties."""
        self.setWindowTitle(self._WINDOW_DISPLAY_TITLE)
        self.setMinimumSize(*self._MIN_WINDOW_SIZE)
        self.resize(self._resolve_initial_window_size())
        # NOTE: do not mutate windowFlags() here. Changing flags after the
        # window is created makes Qt rebuild the native window, which has been
        # observed to leave the caption CLOSE button visible but unclickable.
        
        # Load window icon
        self._custom_icon = self._load_external_icon()
        icon = self._custom_icon or self._make_icon(False)
        QtWidgets.QApplication.setWindowIcon(icon)
        self.setWindowIcon(icon)

    def _resolve_default_window_size(self) -> QtCore.QSize:
        """Scale the default window from a 1920x1080 baseline."""
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return QtCore.QSize(*self._BASE_WINDOW_SIZE)

        available = screen.availableGeometry()
        scale = screen.devicePixelRatio()
        if scale <= 0:
            scale = 1.0

        effective_width = max(1.0, available.width() * scale)
        effective_height = max(1.0, available.height() * scale)
        width_ratio = effective_width / self._BASE_SCREEN_SIZE[0]
        height_ratio = effective_height / self._BASE_SCREEN_SIZE[1]
        ratio = min(1.0, width_ratio, height_ratio)

        width = int(round(self._BASE_WINDOW_SIZE[0] * ratio))
        height = int(round(self._BASE_WINDOW_SIZE[1] * ratio))

        max_width = max(self._MIN_WINDOW_SIZE[0], int(round(available.width() * 0.9)))
        max_height = max(self._MIN_WINDOW_SIZE[1], int(round(available.height() * 0.9)))
        width = max(self._MIN_WINDOW_SIZE[0], min(width, max_width))
        height = max(self._MIN_WINDOW_SIZE[1], min(height, max_height))
        return QtCore.QSize(width, height)

    def _resolve_initial_window_size(self) -> QtCore.QSize:
        """Use the remembered size when enabled, otherwise derive a scaled default."""
        ui_settings = self.settings.data.get("ui", {})
        if isinstance(ui_settings, dict) and ui_settings.get("rememberWindowSize", False):
            window_size = ui_settings.get("windowSize", {})
            if isinstance(window_size, dict):
                try:
                    width = int(window_size.get("width", 0) or 0)
                    height = int(window_size.get("height", 0) or 0)
                except Exception:
                    width = 0
                    height = 0
                if width > 0 and height > 0:
                    screen = QtWidgets.QApplication.primaryScreen()
                    if screen is not None:
                        available = screen.availableGeometry()
                        width = max(self._MIN_WINDOW_SIZE[0], min(width, max(self._MIN_WINDOW_SIZE[0], int(round(available.width() * 0.9)))))
                        height = max(self._MIN_WINDOW_SIZE[1], min(height, max(self._MIN_WINDOW_SIZE[1], int(round(available.height() * 0.9)))))
                    return QtCore.QSize(width, height)
        return self._resolve_default_window_size()

    def _persist_window_size_if_enabled(self) -> None:
        """Store the current window size when remember-size is enabled."""
        ui_settings = self.settings.data.setdefault("ui", {})
        if not isinstance(ui_settings, dict) or not ui_settings.get("rememberWindowSize", False):
            return
        ui_settings["windowSize"] = {"width": self.width(), "height": self.height()}
        self.settings.save()
    
    def _setup_timers(self):
        """Setup timers for recentering and window focus checking."""
        pass

    def _schedule_live_apply(self):
        """Debounce settings persistence so advanced-page edits take effect immediately."""
        if self._suspend_live_apply > 0:
            return
        self._profile_dirty = True
        self._live_apply_timer.start(120)

    def _apply_live_settings(self):
        """Apply settings after the debounce window."""
        if self._suspend_live_apply > 0:
            return
        self._on_apply(show_feedback=False)

    def _begin_form_update(self):
        """Prevent live-apply recursion while populating widgets."""
        self._suspend_live_apply += 1

    def _end_form_update(self):
        """Resume live apply after populating widgets."""
        if self._suspend_live_apply > 0:
            self._suspend_live_apply -= 1
    
    def _build_ui(self):
        """Build the main UI."""
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        
        layout = QtWidgets.QVBoxLayout(central)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        
        # Mode tabs
        self.modeTabs = QtWidgets.QTabBar()
        self.modeTabs.addTab(self.i18n.t("mode.simple", "Simple"))
        self.modeTabs.addTab(self.i18n.t("mode.advanced", "Advanced"))
        self.modeTabs.currentChanged.connect(self._on_mode_changed)
        layout.addWidget(self.modeTabs)
        
        # Stacked pages
        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self._build_simple_page())
        self.stack.addWidget(self._build_advanced_page())
        layout.addWidget(self.stack)
    
    def _build_simple_page(self) -> QtWidgets.QWidget:
        """Build the simple mode page."""
        return build_simple_page(self)
    
    def _build_advanced_page(self) -> QtWidgets.QWidget:
        """Build the advanced settings page."""
        return build_advanced_page(self)
    
    def _section_label(self, text: str) -> QtWidgets.QLabel:
        """Backward-compatible wrapper for shared section labels."""
        from ui.pages.common import create_section_label
        return create_section_label(text)
    
    def _build_info_card(self, title: str) -> QtWidgets.QFrame:
        """Backward-compatible wrapper for shared info cards."""
        from ui.pages.common import create_info_card
        return create_info_card(title)
    
    def _pick_process(self):
        """Open process picker dialog."""
        dialog = ProcessPickerDialog(self, self.i18n)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            selected = dialog.get_selected_process()
            if selected:
                self.manualInputEdit.setText(selected)

    def _pick_clicker_blacklist_process(self):
        """Pick a foreground process for the clicker blacklist."""
        dialog = ProcessPickerDialog(self, self.i18n)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            selected = dialog.get_selected_process()
            if selected:
                self.clickerBlacklistInputEdit.setText(selected)

    def _open_window_resize(self):
        """Open window resize & center dialog."""
        dialog = WindowResizeDialog(self, self.i18n)
        dialog.exec()

    def _add_target_window(self):
        """Add current input to target list."""
        text = self.manualInputEdit.text().strip()
        if not text:
            return
            
        # Check for duplicates
        items = [self.targetList.item(i).text() for i in range(self.targetList.count())]
        if text in items:
            return
            
        self.targetList.addItem(text)
        self.manualInputEdit.clear()
        self._schedule_live_apply()

    def _remove_target_window(self):
        """Remove selected item from target list."""
        row = self.targetList.currentRow()
        if row >= 0:
            self.targetList.takeItem(row)
            self._schedule_live_apply()

    def _add_clicker_blacklist_process(self):
        """Add current input to the active clicker profile process blacklist."""
        text = self.clickerBlacklistInputEdit.text().strip()
        if not text:
            return

        items = [self.clickerProcessBlacklist.item(i).text() for i in range(self.clickerProcessBlacklist.count())]
        if text in items:
            return

        self.clickerProcessBlacklist.addItem(text)
        self.clickerBlacklistInputEdit.clear()
        self._schedule_live_apply()

    def _remove_clicker_blacklist_process(self):
        """Remove selected process from the active clicker profile blacklist."""
        row = self.clickerProcessBlacklist.currentRow()
        if row >= 0:
            self.clickerProcessBlacklist.takeItem(row)
            self._schedule_live_apply()

    def _on_profile_list_follow_toggled(self, checked: bool):
        """Toggle whether black/white lists follow clicker profile switching."""
        if self._suspend_live_apply > 0:
            return
        binding = self._profile_list_binding()
        if checked:
            binding["followProfile"] = True
            self._profile_dirty = True
            active = self._get_raw_active_clicker_profile()
            self._load_profile_into_form(active)
            self._schedule_live_apply()
            self._notify(self.i18n.t("profile.lists.follow.enabled", "Black/white lists now follow profiles."))
            return

        reply = QtWidgets.QMessageBox.question(
            self,
            self.i18n.t("profile.lists.follow.disable.title", "Freeze black/white lists?"),
            self.i18n.t(
                "profile.lists.follow.disable.message",
                "Current auto-clicker process blacklist and target-window list will be frozen globally. "
                "Profile-stored lists are kept but ignored until you enable following profiles again.",
            ),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            self.profileListFollowCheck.blockSignals(True)
            try:
                self.profileListFollowCheck.setChecked(True)
            finally:
                self.profileListFollowCheck.blockSignals(False)
            return

        snapshot = self._snapshot_profile_lists_from_form()
        binding["followProfile"] = False
        binding["processBlacklist"] = snapshot["processBlacklist"]
        binding["windowSpecific"] = snapshot["windowSpecific"]
        self.settings.data["windowSpecific"] = json.loads(json.dumps(snapshot["windowSpecific"]))
        self._profile_dirty = True
        self._schedule_live_apply()
        self._notify(self.i18n.t("profile.lists.follow.disabled", "Current black/white lists are frozen globally."))

    def _current_profile_form_data(self) -> Dict[str, Any]:
        """Build a clicker profile from the current form controls."""
        profile = collect_clicker_profile_form_data(self)
        if not self._profile_lists_follow_profile():
            raw_profile = self._get_raw_active_clicker_profile()
            profile["processBlacklist"] = json.loads(json.dumps(raw_profile.get("processBlacklist", [])))
            raw_feature_settings = raw_profile.get("featureSettings", {})
            raw_window_specific = raw_feature_settings.get("windowSpecific") if isinstance(raw_feature_settings, dict) else None
            feature_settings = profile.setdefault("featureSettings", {})
            if isinstance(raw_window_specific, dict):
                feature_settings["windowSpecific"] = json.loads(json.dumps(raw_window_specific))
            else:
                feature_settings.pop("windowSpecific", None)
        return profile

    def _current_general_settings_form_data(self) -> Dict[str, Any]:
        """Build a general settings payload from the current form controls."""
        return collect_general_settings_form_data(self)

    def _load_profile_into_form(self, profile: Dict[str, Any]) -> None:
        """Populate clicker controls from a profile."""
        self._apply_profile_feature_settings(profile)
        load_clicker_profile_into_form(self, profile)
        self._load_feature_settings_into_form(profile.get("featureSettings", {}))
        self._begin_form_update()
        try:
            self._apply_frozen_lists_to_runtime_and_form()
            if hasattr(self, "profileListFollowCheck"):
                self.profileListFollowCheck.setChecked(self._profile_lists_follow_profile())
        finally:
            self._end_form_update()

    def _apply_profile_feature_settings(self, profile: Dict[str, Any]) -> None:
        """Apply feature settings stored inside a clicker profile."""
        feature_settings = profile.get("featureSettings", {})
        if not isinstance(feature_settings, dict):
            return
        for key in (
            "recenter",
            "position",
            "mouseMacros",
            "inputBackend",
            "inputMode",
            "fallbackBackend",
            "fallbackPolicy",
        ):
            if key in feature_settings:
                self.settings.data[key] = json.loads(json.dumps(feature_settings[key]))
        if self._profile_lists_follow_profile() and "windowSpecific" in feature_settings:
            self.settings.data["windowSpecific"] = json.loads(json.dumps(feature_settings["windowSpecific"]))
        elif not self._profile_lists_follow_profile():
            self.settings.data["windowSpecific"] = self._frozen_window_specific()

    def _set_combo_data(self, combo, value) -> None:
        """Set a combo box by itemData without emitting change signals."""
        if combo is None:
            return
        combo.blockSignals(True)
        try:
            for i in range(combo.count()):
                if combo.itemData(i) == value:
                    combo.setCurrentIndex(i)
                    break
        finally:
            combo.blockSignals(False)

    def _load_feature_settings_into_form(self, feature_settings: Dict[str, Any]) -> None:
        """Refresh feature controls after switching profiles."""
        if not isinstance(feature_settings, dict) or not hasattr(self, "mouseMacroEnabledCheck"):
            return
        self._begin_form_update()
        try:
            recenter = self.settings.data.get("recenter", {})
            self.recenterCheck.setChecked(bool(recenter.get("enabled", True)))
            self.recenterSpin.setValue(int(recenter.get("intervalMs", 250)))

            self._set_combo_data(getattr(self, "inputBackendCombo", None), self.settings.data.get("inputBackend", "auto"))

            macro_cfg = self.settings.data.get("mouseMacros", {})
            self.mouseMacroEnabledCheck.setChecked(bool(macro_cfg.get("enabled", False)))
            self._set_combo_data(self.mouseMacroSourceCombo, macro_cfg.get("source", "builder"))
            self.mouseMacroConfigFileEdit.setText(str(macro_cfg.get("configFile", "") or ""))
            if hasattr(self, "mouseMacroPanicHotkeyCapture"):
                self.mouseMacroPanicHotkeyCapture.set_hotkey(
                    macro_cfg.get("panicHotkey", {"modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F12"})
                )
            macro_sound = macro_cfg.get("sound", {}) if isinstance(macro_cfg.get("sound", {}), dict) else {}
            start_sound = macro_sound.get("start", {}) if isinstance(macro_sound.get("start", {}), dict) else {}
            stop_sound = macro_sound.get("stop", {}) if isinstance(macro_sound.get("stop", {}), dict) else {}
            if hasattr(self, "mouseMacroStartSoundEnabledCheck"):
                self.mouseMacroStartSoundEnabledCheck.setChecked(bool(start_sound.get("enabled", False)))
                self._set_combo_data(self.mouseMacroStartSoundPresetCombo, start_sound.get("preset", "systemAsterisk"))
                self.mouseMacroStartCustomSoundPathEdit.setText(str(start_sound.get("customFile", "") or ""))
                self.mouseMacroStopSoundEnabledCheck.setChecked(bool(stop_sound.get("enabled", False)))
                self._set_combo_data(self.mouseMacroStopSoundPresetCombo, stop_sound.get("preset", "systemHand"))
                self.mouseMacroStopCustomSoundPathEdit.setText(str(stop_sound.get("customFile", "") or ""))
                self._sync_macro_sound_controls()

            position = self.settings.data.get("position", {})
            self._set_combo_data(getattr(self, "posCombo", None), position.get("mode", "virtualCenter"))
            if hasattr(self, "customXSpin"):
                self.customXSpin.setValue(int(position.get("customX", 0)))
            if hasattr(self, "customYSpin"):
                self.customYSpin.setValue(int(position.get("customY", 0)))

            window_specific = self.settings.data.get("windowSpecific", {})
            if hasattr(self, "windowSpecificCheck"):
                self.windowSpecificCheck.setChecked(bool(window_specific.get("enabled", False)))
            if hasattr(self, "autoLockCheck"):
                self.autoLockCheck.setChecked(bool(window_specific.get("autoLockOnWindowFocus", False)))
            if hasattr(self, "resumeAfterSwitchCheck"):
                self.resumeAfterSwitchCheck.setChecked(bool(window_specific.get("resumeAfterWindowSwitch", False)))
            if hasattr(self, "targetList"):
                self.targetList.clear()
                for win_title in window_specific.get("targetWindows", []):
                    self.targetList.addItem(str(win_title))
            self._sync_mouse_macro_controls()
        finally:
            self._end_form_update()

    def _refresh_clicker_ui(self) -> None:
        """Refresh UI fragments that depend on clicker profile state."""
        self._update_clicker_button()
        self._update_simple_info()
        self._update_tray_meta()
        self._update_taskbar_status()

    def _show_saved_tooltip(self) -> None:
        """Show the standard saved tooltip near the cursor."""
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), self.i18n.t("saved", "Settings saved"), self)

    def _reregister_hotkeys(self) -> None:
        """Re-register global hotkeys after profile-affecting changes."""
        unregister_hotkeys()
        success, errors = register_hotkeys(self.settings.data)
        if not success:
            self._register_hotkeys_or_warn(errors)

    def _refresh_all_runtime_ui(self) -> None:
        """Refresh UI fragments affected by settings apply."""
        self._update_toggle_button()
        self._update_clicker_button()
        self._update_simple_info()
        self._update_tray_meta()
        self._update_taskbar_status()

    def _populate_clicker_profiles(self) -> None:
        """Refresh the profile combo box from settings."""
        if not hasattr(self, "clickerProfileCombo"):
            return

        current_id = self.settings.data.get("activeClickerProfileId", self._selected_profile_id)
        self.clickerProfileCombo.blockSignals(True)
        self.clickerProfileCombo.clear()
        profiles = self.settings.get_clicker_profiles()
        target_index = 0
        for profile in profiles:
            self.clickerProfileCombo.addItem(
                profile.get("name", self.i18n.t("clicker.profile.defaultName", "Default Profile")),
                profile.get("id"),
            )
        for i in range(self.clickerProfileCombo.count()):
            if self.clickerProfileCombo.itemData(i) == current_id:
                target_index = i
                break
        self.clickerProfileCombo.setCurrentIndex(target_index)
        self.clickerProfileCombo.blockSignals(False)
        active = self.settings.set_active_clicker_profile(current_id)
        self._load_profile_into_form(active)

    def _on_clicker_profile_selected(self, _index: int) -> None:
        """Switch the active clicker profile."""
        if self._suspend_live_apply > 0:
            return
        profile_id = self.clickerProfileCombo.currentData()
        previous_id = self._selected_profile_id
        if not self._select_clicker_profile(profile_id):
            self._restore_clicker_profile_combo(previous_id)
            return

    def _select_clicker_profile_from_tray(self, profile_id: str) -> None:
        """Switch the active clicker profile from the tray menu."""
        self._select_clicker_profile(profile_id)

    def _restore_clicker_profile_combo(self, profile_id: str) -> None:
        """Restore profile combo selection without firing switch signals."""
        if not hasattr(self, "clickerProfileCombo"):
            return
        self.clickerProfileCombo.blockSignals(True)
        try:
            for i in range(self.clickerProfileCombo.count()):
                if self.clickerProfileCombo.itemData(i) == profile_id:
                    self.clickerProfileCombo.setCurrentIndex(i)
                    break
        finally:
            self.clickerProfileCombo.blockSignals(False)

    def _select_clicker_profile(self, profile_id: str) -> bool:
        """Select a clicker profile and apply its feature snapshot."""
        previous_id = self._selected_profile_id
        if not profile_id or profile_id == previous_id:
            self._update_tray_meta()
            return True
        if not self._confirm_profile_switch():
            self._restore_clicker_profile_combo(previous_id)
            self._update_tray_meta()
            return False
        active = self._clicker_profile_controller.select_profile(
            profile_id,
            clicker_running=self.clicker_running,
        )
        if active is None:
            self._restore_clicker_profile_combo(previous_id)
            self._update_tray_meta()
            return False
        self._selected_profile_id = active.get("id", "default")
        self._profile_dirty = False
        self._save_settings_or_warn("Applying feature settings from switched profile")
        self._lock_service.sync_runtime()
        self._macro_service.sync_runtime()
        self._clicker_service.sync_runtime()
        self._reregister_hotkeys()
        self._populate_clicker_profiles()
        self._update_tray_meta()
        return True

    def _confirm_profile_switch(self) -> bool:
        """Ask whether to save dirty profile edits before switching profiles."""
        if not self._profile_dirty:
            return True
        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(self.i18n.t("clicker.profile.unsaved.title", "Unsaved profile changes"))
        box.setText(self.i18n.t("clicker.profile.unsaved.message", "Save changes to the current profile before switching?"))
        save_btn = box.addButton(self.i18n.t("save", "Save"), QtWidgets.QMessageBox.AcceptRole)
        discard_btn = box.addButton(self.i18n.t("discard", "Discard"), QtWidgets.QMessageBox.DestructiveRole)
        cancel_btn = box.addButton(self.i18n.t("cancel", "Cancel"), QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(save_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn:
            return False
        if clicked == save_btn:
            self._save_clicker_profile()
        elif clicked == discard_btn:
            self._profile_dirty = False
        return True

    def _save_clicker_profile(self) -> None:
        """Save the currently edited clicker profile."""
        profile = self._clicker_profile_controller.save_profile(self._current_profile_form_data())
        if profile is None:
            return
        self._selected_profile_id = profile.get("id", "default")
        self._profile_dirty = False
        self._reregister_hotkeys()

    def _create_clicker_profile(self) -> None:
        """Create a new clicker profile based on the current editor state."""
        profile = self._clicker_profile_controller.create_profile(
            self.clickerProfileNameEdit.text().strip(),
            self._current_profile_form_data(),
        )
        if profile is None:
            return
        self._selected_profile_id = profile.get("id", "default")
        self._reregister_hotkeys()

    def _delete_clicker_profile(self) -> None:
        """Delete the currently selected clicker profile."""
        active = self._get_active_clicker_profile()
        new_active = self._clicker_profile_controller.delete_profile(
            active.get("id", "default"),
            clicker_running=self.clicker_running,
        )
        if new_active is None:
            return
        self._selected_profile_id = new_active.get("id", "default")
        self._reregister_hotkeys()

    def _show_clicker_profile_more_menu(self) -> None:
        """Show profile file/import/export maintenance actions."""
        menu = QtWidgets.QMenu(self)
        menu.addAction(self.i18n.t("clicker.profile.export", "Export to file..."), self._export_clicker_profile)
        menu.addAction(self.i18n.t("clicker.profile.import", "Import from file..."), self._import_clicker_profile)
        menu.addSeparator()
        menu.addAction(self.i18n.t("clicker.profile.delete", "Delete"), self._delete_clicker_profile)
        menu.addAction(self.i18n.t("clicker.profile.clear", "Clear saved profiles"), self._clear_clicker_profiles)
        menu.exec(self.moreClickerProfileBtn.mapToGlobal(QtCore.QPoint(0, self.moreClickerProfileBtn.height())))

    def _export_clicker_profile(self) -> None:
        """Export the current profile, including feature settings, to a JSON file."""
        profile = self._current_profile_form_data()
        default_name = f"{profile.get('name', 'profile')}.json".replace("/", "-").replace("\\", "-")
        path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            self.i18n.t("clicker.profile.export.title", "Export Profile"),
            default_name,
            self.i18n.t("json.files", "JSON Files (*.json);;All Files (*.*)"),
        )
        if not path:
            return
        try:
            Path(path).write_text(json.dumps(profile, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self._notify(self.i18n.t("clicker.profile.exported", "Profile exported: {0}").format(path))
        except Exception as exc:
            self._show_operation_error(
                self.i18n.t("error", "Error"),
                self.i18n.t("clicker.profile.export.failed", "Failed to export profile."),
                str(exc),
            )

    def _import_clicker_profile(self) -> None:
        """Import a profile JSON file and make it active."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.i18n.t("clicker.profile.import.title", "Import Profile"),
            "",
            self.i18n.t("json.files", "JSON Files (*.json);;All Files (*.*)"),
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Profile JSON must be an object")
            payload["id"] = ""
            profile = self.settings.create_clicker_profile(str(payload.get("name", "") or ""), payload)
            self._populate_clicker_profiles()
            self._selected_profile_id = profile.get("id", "default")
            self._profile_dirty = False
            self._save_settings_or_warn("Importing clicker profile")
            self._reregister_hotkeys()
            self._notify(self.i18n.t("clicker.profile.imported", "Profile imported: {0}").format(profile.get("name", "")))
        except Exception as exc:
            self._show_operation_error(
                self.i18n.t("error", "Error"),
                self.i18n.t("clicker.profile.import.failed", "Failed to import profile."),
                str(exc),
            )

    def _clear_clicker_profiles(self) -> None:
        """Clear saved profiles and return to one default profile."""
        reply = QtWidgets.QMessageBox.question(
            self,
            self.i18n.t("clicker.profile.clear", "Clear saved profiles"),
            self.i18n.t("clicker.profile.clear.confirm", "Delete all saved profiles and reset to the default profile?"),
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
            QtWidgets.QMessageBox.No,
        )
        if reply != QtWidgets.QMessageBox.Yes:
            return
        new_active = self.settings.clear_clicker_profiles()
        self._populate_clicker_profiles()
        self._selected_profile_id = new_active.get("id", "default")
        self._profile_dirty = False
        self._save_settings_or_warn("Clearing clicker profiles")
        self._reregister_hotkeys()

    def _browse_clicker_sound_file(self, event: str = "start") -> None:
        """Select a custom clicker sound file."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.i18n.t("clicker.sound.path.title", "Select Audio File"),
            "",
            self.i18n.t("clicker.sound.path.filter", "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*.*)"),
        )
        if path:
            path_edit = self.clickerStopCustomSoundPathEdit if event == "stop" else self.clickerCustomSoundPathEdit
            preset_combo = self.clickerStopSoundPresetCombo if event == "stop" else self.clickerSoundPresetCombo
            path_edit.setText(path)
            for i in range(preset_combo.count()):
                if preset_combo.itemData(i) == "custom":
                    preset_combo.setCurrentIndex(i)
                    break
            self._sync_clicker_sound_controls()
            self._schedule_live_apply()

    def _preview_clicker_sound(self, event: str = "start") -> None:
        """Preview the currently selected clicker sound."""
        preset_combo = self.clickerStopSoundPresetCombo if event == "stop" else self.clickerSoundPresetCombo
        path_edit = self.clickerStopCustomSoundPathEdit if event == "stop" else self.clickerCustomSoundPathEdit
        sound_config = {"enabled": True, "preset": preset_combo.currentData() or "systemAsterisk", "customFile": path_edit.text().strip()}
        self._clicker_service.play_sound_preview(sound_config)

    def _browse_macro_sound_file(self, event: str = "start") -> None:
        """Select a custom macro sound file."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.i18n.t("clicker.sound.path.title", "Select Audio File"),
            "",
            self.i18n.t("clicker.sound.path.filter", "Audio Files (*.wav *.mp3 *.ogg *.flac);;All Files (*.*)"),
        )
        if not path:
            return
        path_edit = self.mouseMacroStopCustomSoundPathEdit if event == "stop" else self.mouseMacroStartCustomSoundPathEdit
        preset_combo = self.mouseMacroStopSoundPresetCombo if event == "stop" else self.mouseMacroStartSoundPresetCombo
        path_edit.setText(path)
        for i in range(preset_combo.count()):
            if preset_combo.itemData(i) == "custom":
                preset_combo.setCurrentIndex(i)
                break
        self._sync_macro_sound_controls()
        self._schedule_live_apply()

    def _preview_macro_sound(self, event: str = "start") -> None:
        """Preview the currently selected macro sound."""
        preset_combo = self.mouseMacroStopSoundPresetCombo if event == "stop" else self.mouseMacroStartSoundPresetCombo
        path_edit = self.mouseMacroStopCustomSoundPathEdit if event == "stop" else self.mouseMacroStartCustomSoundPathEdit
        self._macro_service.play_sound_preview({
            "enabled": True,
            "preset": preset_combo.currentData() or "systemAsterisk",
            "customFile": path_edit.text().strip(),
        })



    def _describe_mouse_macro_action(self, action: Dict[str, Any]) -> str:
        """Return a compact description for a macro action."""
        action_type = str(action.get("type", "") or "")
        if action_type == "mouseClick":
            try:
                hold_ms = int(action.get("holdMs", 0) or 0)
            except Exception:
                hold_ms = 0
            suffix = f" / {hold_ms}ms" if hold_ms > 0 else ""
            return self.i18n.t("macro.preview.action.mouseClick", "Click {0}").format(action.get("button", "left")) + suffix
        if action_type == "key":
            return self.i18n.t("macro.preview.action.key", "Key {0}").format(action.get("key", "?"))
        if action_type == "keyDown":
            return self.i18n.t("macro.preview.action.keyDown", "Key down {0}").format(action.get("key", "?"))
        if action_type == "keyUp":
            return self.i18n.t("macro.preview.action.keyUp", "Key up {0}").format(action.get("key", "?"))
        if action_type == "mouseDown":
            return self.i18n.t("macro.preview.action.mouseDown", "Mouse down {0}").format(action.get("button", "left"))
        if action_type == "mouseUp":
            return self.i18n.t("macro.preview.action.mouseUp", "Mouse up {0}").format(action.get("button", "left"))
        if action_type == "mouseMove":
            return self.i18n.t("macro.preview.action.mouseMove", "Move to {0},{1}").format(action.get("x", 0), action.get("y", 0))
        if action_type == "mouseMoveRelative":
            return self.i18n.t("macro.preview.action.mouseMoveRelative", "Move by {0},{1}").format(action.get("dx", 0), action.get("dy", 0))
        if action_type == "mouseScroll":
            return self.i18n.t("macro.preview.action.mouseScroll", "Scroll {0},{1}").format(action.get("dx", 0), action.get("dy", action.get("amount", 0)))
        if action_type == "hotkey":
            return self.i18n.t("macro.preview.action.hotkey", "Hotkey {0}").format(format_hotkey_display(action))
        if action_type == "text":
            text = str(action.get("text", "") or "")
            if len(text) > 24:
                text = f"{text[:24]}…"
            return self.i18n.t("macro.preview.action.text", "Text \"{0}\"").format(text)
        if action_type == "delay":
            return self.i18n.t("macro.preview.action.delay", "Delay {0}ms").format(action.get("ms", 0))
        if action_type == "repeat":
            return self.i18n.t("macro.preview.action.repeat", "Repeat x{0}").format(action.get("count", 1))
        return action_type or "?"

    def _macro_preset_label(self, relative_path: str) -> str:
        """Build a readable label for a bundled macro preset."""
        path = resolve_macro_config_path(relative_path)
        fallback_name = Path(relative_path).stem.replace("-", " ")
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
            rules = payload.get("rules", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
            if isinstance(rules, list) and rules and isinstance(rules[0], dict):
                return str(rules[0].get("name") or fallback_name)
        except Exception:
            pass
        return fallback_name

    def _list_mouse_macro_presets(self) -> list[tuple[str, str]]:
        """Return bundled macro JSON presets as (label, relative path)."""
        language = str(self.settings.data.get("language", "zh-Hans") or "zh-Hans")
        presets: list[tuple[str, str]] = []
        seen_languages: set[str] = set()
        seen_paths: set[str] = set()
        for lang in (language, "zh-Hans", "en"):
            if lang in seen_languages:
                continue
            seen_languages.add(lang)
            preset_dir = Path(APP_DIR) / "examples" / "mouse-macros" / lang
            if not preset_dir.exists():
                continue
            for path in sorted(preset_dir.glob("*.json")):
                relative_path = str(Path("examples") / "mouse-macros" / lang / path.name).replace("\\", "/")
                if relative_path in seen_paths:
                    continue
                seen_paths.add(relative_path)
                presets.append((self._macro_preset_label(relative_path), relative_path))
        return presets

    def _select_combo_data(self, combo: QtWidgets.QComboBox, value: str) -> None:
        """Set a combo box by item data without emitting change signals."""
        blocked = combo.blockSignals(True)
        try:
            for index in range(combo.count()):
                if str(combo.itemData(index) or "") == value:
                    combo.setCurrentIndex(index)
                    return
            combo.setCurrentIndex(0)
        finally:
            combo.blockSignals(blocked)

    def _sync_mouse_macro_preset_selection(self) -> None:
        """Keep the bundled-preset selector aligned with the config file edit."""
        if not hasattr(self, "mouseMacroPresetCombo"):
            return
        current = str(self.mouseMacroConfigFileEdit.text() or "").strip()
        current_resolved = ""
        if current:
            try:
                current_resolved = str(resolve_macro_config_path(current).resolve())
            except Exception:
                current_resolved = ""
        selected = ""
        for index in range(1, self.mouseMacroPresetCombo.count()):
            candidate = str(self.mouseMacroPresetCombo.itemData(index) or "")
            if not candidate:
                continue
            if current == candidate:
                selected = candidate
                break
            try:
                if current_resolved and str(resolve_macro_config_path(candidate).resolve()) == current_resolved:
                    selected = candidate
                    break
            except Exception:
                continue
        self._select_combo_data(self.mouseMacroPresetCombo, selected)

    def _build_mouse_macro_file_preview_text(self, file_path: str) -> tuple[bool, str]:
        """Read and validate a macro JSON file, returning preview text."""
        path = file_path.strip()
        if not path:
            return False, self.i18n.t("macro.preview.empty", "Select a JSON file to preview its rules.")
        try:
            with open(path, "r", encoding="utf-8") as file:
                payload = json.load(file)
        except Exception as exc:
            return False, self.i18n.t("macro.preview.invalid", "Invalid JSON or unreadable file: {0}").format(str(exc))

        if isinstance(payload, list):
            rules = payload
        elif isinstance(payload, dict):
            rules = payload.get("rules", [])
        else:
            rules = []
        if not isinstance(rules, list) or not rules:
            return False, self.i18n.t("macro.preview.noRules", "No usable rules array found.")

        lines = [self.i18n.t("macro.preview.valid", "Valid macro JSON: {0} rule(s).").format(len(rules))]
        for index, rule in enumerate(rules[:5], start=1):
            if not isinstance(rule, dict):
                lines.append(f"{index}. ?")
                continue
            hold = rule.get("holdKey") or rule.get("holdMouseButton", "?")
            press = rule.get("pressKey") or rule.get("pressMouseButton", "?")
            toggle_on = rule.get("toggleOnKey") or rule.get("toggleOnMouseButton") or hold
            toggle_off = rule.get("toggleOffKey") or rule.get("toggleOffMouseButton") or toggle_on
            mode = str(rule.get("triggerMode", "hold") or "hold")
            enabled = self.i18n.t("simple.enabled", "Enabled") if rule.get("enabled", False) else self.i18n.t("simple.disabled", "Disabled")
            actions = rule.get("actions", [])
            if not isinstance(actions, list):
                actions = []
            action_text = " → ".join(self._describe_mouse_macro_action(action) for action in actions[:6] if isinstance(action, dict))
            if len(actions) > 6:
                action_text += " → …"
            if mode == "holdLoop":
                trigger_text = self.i18n.t("macro.preview.trigger.holdLoop", "hold {0} loop").format(hold)
            elif mode == "toggleLoop":
                if toggle_off != toggle_on:
                    trigger_text = self.i18n.t(
                        "macro.preview.trigger.toggleLoopOnOff",
                        "press {0} arm loop, press {1} stop",
                    ).format(toggle_on, toggle_off)
                else:
                    trigger_text = self.i18n.t("macro.preview.trigger.toggleLoop", "press {0} toggle loop").format(toggle_on)
                if rule.get("loopWhilePressHeld"):
                    trigger_text += self.i18n.t(
                        "macro.preview.trigger.loopWhilePressHeld",
                        ", while holding {0}",
                    ).format(press)
            elif mode == "toggle":
                if toggle_off != toggle_on:
                    trigger_text = self.i18n.t(
                        "macro.preview.trigger.toggleOnOff",
                        "press {0} arm, press {1} stop; trigger {2}",
                    ).format(toggle_on, toggle_off, press)
                else:
                    trigger_text = self.i18n.t("macro.preview.trigger.toggle", "toggle {0}, then press {1}").format(toggle_on, press)
            else:
                trigger_text = self.i18n.t("macro.preview.trigger.hold", "{0} + {1}").format(hold, press)
            lines.append(f"{index}. {enabled}: {trigger_text} → {action_text or '?'}")
        if len(rules) > 5:
            lines.append(self.i18n.t("macro.preview.more", "...and {0} more rule(s).").format(len(rules) - 5))
        return True, "\n".join(lines)

    def _update_mouse_macro_file_preview(self) -> None:
        """Refresh the external JSON preview without requiring button clicks."""
        if not hasattr(self, "mouseMacroFilePreviewLabel"):
            return
        ok, text = self._build_mouse_macro_file_preview_text(self.mouseMacroConfigFileEdit.text())
        color = "rgba(48, 209, 88, 0.95)" if ok else "rgba(255, 159, 10, 0.95)"
        self.mouseMacroFilePreviewLabel.setStyleSheet(f"color: {color}; font-size: 12px;")
        self.mouseMacroFilePreviewLabel.setText(text)
        self._sync_mouse_macro_preset_selection()

    def _on_mouse_macro_preset_changed(self, _index: int = -1) -> None:
        """Apply a bundled macro preset from the selector."""
        if not hasattr(self, "mouseMacroPresetCombo"):
            return
        preset_path = str(self.mouseMacroPresetCombo.currentData() or "")
        if not preset_path:
            return
        self.mouseMacroConfigFileEdit.setText(preset_path)
        for i in range(self.mouseMacroSourceCombo.count()):
            if self.mouseMacroSourceCombo.itemData(i) == "file":
                self.mouseMacroSourceCombo.setCurrentIndex(i)
                break
        self._sync_mouse_macro_controls()
        self._schedule_live_apply()

    def _reset_mouse_macro_file_selection(self) -> None:
        """Clear external macro JSON selection and return to UI builder mode."""
        self.mouseMacroConfigFileEdit.clear()
        if hasattr(self, "mouseMacroPresetCombo"):
            self._select_combo_data(self.mouseMacroPresetCombo, "")
        for i in range(self.mouseMacroSourceCombo.count()):
            if self.mouseMacroSourceCombo.itemData(i) == "builder":
                self.mouseMacroSourceCombo.setCurrentIndex(i)
                break
        self._sync_mouse_macro_controls()
        self._schedule_live_apply()

    def _browse_mouse_macro_file(self) -> None:
        """Select an external mouse macro JSON file."""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            self.i18n.t("macro.file.title", "Select Macro JSON"),
            "",
            self.i18n.t("macro.file.filter", "JSON Files (*.json);;All Files (*.*)"),
        )
        if path:
            self.mouseMacroConfigFileEdit.setText(path)
            if hasattr(self, "mouseMacroPresetCombo"):
                self._select_combo_data(self.mouseMacroPresetCombo, "")
            for i in range(self.mouseMacroSourceCombo.count()):
                if self.mouseMacroSourceCombo.itemData(i) == "file":
                    self.mouseMacroSourceCombo.setCurrentIndex(i)
                    break
            self._sync_mouse_macro_controls()
            self._schedule_live_apply()

    def _sync_mouse_macro_controls(self):
        """Show controls relevant to builder/file macro mode and action type."""
        if not hasattr(self, "mouseMacroSourceCombo"):
            return
        source = self.mouseMacroSourceCombo.currentData() or "builder"
        builder_visible = source == "builder"
        self.mouseMacroBuilderGroup.setVisible(builder_visible)
        self.mouseMacroConfigFileEdit.setVisible(not builder_visible)
        if hasattr(self, "mouseMacroPresetLabel"):
            self.mouseMacroPresetLabel.setVisible(not builder_visible)
        if hasattr(self, "mouseMacroPresetCombo"):
            self.mouseMacroPresetCombo.setVisible(not builder_visible)
        self.mouseMacroBrowseBtn.setVisible(not builder_visible)
        if hasattr(self, "mouseMacroResetFileBtn"):
            self.mouseMacroResetFileBtn.setVisible(not builder_visible)
        self.mouseMacroFileHint.setVisible(not builder_visible)
        self.mouseMacroFilePreviewLabel.setVisible(not builder_visible)
        self._update_mouse_macro_file_preview()

        action_type = self.mouseMacroActionTypeCombo.currentData() or "hotkey"
        self.mouseMacroActionHotkeyCapture.setVisible(action_type in ("hotkey", "key", "keyDown", "keyUp"))
        self.mouseMacroActionMouseCombo.setVisible(action_type in ("mouseDown", "mouseUp", "mouseClick"))
        self.mouseMacroActionTextEdit.setVisible(action_type == "text")
        self.mouseMacroDelaySpin.setVisible(action_type == "delay")

    def _sync_clicker_trigger_controls(self):
        """Only show trigger inputs relevant to the selected trigger mode."""
        mode = self.clickerTriggerModeCombo.currentData() or "toggle"
        toggle_visible = mode == "toggle"
        hold_key_visible = mode == "holdKey"
        hold_mouse_visible = mode == "holdMouseButton"
        self.clickerToggleHotkeyLabel.setVisible(toggle_visible)
        self.clickerToggleHotkeyCapture.setVisible(toggle_visible)
        self.clickerHoldKeyLabel.setVisible(hold_key_visible)
        self.clickerHoldKeyCapture.setVisible(hold_key_visible)
        self.clickerHoldMouseLabel.setVisible(hold_mouse_visible)
        self.clickerHoldMouseCombo.setVisible(hold_mouse_visible)
        self._sync_clicker_swap_controls()
        self._update_clicker_button()
        self._update_simple_info()

    def _sync_clicker_swap_controls(self):
        """Show only the swap source input matching the selected swap mode."""
        if not hasattr(self, "clickerSwapModeCombo"):
            return
        mode = self.clickerSwapModeCombo.currentData() or "off"
        key_visible = mode == "key"
        mouse_visible = mode == "mouseButton"
        self.clickerSwapKeyLabel.setVisible(key_visible)
        self.clickerSwapKeyCapture.setVisible(key_visible)
        self.clickerSwapMouseLabel.setVisible(mouse_visible)
        self.clickerSwapMouseCombo.setVisible(mouse_visible)

    def _sync_clicker_sound_controls(self):
        """Show the custom sound path only for custom-file mode."""
        preset = self.clickerSoundPresetCombo.currentData() or "systemAsterisk"
        use_custom = preset == "custom"
        enabled = self.clickerSoundEnabledCheck.isChecked()
        self.clickerSoundPresetLabel.setEnabled(enabled)
        self.clickerSoundPresetCombo.setEnabled(enabled)
        self.clickerSoundPreviewBtn.setEnabled(True)
        self.clickerCustomSoundPathEdit.setVisible(enabled and use_custom)
        self.clickerCustomSoundBrowseBtn.setVisible(enabled and use_custom)
        if hasattr(self, "clickerStopSoundPresetCombo"):
            stop_preset = self.clickerStopSoundPresetCombo.currentData() or "systemHand"
            stop_use_custom = stop_preset == "custom"
            stop_enabled = self.clickerStopSoundEnabledCheck.isChecked()
            self.clickerStopSoundPresetLabel.setEnabled(stop_enabled)
            self.clickerStopSoundPresetCombo.setEnabled(stop_enabled)
            self.clickerStopSoundPreviewBtn.setEnabled(True)
            self.clickerStopCustomSoundPathEdit.setVisible(stop_enabled and stop_use_custom)
            self.clickerStopCustomSoundBrowseBtn.setVisible(stop_enabled and stop_use_custom)

    def _sync_macro_sound_controls(self):
        """Show macro custom sound paths only for custom-file mode."""
        if not hasattr(self, "mouseMacroStartSoundPresetCombo"):
            return
        start_enabled = self.mouseMacroStartSoundEnabledCheck.isChecked()
        start_custom = (self.mouseMacroStartSoundPresetCombo.currentData() or "systemAsterisk") == "custom"
        self.mouseMacroStartSoundPresetCombo.setEnabled(start_enabled)
        self.mouseMacroStartSoundPreviewBtn.setEnabled(True)
        self.mouseMacroStartCustomSoundPathEdit.setVisible(start_enabled and start_custom)
        self.mouseMacroStartCustomSoundBrowseBtn.setVisible(start_enabled and start_custom)

        stop_enabled = self.mouseMacroStopSoundEnabledCheck.isChecked()
        stop_custom = (self.mouseMacroStopSoundPresetCombo.currentData() or "systemHand") == "custom"
        self.mouseMacroStopSoundPresetCombo.setEnabled(stop_enabled)
        self.mouseMacroStopSoundPreviewBtn.setEnabled(True)
        self.mouseMacroStopCustomSoundPathEdit.setVisible(stop_enabled and stop_custom)
        self.mouseMacroStopCustomSoundBrowseBtn.setVisible(stop_enabled and stop_custom)
    
    def _on_apply(self, show_feedback: bool = True):
        """Apply and save settings."""
        startup_updated = self._settings_apply_controller.apply(show_feedback=show_feedback)
        if not startup_updated:
            self.startupCheck.blockSignals(True)
            self.startupCheck.setChecked(is_startup_enabled())
            self.startupCheck.blockSignals(False)

    def _on_mode_changed(self, idx: int):
        """Handle mode tab change."""
        self.stack.setCurrentIndex(idx)
    
    # --- Lock/Unlock Logic ---
    def lock(self, manual: bool = False):
        """Lock the cursor to target position."""
        self._lock_service.lock(manual=manual)

    def unlock(self, manual: bool = False):
        """Unlock the cursor."""
        self._lock_service.unlock(manual=manual)
    
    def toggle_lock(self):
        """Toggle lock state."""
        self._lock_service.toggle()
    
    def _on_lock_state_changed(self):
        """Called when lock state changes."""
        self._update_status_badge()
        self._update_simple_info()
        self._update_toggle_button()
        self._update_clicker_button()
        self._update_tray_icon()
        self._update_tray_meta()
        self._update_taskbar_status()

    def _apply_clicker_timer(self):
        """Compatibility wrapper for clicker runtime updates."""
        self._clicker_service.sync_runtime()

    def start_clicker(self, show_message: bool = True, immediate_click: bool = False):
        """Start the auto clicker."""
        self._clicker_service.start(show_message=show_message, immediate_click=immediate_click)

    def stop_clicker(self, show_message: bool = True):
        """Stop the auto clicker."""
        self._clicker_service.stop(show_message=show_message)

    def toggle_clicker(self):
        """Toggle the auto clicker."""
        self._clicker_service.toggle()
    
    # --- UI Updates ---
    def _update_status_badge(self):
        """Update the status badge appearance."""
        text, style = build_status_badge_presentation(
            self.i18n,
            locked=self.locked,
            is_force_lock=self._lock_service.is_force_lock,
            auto_lock_suspended=self._lock_service.auto_lock_suspended,
            window_specific=self.settings.data.get("windowSpecific", {}),
        )
        self.statusBadge.setText(text)
        self.statusBadge.setStyleSheet(style)

    def _update_simple_info(self):
        """Update simple mode information cards."""
        if not hasattr(self, "configLabel") or not hasattr(self, "hotkeysLabel"):
            return

        config_text, hotkeys_text = build_simple_info_text(
            self.i18n,
            settings_data=self.settings.data,
            clicker=self._get_active_clicker_profile(),
            clicker_running=self.clicker_running,
            clicker_presets=CLICKER_PRESETS,
            clicker_trigger_modes=CLICKER_TRIGGER_MODES,
        )
        self.configLabel.setText(config_text)
        self.hotkeysLabel.setText(hotkeys_text)
    
    def _update_toggle_button(self):
        """Update the toggle button text."""
        self.toggleBtn.setText(
            build_toggle_button_text(
                self.i18n,
                locked=self.locked,
                hotkeys=self.settings.data["hotkeys"],
            )
        )

    def _get_clicker_preset_for_interval(self, interval_ms: int) -> str:
        """Resolve the current interval to a preset key when possible."""
        return resolve_clicker_preset(interval_ms, CLICKER_PRESETS)

    def _describe_clicker_preset(self, preset_key: str, interval_ms: int) -> str:
        """Return a short descriptive label for the clicker preset."""
        return describe_clicker_preset(self.i18n, preset_key)

    def _sync_clicker_interval_controls(self):
        """Show the custom interval editor only for the custom preset."""
        if not hasattr(self, "clickerPresetCombo"):
            return

        preset_key = self.clickerPresetCombo.currentData() or "custom"
        interval_ms = self.clickerIntervalSpin.value() if hasattr(self, "clickerIntervalSpin") else 100
        is_custom = preset_key == "custom"

        if hasattr(self, "clickerIntervalLabel"):
            self.clickerIntervalLabel.setVisible(is_custom)
        if hasattr(self, "clickerIntervalSpin"):
            self.clickerIntervalSpin.setVisible(is_custom)
            self.clickerIntervalSpin.setEnabled(is_custom)
        if hasattr(self, "clickerPresetHint"):
            self.clickerPresetHint.setText(self._describe_clicker_preset(preset_key, interval_ms))

    def _on_clicker_preset_changed(self, _index: int = -1):
        """Apply preset interval values and refresh the UI."""
        preset_key = self.clickerPresetCombo.currentData() or "custom"
        preset_interval = CLICKER_PRESETS.get(preset_key)
        if preset_interval is not None:
            self.clickerIntervalSpin.setValue(preset_interval)
        self._sync_clicker_interval_controls()
        self._schedule_live_apply()

    def _update_clicker_button(self):
        """Update the auto clicker button text and enabled state."""
        if not hasattr(self, "clickerBtn"):
            return

        text, enabled = build_clicker_button_presentation(
            self.i18n,
            clicker=self._get_active_clicker_profile(),
            clicker_running=self.clicker_running,
        )
        self.clickerBtn.setText(text)
        self.clickerBtn.setEnabled(enabled)
    
    # --- Theme ---
    def _apply_theme(self):
        """Apply the current theme."""
        theme = self.settings.data.get("theme", "dark")
        self._theme_service.apply(self, theme)
    
    # --- System Tray ---
    def _create_tray(self):
        """Create system tray icon and menu."""
        self._tray_service = TrayService(
            parent=self,
            dynamic_icon_factory=self._make_icon,
            i18n=self.i18n,
            get_locked=lambda: self.locked,
            get_clicker_running=lambda: self.clicker_running,
            get_status=self._get_visual_status,
            get_clicker_profile=self._get_active_clicker_profile,
            get_clicker_profiles=self.settings.get_clicker_profiles,
            get_active_profile_id=lambda: self.settings.data.get("activeClickerProfileId", self._selected_profile_id),
            get_hotkeys=lambda: self.settings.data["hotkeys"],
            on_toggle_lock=self.toggle_lock,
            on_lock=lambda: self.lock(manual=True),
            on_unlock=lambda: self.unlock(manual=True),
            on_toggle_clicker=self.toggle_clicker,
            on_select_profile=self._select_clicker_profile_from_tray,
            on_show_window=self._show_from_tray,
            on_quit=self._quit,
        )
    
    def _make_icon(self, locked: bool, status: str = "") -> QtGui.QIcon:
        """Create the application icon."""
        size = 128
        pm = QtGui.QPixmap(size, size)
        pm.fill(QtCore.Qt.transparent)

        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        base_icon = self._custom_icon
        if base_icon is not None and not base_icon.isNull():
            source = base_icon.pixmap(size, size)
            p.drawPixmap(0, 0, source)
        else:
            # Background circle
            color = QtGui.QColor(46, 204, 113) if locked else QtGui.QColor(10, 132, 255)
            p.setBrush(color)
            p.setPen(QtCore.Qt.NoPen)
            p.drawEllipse(0, 0, size, size)

            # Lock body
            pad = 28
            body = QtCore.QRect(pad, pad + 18, size - 2*pad, size - 2*pad - 18)
            p.setBrush(QtGui.QColor(255, 255, 255))
            p.drawRoundedRect(body, 14, 14)

            # Shackle
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
            pen.setWidth(14)
            p.setPen(pen)
            p.setBrush(QtCore.Qt.NoBrush)
            p.drawArc(size//2 - 30, pad - 6, 60, 48, 0, 180*16)

        p.end()
        return QtGui.QIcon(pm)
    
    def _load_external_icon(self) -> Optional[QtGui.QIcon]:
        """Try to load external icon file."""
        candidates = [
            os.path.join(ASSETS_DIR, "app.ico"),
            os.path.join(ASSETS_DIR, "icon.ico"),
            os.path.join(ASSETS_DIR, "app.png"),
            os.path.join(RUN_DIR, "app.ico"),
        ]
        
        for path in candidates:
            if os.path.exists(path):
                icon = QtGui.QIcon(path)
                if not icon.isNull():
                    return icon
        return None
    
    def _update_tray_icon(self):
        """Update tray icon based on lock state."""
        self._apply_status_icon()
        if self._tray_service is not None:
            self._tray_service.refresh_icon()
    
    def _update_tray_meta(self):
        """Update tray menu information."""
        if self._tray_service is not None:
            self._tray_service.refresh()

    def _update_taskbar_status(self) -> None:
        """Update the Windows taskbar progress indicator as a safety hint."""
        if not hasattr(self, "winId") or self._taskbar_status_service is None:
            return
        hwnd = int(self.winId())
        status = self._get_visual_status()
        self._taskbar_status_service.set_state(hwnd, status)
        self._apply_status_icon(status)
        self._update_window_runtime_title()

    def _flash_taskbar_state(self, state: str) -> None:
        """Temporarily show a taskbar state such as green unlock feedback."""
        taskbar_cfg = self.settings.data.get("taskbar", {})
        if isinstance(taskbar_cfg, dict) and not taskbar_cfg.get("stateFlashEnabled", True):
            return
        try:
            duration_ms = int(taskbar_cfg.get("stateFlashMs", 1000)) if isinstance(taskbar_cfg, dict) else 1000
        except Exception:
            duration_ms = 1000
        duration_ms = max(100, min(10000, duration_ms))
        if not hasattr(self, "winId") or self._taskbar_status_service is None:
            return
        self._taskbar_flash_timer.stop()
        self._taskbar_status_service.set_state(int(self.winId()), state)
        self._taskbar_flash_timer.start(duration_ms)

    def _apply_status_icon(self, status: str | None = None) -> None:
        """Apply the runtime status badge to the window/taskbar icon."""
        status = self._get_visual_status() if status is None else status
        icon = self._make_icon(self.locked, status)
        QtWidgets.QApplication.setWindowIcon(icon)
        self.setWindowIcon(icon)

    def showEvent(self, event):
        """Refresh taskbar status after the window is shown."""
        super().showEvent(event)
        self._update_taskbar_status()
    
    def _show_from_tray(self):
        """Show window from tray."""
        self.activate_from_external_request()
    
    def _quit(self):
        """Quit the application."""
        try:
            self.stop_clicker(show_message=False)
            self._macro_service.stop()
            self._lock_service.release_cursor()
        finally:
            if self._taskbar_status_service is not None:
                self._taskbar_status_service.close()
            unregister_hotkeys()
            release_single_instance()
            QtWidgets.QApplication.quit()
    
    def _reset_close_action(self):
        """Reset the close action to 'ask'."""
        self.settings.data["closeAction"] = "ask"
        if not self._save_settings_or_warn("Resetting close action"):
            return
        QtWidgets.QMessageBox.information(
            self,
            self.i18n.t("settings.reset", "Settings Reset"),
            self.i18n.t("close.action.reset.done", "Close behavior has been reset to 'Ask every time'.")
        )

    def _system_tray_available(self) -> bool:
        """Return whether a system tray exists to hide into."""
        return bool(QtWidgets.QSystemTrayIcon.isSystemTrayAvailable())

    def _minimize_to_tray_or_quit(self, event) -> bool:
        """Hide to tray when possible; otherwise close for real so the X always works."""
        if not self._system_tray_available():
            self.settings.data["closeAction"] = "quit"
            self._persist_window_size_if_enabled()
            event.accept()
            self._quit()
            return False
        event.ignore()
        self.hide()
        return True

    def closeEvent(self, event):
        """Handle window close - minimize to tray or quit."""
        # Shift+Close always quits
        if QtWidgets.QApplication.keyboardModifiers() & QtCore.Qt.ShiftModifier:
            self._persist_window_size_if_enabled()
            event.accept()
            self._quit()
            return

        action = self.settings.data.get("closeAction", "ask")
        
        if action == "ask":
            dialog = CloseActionDialog(self, self.i18n)
            if dialog.exec() == QtWidgets.QDialog.Accepted:
                if dialog.action == "minimize":
                    if self._minimize_to_tray_or_quit(event):
                        self._notify(self.i18n.t("tray.minimized", "Minimized to tray."))
                elif dialog.action == "quit":
                    self._persist_window_size_if_enabled()
                    event.accept()
                    self._quit()
                
                if dialog.dont_ask_again and dialog.action:
                    self.settings.data["closeAction"] = dialog.action
                    if not self._save_settings_or_warn("Saving close action preference"):
                        self.settings.data["closeAction"] = "ask"
            else:
                # Cancelled
                event.ignore()
        elif action == "minimize":
            self._minimize_to_tray_or_quit(event)
        elif action == "quit":
            self._persist_window_size_if_enabled()
            event.accept()
            self._quit()
