"""
Custom widgets for MCL.
Includes Minecraft-style hotkey capture input and enhanced process picker.
"""
from PySide6 import QtCore, QtGui, QtWidgets
from typing import Optional, Dict, Any, Callable


class HotkeyCapture(QtWidgets.QLineEdit):
    """
    Minecraft-style hotkey capture input.
    Click to focus, then press any key combination to capture it.
    """

    hotkeyChanged = QtCore.Signal(dict)  # Emits the new hotkey config

    def __init__(self, parent=None, i18n=None, allow_simple=False):
        super().__init__(parent)
        self.i18n = i18n
        self._allow_simple = bool(allow_simple)
        self._hotkey_config: Dict[str, Any] = {
            "modCtrl": False,
            "modAlt": False,
            "modShift": False,
            "modWin": False,
            "key": ""
        }
        self._is_capturing = False
        
        self.setReadOnly(True)
        self.setAlignment(QtCore.Qt.AlignCenter)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._update_display()
        self._apply_style(False)
    
    def _get_text(self, key: str, fallback: str) -> str:
        """Get translated text or fallback."""
        if self.i18n:
            return self.i18n.t(key, fallback)
        return fallback
    
    def _apply_style(self, capturing: bool):
        """Apply visual style based on capture state."""
        if capturing:
            self.setStyleSheet("""
                QLineEdit {
                    background: #3a3a4a;
                    border: 2px solid #0a84ff;
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: #ffd700;
                    font-weight: bold;
                }
            """)
        else:
            self.setStyleSheet("""
                QLineEdit {
                    background: #2c2c2e;
                    border: 2px solid #48484a;
                    border-radius: 6px;
                    padding: 8px 12px;
                    color: #ebebf5;
                }
                QLineEdit:hover {
                    border-color: #0a84ff;
                }
            """)
    
    def set_hotkey(self, config: Dict[str, Any]):
        """Set the current hotkey configuration."""
        self._hotkey_config = {
            "modCtrl": config.get("modCtrl", False),
            "modAlt": config.get("modAlt", False),
            "modShift": config.get("modShift", False),
            "modWin": config.get("modWin", False),
            "key": config.get("key", "")
        }
        self._update_display()
    
    def get_hotkey(self) -> Dict[str, Any]:
        """Get the current hotkey configuration."""
        return self._hotkey_config.copy()
    
    def _update_display(self):
        """Update the displayed text based on current config."""
        if self._is_capturing:
            self.setText(self._get_text("hotkey.capture.hint", "Press keys..."))
            return
        
        parts = []
        if self._hotkey_config.get("modCtrl"):
            parts.append("Ctrl")
        if self._hotkey_config.get("modAlt"):
            parts.append("Alt")
        if self._hotkey_config.get("modShift"):
            parts.append("Shift")
        if self._hotkey_config.get("modWin"):
            parts.append("Win")
        
        key = self._hotkey_config.get("key", "")
        if key:
            parts.append(key)
        
        if parts:
            self.setText(" + ".join(parts))
        else:
            self.setText(self._get_text("hotkey.capture.click", "Click to set..."))
    
    def mousePressEvent(self, event):
        """Start capturing when clicked."""
        if event.button() == QtCore.Qt.LeftButton:
            self._start_capture()
        super().mousePressEvent(event)
    
    def _start_capture(self):
        """Enter capture mode."""
        self._is_capturing = True
        self._apply_style(True)
        self._update_display()
        self.setFocus()
    
    def _stop_capture(self):
        """Exit capture mode."""
        self._is_capturing = False
        self._apply_style(False)
        self._update_display()
    
    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Capture key press events."""
        if not self._is_capturing:
            return
        
        key = event.key()
        modifiers = event.modifiers()
        
        # Ignore if only modifier keys are pressed
        modifier_keys = {
            QtCore.Qt.Key_Control, QtCore.Qt.Key_Alt, 
            QtCore.Qt.Key_Shift, QtCore.Qt.Key_Meta
        }
        if key in modifier_keys:
            # Update display with current modifiers but don't finalize
            temp_config = {
                "modCtrl": bool(modifiers & QtCore.Qt.ControlModifier),
                "modAlt": bool(modifiers & QtCore.Qt.AltModifier),
                "modShift": bool(modifiers & QtCore.Qt.ShiftModifier),
                "modWin": bool(modifiers & QtCore.Qt.MetaModifier),
                "key": "..."
            }
            self._show_temp_config(temp_config)
            return
        
        # Escape cancels capture
        if key == QtCore.Qt.Key_Escape:
            self._stop_capture()
            return
        
        # Convert Qt key to our key string
        key_str = self._qt_key_to_string(key)
        if not key_str:
            return  # Unsupported key
        
        # Build the new config
        new_config = {
            "modCtrl": bool(modifiers & QtCore.Qt.ControlModifier),
            "modAlt": bool(modifiers & QtCore.Qt.AltModifier),
            "modShift": bool(modifiers & QtCore.Qt.ShiftModifier),
            "modWin": bool(modifiers & QtCore.Qt.MetaModifier),
            "key": key_str
        }
        
        # Check if hotkey is too simple (no modifier)
        has_modifier = any([
            new_config["modCtrl"], new_config["modAlt"],
            new_config["modShift"], new_config["modWin"]
        ])
        
        if not has_modifier and not self._allow_simple:
            # Show warning dialog but still allow the setting
            reply = QtWidgets.QMessageBox.warning(
                self.window() if self.window() else None,
                self._get_text("hotkey.simple.title", "Simple Hotkey Warning"),
                self._get_text("hotkey.simple.message",
                    "Setting a hotkey without Ctrl/Alt/Shift/Win may interfere with normal keyboard use.\n\n"
                    "Are you sure you want to use this hotkey?"),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No
            )
            if reply != QtWidgets.QMessageBox.Yes:
                self._stop_capture()
                return
        
        self._hotkey_config = new_config
        self._stop_capture()
        self.hotkeyChanged.emit(new_config)
    
    def _show_temp_config(self, config: Dict[str, Any]):
        """Show temporary config while capturing."""
        parts = []
        if config.get("modCtrl"):
            parts.append("Ctrl")
        if config.get("modAlt"):
            parts.append("Alt")
        if config.get("modShift"):
            parts.append("Shift")
        if config.get("modWin"):
            parts.append("Win")
        parts.append(config.get("key", "..."))
        self.setText(" + ".join(parts))
    
    def _qt_key_to_string(self, key: int) -> Optional[str]:
        """Convert Qt key code to our key string format."""
        # Letters A-Z
        if QtCore.Qt.Key_A <= key <= QtCore.Qt.Key_Z:
            return chr(key)
        
        # Numbers 0-9
        if QtCore.Qt.Key_0 <= key <= QtCore.Qt.Key_9:
            return chr(key)
        
        # Function keys F1-F24
        if QtCore.Qt.Key_F1 <= key <= QtCore.Qt.Key_F24:
            return f"F{key - QtCore.Qt.Key_F1 + 1}"
        
        # Other common keys
        key_map = {
            QtCore.Qt.Key_Space: "Space",
            QtCore.Qt.Key_Tab: "Tab",
            QtCore.Qt.Key_Return: "Enter",
            QtCore.Qt.Key_Backspace: "Backspace",
            QtCore.Qt.Key_Delete: "Delete",
            QtCore.Qt.Key_Insert: "Insert",
            QtCore.Qt.Key_Home: "Home",
            QtCore.Qt.Key_End: "End",
            QtCore.Qt.Key_PageUp: "PageUp",
            QtCore.Qt.Key_PageDown: "PageDown",
            QtCore.Qt.Key_Up: "Up",
            QtCore.Qt.Key_Down: "Down",
            QtCore.Qt.Key_Left: "Left",
            QtCore.Qt.Key_Right: "Right",
        }
        
        return key_map.get(key)
    
    def focusOutEvent(self, event):
        """Stop capturing when focus is lost."""
        if self._is_capturing:
            self._stop_capture()
        super().focusOutEvent(event)


class ProcessPickerDialog(QtWidgets.QDialog):
    """
    Enhanced process picker dialog with search functionality.
    Similar to Cheat Engine's process list.
    """
    
    def __init__(self, parent=None, i18n=None):
        super().__init__(parent)
        self.i18n = i18n
        self.selected_process: Optional[str] = None
        self._all_processes = []
        
        self._setup_ui()
        self._apply_style()
        self.refresh_processes()
    
    def _t(self, key: str, fallback: str) -> str:
        """Get translated text."""
        if self.i18n:
            return self.i18n.t(key, fallback)
        return fallback
    
    def _setup_ui(self):
        """Setup the dialog UI."""
        self.setWindowTitle(self._t("process.picker.title", "Select Process"))
        self.setMinimumSize(500, 400)
        self.resize(550, 450)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)
        
        # Header label
        header = QtWidgets.QLabel(self._t("process.picker.label", "Select a process to lock the mouse to:"))
        header.setStyleSheet("font-size: 14px; font-weight: 500;")
        layout.addWidget(header)
        
        # Search box
        search_layout = QtWidgets.QHBoxLayout()
        self.searchBox = QtWidgets.QLineEdit()
        self.searchBox.setPlaceholderText(self._t("process.picker.search", "Search..."))
        self.searchBox.textChanged.connect(self._filter_list)
        self.searchBox.setClearButtonEnabled(True)
        search_layout.addWidget(self.searchBox)
        
        self.refreshBtn = QtWidgets.QPushButton(self._t("process.picker.refresh", "Refresh"))
        self.refreshBtn.clicked.connect(self.refresh_processes)
        self.refreshBtn.setFixedWidth(80)
        search_layout.addWidget(self.refreshBtn)
        layout.addLayout(search_layout)
        
        # Process list
        self.processList = QtWidgets.QListWidget()
        self.processList.setAlternatingRowColors(True)
        self.processList.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.processList)
        
        # Buttons
        button_layout = QtWidgets.QHBoxLayout()
        button_layout.addStretch()
        
        self.okBtn = QtWidgets.QPushButton(self._t("process.picker.ok", "OK"))
        self.okBtn.setFixedWidth(80)
        self.okBtn.clicked.connect(self.accept)
        
        self.cancelBtn = QtWidgets.QPushButton(self._t("process.picker.cancel", "Cancel"))
        self.cancelBtn.setFixedWidth(80)
        self.cancelBtn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.okBtn)
        button_layout.addWidget(self.cancelBtn)
        layout.addLayout(button_layout)
    
    def _apply_style(self):
        """Apply dialog styling."""
        self.setStyleSheet("""
            QDialog {
                background: #1c1c1e;
            }
            QLabel {
                color: #ebebf5;
            }
            QLineEdit {
                background: #2c2c2e;
                border: 1px solid #48484a;
                border-radius: 6px;
                padding: 8px;
                color: #ebebf5;
            }
            QLineEdit:focus {
                border-color: #0a84ff;
            }
            QListWidget {
                background: #2c2c2e;
                border: 1px solid #48484a;
                border-radius: 6px;
                color: #ebebf5;
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #3a3a3c;
            }
            QListWidget::item:selected {
                background: #0a84ff;
                color: white;
            }
            QListWidget::item:selected:!active {
                background: #0a60bd; /* Slightly darker when not focused, but still visible */
                color: white;
            }
            QListWidget::item:selected:active {
                background: #0a84ff;
                color: white;
            }
            QListWidget::item:hover {
                background: #3a3a3c;
            }
            QListWidget::item:alternate {
                background: #252527;
            }
            QPushButton {
                background: #0a84ff;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                color: white;
            }
            QPushButton:hover {
                background: #2b95ff;
            }
            QPushButton:pressed {
                background: #0671dd;
            }
        """)
    
    def refresh_processes(self):
        """Refresh the process list."""
        self.processList.clear()
        self._all_processes = []
        
        try:
            from win_api import enumerate_visible_windows
            windows = enumerate_visible_windows()
            
            for hwnd, title, proc_name in windows:
                self._all_processes.append({
                    "hwnd": hwnd,
                    "title": title,
                    "process": proc_name
                })
                
                item = QtWidgets.QListWidgetItem(f"{title}")
                item.setToolTip(f"{proc_name}\n{title}")
                # Store process name as the primary data (UserRole)
                item.setData(QtCore.Qt.UserRole, proc_name)
                # Store title as secondary data
                item.setData(QtCore.Qt.UserRole + 1, title)
                item.setData(QtCore.Qt.UserRole + 2, hwnd)
                self.processList.addItem(item)
        except Exception as e:
            error_item = QtWidgets.QListWidgetItem(f"Error loading processes: {e}")
            self.processList.addItem(error_item)
    
    def _filter_list(self, text: str):
        """Filter the process list based on search text."""
        search_lower = text.lower()
        
        for i in range(self.processList.count()):
            item = self.processList.item(i)
            if search_lower:
                # Check both title and tooltip (which contains process name)
                visible = (search_lower in item.text().lower() or 
                          search_lower in (item.toolTip() or "").lower())
                item.setHidden(not visible)
            else:
                item.setHidden(False)
    
    def get_selected_process(self) -> Optional[str]:
        """Get the selected match text, preferring the process name for stability."""
        item = self.processList.currentItem()
        if item:
            process = item.data(QtCore.Qt.UserRole)
            title = item.data(QtCore.Qt.UserRole + 1)
            return process or title
        return None
    
    def get_selected_hwnd(self) -> Optional[int]:
        """Get the selected window handle."""
        item = self.processList.currentItem()
        if item:
            return item.data(QtCore.Qt.UserRole + 2)
        return None
    
    def accept(self):
        """Handle OK button."""
        self.selected_process = self.get_selected_process()
        if self.selected_process:
            super().accept()


class CloseActionDialog(QtWidgets.QDialog):
    """
    Dialog to ask user whether to minimize to tray or quit.
    """
    
    def __init__(self, parent=None, i18n=None):
        super().__init__(parent)
        self.i18n = i18n
        self.action = None  # "minimize" or "quit"
        self.dont_ask_again = False
        
        self._setup_ui()
        self._apply_style()
    
    def _t(self, key: str, fallback: str) -> str:
        """Get translated text."""
        if self.i18n:
            return self.i18n.t(key, fallback)
        return fallback
    
    def _setup_ui(self):
        self.setWindowTitle(self._t("close.dialog.title", "Close Application"))
        self.setFixedSize(400, 200)
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)
        
        # Message
        msg_label = QtWidgets.QLabel(self._t("close.dialog.message", "How do you want to close the application?"))
        msg_label.setWordWrap(True)
        msg_label.setStyleSheet("font-size: 14px; color: #ebebf5;")
        layout.addWidget(msg_label)
        
        # Options
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.setSpacing(12)
        
        self.minimizeBtn = QtWidgets.QPushButton(self._t("close.dialog.minimize", "Minimize to Tray"))
        self.minimizeBtn.setCursor(QtCore.Qt.PointingHandCursor)
        self.minimizeBtn.setEnabled(QtWidgets.QSystemTrayIcon.isSystemTrayAvailable())
        self.minimizeBtn.clicked.connect(self._on_minimize)
        
        self.quitBtn = QtWidgets.QPushButton(self._t("close.dialog.quit", "Quit Application"))
        self.quitBtn.setCursor(QtCore.Qt.PointingHandCursor)
        self.quitBtn.setStyleSheet("background: #ff453a; color: white;")
        self.quitBtn.clicked.connect(self._on_quit)
        
        btn_layout.addWidget(self.minimizeBtn)
        btn_layout.addWidget(self.quitBtn)
        layout.addLayout(btn_layout)
        
        # Checkbox
        self.dontAskCheck = QtWidgets.QCheckBox(self._t("close.dialog.dontask", "Don't ask again"))
        self.dontAskCheck.setStyleSheet("color: #aeaeb2;")
        layout.addWidget(self.dontAskCheck)
        
    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background: #1c1c1e;
            }
            QPushButton {
                background: #3a3a3c;
                border: none;
                border-radius: 6px;
                padding: 10px 16px;
                color: white;
                font-weight: 500;
                font-size: 13px;
            }
            QPushButton:hover {
                background: #48484a;
            }
        """)

    def _on_minimize(self):
        self.action = "minimize"
        self.dont_ask_again = self.dontAskCheck.isChecked()
        self.accept()
        
    def _on_quit(self):
        self.action = "quit"
        self.dont_ask_again = self.dontAskCheck.isChecked()
        self.accept()


class WindowResizeDialog(QtWidgets.QDialog):
    """Dialog for resizing a window and optionally centering it on screen."""

    PRESETS = [
        ("3840 × 2160  (4K)", 3840, 2160),
        ("2560 × 1440  (2K)", 2560, 1440),
        ("1920 × 1080  (Full HD)", 1920, 1080),
        ("1600 × 900", 1600, 900),
        ("1280 × 720   (HD)", 1280, 720),
        ("1024 × 768", 1024, 768),
        ("800 × 600", 800, 600),
    ]

    def __init__(self, parent=None, i18n=None):
        super().__init__(parent)
        self.i18n = i18n
        self._selected_hwnd = None
        self._windows = []  # list of (hwnd, title, proc_name)
        self._setup_ui()
        self._apply_style()
        self._refresh_windows()

    def _t(self, key: str, fallback: str) -> str:
        """Get translated text."""
        if self.i18n:
            return self.i18n.t(key, fallback)
        return fallback

    def _setup_ui(self):
        self.setWindowTitle(self._t("windowTools.title", "Window Resize & Center"))
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # --- Window Selection ---
        layout.addWidget(QtWidgets.QLabel(self._t("windowTools.selectWindow", "Select Window")))

        # Search box
        self.searchEdit = QtWidgets.QLineEdit()
        self.searchEdit.setPlaceholderText(self._t("process.picker.search", "Search..."))
        self.searchEdit.textChanged.connect(self._filter_list)
        layout.addWidget(self.searchEdit)

        # Window list
        self.windowList = QtWidgets.QListWidget()
        self.windowList.setMinimumHeight(180)
        self.windowList.currentRowChanged.connect(self._on_selection_changed)
        layout.addWidget(self.windowList)

        # Refresh button
        self.refreshBtn = QtWidgets.QPushButton(self._t("process.picker.refresh", "Refresh"))
        self.refreshBtn.clicked.connect(self._refresh_windows)
        layout.addWidget(self.refreshBtn)

        # --- Resolution ---
        layout.addWidget(QtWidgets.QLabel(self._t("windowTools.resolution", "Resolution")))
        self.currentResolutionLabel = QtWidgets.QLabel(
            self._t("windowTools.currentResolution.empty", "Current window resolution: No window selected")
        )
        self.currentResolutionLabel.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
        layout.addWidget(self.currentResolutionLabel)

        # Presets combo
        preset_layout = QtWidgets.QHBoxLayout()
        preset_layout.addWidget(QtWidgets.QLabel(self._t("windowTools.presets", "Presets")))
        self.presetCombo = QtWidgets.QComboBox()
        self.presetCombo.addItem(self._t("windowTools.custom", "Custom"), None)
        for label, w, h in self.PRESETS:
            self.presetCombo.addItem(label, (w, h))
        self.presetCombo.currentIndexChanged.connect(self._on_preset_changed)
        preset_layout.addWidget(self.presetCombo, 1)
        layout.addLayout(preset_layout)

        # Custom size inputs
        size_layout = QtWidgets.QHBoxLayout()
        size_layout.addWidget(QtWidgets.QLabel(self._t("windowTools.width", "Width")))
        self.widthSpin = QtWidgets.QSpinBox()
        self.widthSpin.setRange(100, 7680)
        self.widthSpin.setValue(1600)
        self.widthSpin.setSuffix(" px")
        self.widthSpin.valueChanged.connect(self._on_custom_size_changed)
        size_layout.addWidget(self.widthSpin)

        size_layout.addWidget(QtWidgets.QLabel("×"))

        size_layout.addWidget(QtWidgets.QLabel(self._t("windowTools.height", "Height")))
        self.heightSpin = QtWidgets.QSpinBox()
        self.heightSpin.setRange(100, 4320)
        self.heightSpin.setValue(900)
        self.heightSpin.setSuffix(" px")
        self.heightSpin.valueChanged.connect(self._on_custom_size_changed)
        size_layout.addWidget(self.heightSpin)
        layout.addLayout(size_layout)

        # --- Center Option ---
        self.centerCheck = QtWidgets.QCheckBox(
            self._t("windowTools.centerOnScreen", "Center window on screen")
        )
        self.centerCheck.setChecked(True)
        layout.addWidget(self.centerCheck)

        layout.addStretch()

        # --- Action Buttons ---
        btn_layout = QtWidgets.QHBoxLayout()
        btn_layout.addStretch()

        self.cancelBtn = QtWidgets.QPushButton(self._t("process.picker.cancel", "Cancel"))
        self.cancelBtn.clicked.connect(self.reject)
        btn_layout.addWidget(self.cancelBtn)

        self.applyBtn = QtWidgets.QPushButton(self._t("windowTools.apply", "Apply"))
        self.applyBtn.clicked.connect(self._on_apply)
        self.applyBtn.setEnabled(False)
        btn_layout.addWidget(self.applyBtn)
        layout.addLayout(btn_layout)

    def _apply_style(self):
        self.setStyleSheet("""
            QDialog {
                background: #1c1c1e;
            }
            QLabel {
                color: #ebebf5;
            }
            QLineEdit, QSpinBox {
                background: #2c2c2e;
                border: 1px solid #48484a;
                border-radius: 6px;
                padding: 8px;
                color: #ebebf5;
            }
            QLineEdit:focus, QSpinBox:focus {
                border-color: #0a84ff;
            }
            QComboBox {
                background: #2c2c2e;
                border: 1px solid #48484a;
                border-radius: 6px;
                padding: 6px 10px;
                color: #ebebf5;
                min-height: 28px;
            }
            QComboBox:hover {
                border-color: #636366;
            }
            QComboBox::drop-down {
                border: none;
                width: 24px;
            }
            QComboBox QAbstractItemView {
                background: #2c2c2e;
                border: 1px solid #48484a;
                color: #ebebf5;
                selection-background-color: #0a84ff;
            }
            QListWidget {
                background: #2c2c2e;
                border: 1px solid #48484a;
                border-radius: 6px;
                color: #ebebf5;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-bottom: 1px solid #3a3a3c;
            }
            QListWidget::item:selected {
                background: #0a84ff;
                color: white;
            }
            QListWidget::item:hover {
                background: #3a3a3c;
            }
            QCheckBox {
                color: #ebebf5;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #636366;
                background: #2c2c2e;
            }
            QCheckBox::indicator:checked {
                background: #0a84ff;
                border-color: #0a84ff;
            }
            QPushButton {
                background: #48484a;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                color: white;
            }
            QPushButton:hover {
                background: #636366;
            }
            QPushButton:pressed {
                background: #3a3a3c;
            }
            QPushButton#applyBtn {
                background: #0a84ff;
            }
            QPushButton#applyBtn:hover {
                background: #2b95ff;
            }
            QPushButton#applyBtn:disabled {
                background: #48484a;
                color: #8e8e93;
            }
        """)
        self.applyBtn.setObjectName("applyBtn")

    def _refresh_windows(self):
        from win_api import enumerate_visible_windows
        self._windows = enumerate_visible_windows()
        self._populate_list(self._windows)

    def _populate_list(self, windows):
        self.windowList.clear()
        for hwnd, title, proc_name in windows:
            display = f"[{proc_name}]  {title}"
            item = QtWidgets.QListWidgetItem(display)
            item.setData(QtCore.Qt.UserRole, hwnd)
            self.windowList.addItem(item)

    def _filter_list(self, text: str):
        text = text.lower()
        if not text:
            self._populate_list(self._windows)
        else:
            filtered = [
                (h, t, p) for h, t, p in self._windows
                if text in t.lower() or text in p.lower()
            ]
            self._populate_list(filtered)

    def _on_selection_changed(self, row):
        if row >= 0:
            item = self.windowList.item(row)
            self._selected_hwnd = item.data(QtCore.Qt.UserRole) if item else None
            if self._selected_hwnd:
                from win_api import get_window_client_size

                client_size = get_window_client_size(self._selected_hwnd)
                if client_size is not None:
                    width, height = client_size
                    self._set_current_resolution_text(width, height)
                    self.widthSpin.setValue(width)
                    self.heightSpin.setValue(height)
                    self.presetCombo.blockSignals(True)
                    self.presetCombo.setCurrentIndex(0)
                    for index in range(1, self.presetCombo.count()):
                        if self.presetCombo.itemData(index) == (width, height):
                            self.presetCombo.setCurrentIndex(index)
                            break
                    self.presetCombo.blockSignals(False)
                else:
                    self._set_current_resolution_unavailable()
        else:
            self._selected_hwnd = None
            self.currentResolutionLabel.setText(
                self._t("windowTools.currentResolution.empty", "Current window resolution: No window selected")
            )
        self.applyBtn.setEnabled(self._selected_hwnd is not None)

    def _on_preset_changed(self, index):
        data = self.presetCombo.itemData(index)
        if data is not None:
            w, h = data
            self.widthSpin.blockSignals(True)
            self.heightSpin.blockSignals(True)
            self.widthSpin.setValue(w)
            self.heightSpin.setValue(h)
            self.widthSpin.blockSignals(False)
            self.heightSpin.blockSignals(False)

    def _on_custom_size_changed(self, _value):
        data = self.presetCombo.currentData()
        if data is None:
            return
        current_size = (self.widthSpin.value(), self.heightSpin.value())
        if current_size != data:
            self.presetCombo.blockSignals(True)
            self.presetCombo.setCurrentIndex(0)
            self.presetCombo.blockSignals(False)

    def _set_current_resolution_text(self, width: int, height: int):
        self.currentResolutionLabel.setText(
            self._t("windowTools.currentResolution", "Current window resolution: {0} × {1}").format(width, height)
        )

    def _set_current_resolution_unavailable(self):
        self.currentResolutionLabel.setText(
            self._t("windowTools.currentResolution.unavailable", "Current window resolution: Unavailable")
        )

    def _on_apply(self):
        if not self._selected_hwnd:
            return

        from win_api import get_centered_window_position, get_window_client_size, resize_window

        width = self.widthSpin.value()
        height = self.heightSpin.value()
        center = self.centerCheck.isChecked()
        move_to = None
        if center:
            move_to = get_centered_window_position(
                self._selected_hwnd,
                width,
                height,
                client_size=True,
            )

        success = resize_window(self._selected_hwnd, width, height, move_to=move_to)

        if success:
            client_size = get_window_client_size(self._selected_hwnd)
            if client_size is not None:
                self._set_current_resolution_text(*client_size)
            else:
                self._set_current_resolution_unavailable()
            QtWidgets.QMessageBox.information(
                self,
                self._t("windowTools.title", "Window Resize & Center"),
                self._t("windowTools.success", "Window adjusted successfully!")
            )
            self.accept()
        else:
            QtWidgets.QMessageBox.warning(
                self,
                self._t("error", "Error"),
                self._t("windowTools.error", "Failed to adjust window. The window may have been closed.")
            )
