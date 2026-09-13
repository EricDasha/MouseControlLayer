"""
Advanced page builder.
"""
from PySide6 import QtCore, QtWidgets

from widgets import HotkeyCapture
from ui.pages.common import create_delayed_help_label, create_section_label
from services.macro_schema import MOUSE_BUTTONS, MOUSE_MACRO_TRIGGER_MODES
from win_api import is_startup_enabled


def build_advanced_page(window) -> QtWidgets.QWidget:
    """Build the advanced settings page and attach widgets to the window."""

    page = QtWidgets.QWidget()

    tabs = QtWidgets.QTabWidget()
    root_layout = QtWidgets.QVBoxLayout(page)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.addWidget(tabs)

    def _make_tab(title: str) -> QtWidgets.QVBoxLayout:
        tab = QtWidgets.QWidget()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        tab_layout = QtWidgets.QVBoxLayout(content)
        tab_layout.setContentsMargins(8, 8, 8, 8)
        tab_layout.setSpacing(16)
        scroll.setWidget(content)
        tab_outer = QtWidgets.QVBoxLayout(tab)
        tab_outer.setContentsMargins(0, 0, 0, 0)
        tab_outer.addWidget(scroll)
        tabs.addTab(tab, title)
        return tab_layout

    # Window category: recenter behavior, target position, window-specific locking, window tools
    layout = _make_tab(window.i18n.t("adv.category.window", "Window"))

    layout.addWidget(create_section_label(window.i18n.t("section.behavior", "Behavior")))

    window.recenterCheck = QtWidgets.QCheckBox(window.i18n.t("recenter.enabled", "Enable periodic recentering"))
    window.recenterCheck.setChecked(window.settings.data["recenter"].get("enabled", True))
    window.recenterCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.recenterCheck)

    interval_layout = QtWidgets.QHBoxLayout()
    interval_layout.addWidget(QtWidgets.QLabel(window.i18n.t("recenter.interval", "Interval (ms)")))
    window.recenterSpin = QtWidgets.QSpinBox()
    window.recenterSpin.setRange(16, 5000)
    window.recenterSpin.setSingleStep(16)
    window.recenterSpin.setValue(window.settings.data["recenter"].get("intervalMs", 250))
    window.recenterSpin.valueChanged.connect(lambda _value: window._schedule_live_apply())
    interval_layout.addWidget(window.recenterSpin)
    interval_layout.addStretch()
    layout.addLayout(interval_layout)

    layout.addWidget(create_section_label(window.i18n.t("position.title", "Target Position")))
    pos_layout = QtWidgets.QHBoxLayout()
    window.posCombo = QtWidgets.QComboBox()
    window.posCombo.addItem(window.i18n.t("position.virtualCenter", "Virtual screen center"), "virtualCenter")
    window.posCombo.addItem(window.i18n.t("position.primaryCenter", "Primary screen center"), "primaryCenter")
    window.posCombo.addItem(window.i18n.t("position.custom", "Custom"), "custom")
    window.posCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    current_mode = window.settings.data["position"].get("mode", "virtualCenter")
    for i in range(window.posCombo.count()):
        if window.posCombo.itemData(i) == current_mode:
            window.posCombo.setCurrentIndex(i)
            break
    pos_layout.addWidget(window.posCombo)
    layout.addLayout(pos_layout)

    custom_layout = QtWidgets.QHBoxLayout()
    custom_layout.addWidget(QtWidgets.QLabel("X:"))
    window.customXSpin = QtWidgets.QSpinBox()
    window.customXSpin.setRange(-10000, 10000)
    window.customXSpin.setValue(window.settings.data["position"].get("customX", 0))
    window.customXSpin.valueChanged.connect(lambda _value: window._schedule_live_apply())
    custom_layout.addWidget(window.customXSpin)
    custom_layout.addWidget(QtWidgets.QLabel("Y:"))
    window.customYSpin = QtWidgets.QSpinBox()
    window.customYSpin.setRange(-10000, 10000)
    window.customYSpin.setValue(window.settings.data["position"].get("customY", 0))
    window.customYSpin.valueChanged.connect(lambda _value: window._schedule_live_apply())
    custom_layout.addWidget(window.customYSpin)
    custom_layout.addStretch()
    layout.addLayout(custom_layout)

    layout.addWidget(create_section_label(window.i18n.t("window.specific.title", "Window-Specific Locking")))
    window.windowSpecificCheck = QtWidgets.QCheckBox(
        window.i18n.t("window.specific.enabled", "Enable window-specific locking")
    )
    window.windowSpecificCheck.setChecked(window.settings.data["windowSpecific"].get("enabled", False))
    window.windowSpecificCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.windowSpecificCheck)

    list_layout = QtWidgets.QVBoxLayout()
    list_layout.setSpacing(8)
    list_label = QtWidgets.QLabel(window.i18n.t("window.specific.listLabel", "Target Windows List"))
    list_layout.addWidget(list_label)

    window.targetList = QtWidgets.QListWidget()
    window.targetList.setFixedHeight(120)
    window.targetList.setStyleSheet("""
        QListWidget {
            background: rgba(0, 0, 0, 0.2);
            border: 1px solid rgba(128, 128, 128, 0.3);
            border-radius: 6px;
            padding: 4px;
        }
    """)
    for win_title in window.settings.data["windowSpecific"].get("targetWindows", []):
        window.targetList.addItem(win_title)
    list_layout.addWidget(window.targetList)

    input_layout = QtWidgets.QHBoxLayout()
    window.manualInputEdit = QtWidgets.QLineEdit()
    window.manualInputEdit.setPlaceholderText(window.i18n.t("window.specific.placeholder", "Target window title"))
    input_layout.addWidget(window.manualInputEdit)
    window.pickProcessBtn = QtWidgets.QPushButton(window.i18n.t("window.specific.pick", "Pick Process"))
    window.pickProcessBtn.clicked.connect(window._pick_process)
    input_layout.addWidget(window.pickProcessBtn)
    list_layout.addLayout(input_layout)

    btn_layout = QtWidgets.QHBoxLayout()
    window.addBtn = QtWidgets.QPushButton(window.i18n.t("window.specific.add", "Add"))
    window.addBtn.clicked.connect(window._add_target_window)
    btn_layout.addWidget(window.addBtn)
    window.removeBtn = QtWidgets.QPushButton(window.i18n.t("window.specific.remove", "Remove"))
    window.removeBtn.clicked.connect(window._remove_target_window)
    btn_layout.addWidget(window.removeBtn)
    btn_layout.addStretch()
    list_layout.addLayout(btn_layout)
    layout.addLayout(list_layout)

    window.autoLockCheck = QtWidgets.QCheckBox(
        window.i18n.t("window.specific.autoLock", "Auto lock/unlock on window switch")
    )
    window.autoLockCheck.setChecked(window.settings.data["windowSpecific"].get("autoLockOnWindowFocus", False))
    window.autoLockCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.autoLockCheck)

    window.resumeAfterSwitchCheck = QtWidgets.QCheckBox(
        window.i18n.t("window.specific.resumeAfterSwitch", "Auto re-lock after leaving and re-entering target window (for manual unlock)")
    )
    window.resumeAfterSwitchCheck.setChecked(window.settings.data["windowSpecific"].get("resumeAfterWindowSwitch", False))
    window.resumeAfterSwitchCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.resumeAfterSwitchCheck)

    layout.addWidget(create_section_label(window.i18n.t("section.windowTools", "Window Tools")))
    window.resizeCenterBtn = QtWidgets.QPushButton(window.i18n.t("windowTools.resizeCenter", "Resize & Center Window"))
    window.resizeCenterBtn.setFixedHeight(40)
    window.resizeCenterBtn.setCursor(QtCore.Qt.PointingHandCursor)
    window.resizeCenterBtn.clicked.connect(window._open_window_resize)
    layout.addWidget(window.resizeCenterBtn)

    # Mouse category: input backend, auto clicker, process blacklist, macro
    layout = _make_tab(window.i18n.t("adv.category.mouse", "Mouse"))

    layout.addWidget(create_section_label(window.i18n.t("section.inputOutput", "Input Output")))

    input_backend_layout = QtWidgets.QHBoxLayout()
    input_backend_layout.addWidget(create_delayed_help_label(
        window.i18n.t("inputBackend.title", "Input Backend"),
        window.i18n.t(
            "help.inputBackend",
            "Selects how macro actions are sent to Windows. Auto prefers Native SendInput. This setting controls macro output; the auto clicker has its own backend below.",
        ),
    ))
    window.inputBackendCombo = QtWidgets.QComboBox()
    window.inputBackendCombo.addItem(window.i18n.t("inputBackend.auto", "Auto"), "auto")
    window.inputBackendCombo.addItem(window.i18n.t("inputBackend.nativeSendInput", "Native SendInput"), "native-sendinput")
    window.inputBackendCombo.addItem(window.i18n.t("inputBackend.pythonSendInput", "Python SendInput"), "python-sendinput")
    window.inputBackendCombo.addItem(window.i18n.t("inputBackend.windowMessage", "Window Message"), "window-message")
    window.inputBackendCombo.addItem(window.i18n.t("inputBackend.virtualHid", "Virtual HID (planned)"), "virtual-hid")
    window.inputBackendCombo.addItem(window.i18n.t("inputBackend.hardwareHid", "Hardware HID (planned)"), "hardware-hid")
    current_backend = window.settings.data.get("inputBackend", "auto")
    current_backend = {"sendinput": "native-sendinput", "native-scancode": "native-sendinput", "python-fallback": "python-sendinput"}.get(current_backend, current_backend)
    for i in range(window.inputBackendCombo.count()):
        if window.inputBackendCombo.itemData(i) == current_backend:
            window.inputBackendCombo.setCurrentIndex(i)
            break
    window.inputBackendCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    input_backend_layout.addWidget(window.inputBackendCombo)
    input_backend_layout.addStretch()
    layout.addLayout(input_backend_layout)

    input_backend_hint = QtWidgets.QLabel(
        window.i18n.t(
            "inputBackend.sharedHint",
            "This backend is shared by auto clicker and macro output. If a target ignores instant clicks, try Native SendInput plus mouse down hold, then Window Message.",
        )
    )
    input_backend_hint.setWordWrap(True)
    input_backend_hint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(input_backend_hint)

    layout.addWidget(create_section_label(window.i18n.t("clicker.section", "Auto Clicker")))

    profile_layout = QtWidgets.QHBoxLayout()
    profile_layout.addWidget(QtWidgets.QLabel(window.i18n.t("clicker.profile.select", "Profile")))
    window.clickerProfileCombo = QtWidgets.QComboBox()
    window.clickerProfileCombo.currentIndexChanged.connect(window._on_clicker_profile_selected)
    profile_layout.addWidget(window.clickerProfileCombo)
    layout.addLayout(profile_layout)

    profile_name_layout = QtWidgets.QHBoxLayout()
    profile_name_layout.addWidget(QtWidgets.QLabel(window.i18n.t("clicker.profile.name", "Profile Name")))
    window.clickerProfileNameEdit = QtWidgets.QLineEdit()
    window.clickerProfileNameEdit.setPlaceholderText(window.i18n.t("clicker.profile.placeholder", "Input a profile name"))
    window.clickerProfileNameEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    profile_name_layout.addWidget(window.clickerProfileNameEdit)
    layout.addLayout(profile_name_layout)

    profile_btn_layout = QtWidgets.QHBoxLayout()
    window.newClickerProfileBtn = QtWidgets.QPushButton(window.i18n.t("clicker.profile.new", "New"))
    window.newClickerProfileBtn.clicked.connect(window._create_clicker_profile)
    profile_btn_layout.addWidget(window.newClickerProfileBtn)
    window.saveClickerProfileBtn = QtWidgets.QPushButton(window.i18n.t("clicker.profile.save", "Save Profile"))
    window.saveClickerProfileBtn.clicked.connect(window._save_clicker_profile)
    profile_btn_layout.addWidget(window.saveClickerProfileBtn)
    window.moreClickerProfileBtn = QtWidgets.QPushButton(window.i18n.t("clicker.profile.more", "More"))
    window.moreClickerProfileBtn.clicked.connect(window._show_clicker_profile_more_menu)
    profile_btn_layout.addWidget(window.moreClickerProfileBtn)
    profile_btn_layout.addStretch()
    layout.addLayout(profile_btn_layout)

    window.clickerEnabledCheck = QtWidgets.QCheckBox(window.i18n.t("clicker.enabled", "Enable auto clicker"))
    window.clickerEnabledCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.clickerEnabledCheck)

    clicker_button_layout = QtWidgets.QHBoxLayout()
    clicker_button_layout.addWidget(QtWidgets.QLabel(window.i18n.t("clicker.button", "Click Button")))
    window.clickerButtonCombo = QtWidgets.QComboBox()
    window.clickerButtonCombo.addItem(window.i18n.t("clicker.button.left", "Left Click"), "left")
    window.clickerButtonCombo.addItem(window.i18n.t("clicker.button.right", "Right Click"), "right")
    window.clickerButtonCombo.addItem(window.i18n.t("clicker.button.middle", "Middle Click"), "middle")
    window.clickerButtonCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    clicker_button_layout.addWidget(window.clickerButtonCombo)
    clicker_button_layout.addStretch()
    layout.addLayout(clicker_button_layout)

    clicker_backend_layout = QtWidgets.QHBoxLayout()
    clicker_backend_layout.addWidget(create_delayed_help_label(
        window.i18n.t("clicker.inputBackend", "Clicker Backend"),
        window.i18n.t(
            "help.clickerBackend",
            "Chooses how this clicker profile sends mouse input. Auto uses Native SendInput when available. Window Message targets the foreground window but is not accepted by every game.",
        ),
    ))
    window.clickerInputBackendCombo = QtWidgets.QComboBox()
    window.clickerInputBackendCombo.addItem(window.i18n.t("inputBackend.auto", "Auto"), "auto")
    window.clickerInputBackendCombo.addItem(window.i18n.t("inputBackend.nativeSendInput", "Native SendInput"), "native-sendinput")
    window.clickerInputBackendCombo.addItem(window.i18n.t("inputBackend.pythonSendInput", "Python SendInput"), "python-sendinput")
    window.clickerInputBackendCombo.addItem(window.i18n.t("inputBackend.windowMessage", "Window Message"), "window-message")
    window.clickerInputBackendCombo.addItem(window.i18n.t("inputBackend.virtualHid", "Virtual HID (planned)"), "virtual-hid")
    window.clickerInputBackendCombo.addItem(window.i18n.t("inputBackend.hardwareHid", "Hardware HID (planned)"), "hardware-hid")
    window.clickerInputBackendCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    clicker_backend_layout.addWidget(window.clickerInputBackendCombo)
    clicker_backend_layout.addStretch()
    layout.addLayout(clicker_backend_layout)

    clicker_preset_layout = QtWidgets.QHBoxLayout()
    clicker_preset_layout.addWidget(create_delayed_help_label(
        window.i18n.t("clicker.preset", "Click Speed"),
        window.i18n.t(
            "help.clickerPreset",
            "Speed presets only fill in a click interval. Choose Custom when you want to enter the interval yourself.",
        ),
    ))
    window.clickerPresetCombo = QtWidgets.QComboBox()
    window.clickerPresetCombo.addItem(window.i18n.t("clicker.preset.efficient", "Efficient Mode"), "efficient")
    window.clickerPresetCombo.addItem(window.i18n.t("clicker.preset.extreme", "Extreme Mode"), "extreme")
    window.clickerPresetCombo.addItem(window.i18n.t("clicker.preset.custom", "Custom"), "custom")
    window.clickerPresetCombo.currentIndexChanged.connect(window._on_clicker_preset_changed)
    clicker_preset_layout.addWidget(window.clickerPresetCombo)
    clicker_preset_layout.addStretch()
    layout.addLayout(clicker_preset_layout)

    window.clickerPresetHint = QtWidgets.QLabel()
    window.clickerPresetHint.setWordWrap(True)
    window.clickerPresetHint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(window.clickerPresetHint)

    clicker_interval_layout = QtWidgets.QHBoxLayout()
    window.clickerIntervalLabel = create_delayed_help_label(
        window.i18n.t("clicker.interval", "Click Interval (ms)"),
        window.i18n.t(
            "help.clickerInterval",
            "Time from the start of one click to the start of the next. 100ms means up to 10 click cycles per second. The mouse-down hold occupies part of this period.",
        ),
    )
    clicker_interval_layout.addWidget(window.clickerIntervalLabel)
    window.clickerIntervalSpin = QtWidgets.QSpinBox()
    window.clickerIntervalSpin.setRange(1, 5000)
    window.clickerIntervalSpin.setSingleStep(10)
    window.clickerIntervalSpin.setSuffix(" ms")
    window.clickerIntervalSpin.valueChanged.connect(lambda _value: window._schedule_live_apply())
    clicker_interval_layout.addWidget(window.clickerIntervalSpin)
    clicker_interval_layout.addStretch()
    layout.addLayout(clicker_interval_layout)

    clicker_hold_layout = QtWidgets.QHBoxLayout()
    clicker_hold_layout.addWidget(create_delayed_help_label(
        window.i18n.t("clicker.holdMs", "Mouse down hold (ms)"),
        window.i18n.t(
            "help.clickerHoldMs",
            "How long each click stays pressed before release. 0 uses automatic timing: about half of the click interval, limited to 8-50ms. Increase it for games that miss short clicks or weapons that fire on release.",
        ),
    ))
    window.clickerHoldMsSpin = QtWidgets.QSpinBox()
    window.clickerHoldMsSpin.setRange(0, 1000)
    window.clickerHoldMsSpin.setSingleStep(1)
    window.clickerHoldMsSpin.setSuffix(" ms")
    window.clickerHoldMsSpin.setToolTip(window.i18n.t(
        "clicker.holdMs.tooltip",
        "Each click is sent as down -> hold -> up. 0 uses an automatic 50% duty cycle (8-50ms); at a 100ms interval this means 50ms down and 50ms released."
    ))
    window.clickerHoldMsSpin.valueChanged.connect(lambda _value: window._schedule_live_apply())
    clicker_hold_layout.addWidget(window.clickerHoldMsSpin)
    clicker_hold_layout.addStretch()
    layout.addLayout(clicker_hold_layout)

    trigger_mode_layout = QtWidgets.QHBoxLayout()
    trigger_mode_layout.addWidget(create_delayed_help_label(
        window.i18n.t("clicker.trigger.mode", "Trigger Mode"),
        window.i18n.t(
            "help.clickerTriggerMode",
            "Toggle starts or stops with one hotkey press. Hold Key runs only while a keyboard key is held. Hold Mouse Button runs only while the selected mouse button is held.",
        ),
    ))
    window.clickerTriggerModeCombo = QtWidgets.QComboBox()
    window.clickerTriggerModeCombo.addItem(window.i18n.t("clicker.trigger.toggle", "Toggle"), "toggle")
    window.clickerTriggerModeCombo.addItem(window.i18n.t("clicker.trigger.holdKey", "Hold Key"), "holdKey")
    window.clickerTriggerModeCombo.addItem(window.i18n.t("clicker.trigger.holdMouseButton", "Hold Mouse Button"), "holdMouseButton")
    window.clickerTriggerModeCombo.currentIndexChanged.connect(window._sync_clicker_trigger_controls)
    window.clickerTriggerModeCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    trigger_mode_layout.addWidget(window.clickerTriggerModeCombo)
    trigger_mode_layout.addStretch()
    layout.addLayout(trigger_mode_layout)

    toggle_hotkey_layout = QtWidgets.QHBoxLayout()
    window.clickerToggleHotkeyLabel = QtWidgets.QLabel(window.i18n.t("clicker.hotkey", "Auto Clicker Toggle"))
    toggle_hotkey_layout.addWidget(window.clickerToggleHotkeyLabel)
    window.clickerToggleHotkeyCapture = HotkeyCapture(i18n=window.i18n)
    window.clickerToggleHotkeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    toggle_hotkey_layout.addWidget(window.clickerToggleHotkeyCapture)
    layout.addLayout(toggle_hotkey_layout)

    hold_key_layout = QtWidgets.QHBoxLayout()
    window.clickerHoldKeyLabel = QtWidgets.QLabel(window.i18n.t("clicker.trigger.holdKey.input", "Hold Key"))
    hold_key_layout.addWidget(window.clickerHoldKeyLabel)
    window.clickerHoldKeyCapture = HotkeyCapture(i18n=window.i18n)
    window.clickerHoldKeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    hold_key_layout.addWidget(window.clickerHoldKeyCapture)
    layout.addLayout(hold_key_layout)

    hold_mouse_layout = QtWidgets.QHBoxLayout()
    window.clickerHoldMouseLabel = QtWidgets.QLabel(window.i18n.t("clicker.trigger.holdMouseButton.input", "Hold Mouse Button"))
    hold_mouse_layout.addWidget(window.clickerHoldMouseLabel)
    window.clickerHoldMouseCombo = QtWidgets.QComboBox()
    window.clickerHoldMouseCombo.addItem(window.i18n.t("clicker.mouse.middle", "Middle Button"), "middle")
    window.clickerHoldMouseCombo.addItem(window.i18n.t("clicker.mouse.x1", "Side Button X1 (usually Back)"), "x1")
    window.clickerHoldMouseCombo.addItem(window.i18n.t("clicker.mouse.x2", "Side Button X2 (usually Forward)"), "x2")
    window.clickerHoldMouseCombo.addItem(window.i18n.t("clicker.mouse.left", "Left Button"), "left")
    window.clickerHoldMouseCombo.addItem(window.i18n.t("clicker.mouse.right", "Right Button"), "right")
    window.clickerHoldMouseCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    hold_mouse_layout.addWidget(window.clickerHoldMouseCombo)
    hold_mouse_layout.addStretch()
    layout.addLayout(hold_mouse_layout)

    swap_mode_layout = QtWidgets.QHBoxLayout()
    swap_mode_layout.addWidget(create_delayed_help_label(
        window.i18n.t("clicker.swap.mode", "Swap Click Button"),
        window.i18n.t(
            "help.clickerSwapMode",
            "While the selected key or mouse button is held, the clicker swaps its button: left becomes right and right becomes left. Release it to restore the configured button.",
        ),
    ))
    window.clickerSwapModeCombo = QtWidgets.QComboBox()
    window.clickerSwapModeCombo.addItem(window.i18n.t("clicker.swap.off", "Disabled"), "off")
    window.clickerSwapModeCombo.addItem(window.i18n.t("clicker.swap.key", "Keyboard Shortcut"), "key")
    window.clickerSwapModeCombo.addItem(window.i18n.t("clicker.swap.mouseButton", "Mouse Button"), "mouseButton")
    window.clickerSwapModeCombo.currentIndexChanged.connect(window._sync_clicker_swap_controls)
    window.clickerSwapModeCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    swap_mode_layout.addWidget(window.clickerSwapModeCombo)
    swap_mode_layout.addStretch()
    layout.addLayout(swap_mode_layout)

    swap_key_layout = QtWidgets.QHBoxLayout()
    window.clickerSwapKeyLabel = QtWidgets.QLabel(window.i18n.t("clicker.swap.key.input", "Hold Shortcut"))
    swap_key_layout.addWidget(window.clickerSwapKeyLabel)
    window.clickerSwapKeyCapture = HotkeyCapture(i18n=window.i18n, allow_simple=True)
    window.clickerSwapKeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    swap_key_layout.addWidget(window.clickerSwapKeyCapture)
    layout.addLayout(swap_key_layout)

    swap_mouse_layout = QtWidgets.QHBoxLayout()
    window.clickerSwapMouseLabel = QtWidgets.QLabel(window.i18n.t("clicker.swap.mouseButton.input", "Hold Mouse Button"))
    swap_mouse_layout.addWidget(window.clickerSwapMouseLabel)
    window.clickerSwapMouseCombo = QtWidgets.QComboBox()
    window.clickerSwapMouseCombo.addItem(window.i18n.t("clicker.mouse.x1", "Side Button X1 (usually Back)"), "x1")
    window.clickerSwapMouseCombo.addItem(window.i18n.t("clicker.mouse.x2", "Side Button X2 (usually Forward)"), "x2")
    window.clickerSwapMouseCombo.addItem(window.i18n.t("clicker.mouse.middle", "Middle Button"), "middle")
    window.clickerSwapMouseCombo.addItem(window.i18n.t("clicker.mouse.left", "Left Button"), "left")
    window.clickerSwapMouseCombo.addItem(window.i18n.t("clicker.mouse.right", "Right Button"), "right")
    window.clickerSwapMouseCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    swap_mouse_layout.addWidget(window.clickerSwapMouseCombo)
    swap_mouse_layout.addStretch()
    layout.addLayout(swap_mouse_layout)

    swap_hint = QtWidgets.QLabel(
        window.i18n.t(
            "clicker.swap.hint",
            "Hold the swap source while the clicker runs to temporarily switch the clicked button between left and right.",
        )
    )
    swap_hint.setWordWrap(True)
    swap_hint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(swap_hint)

    sound_enabled_layout = QtWidgets.QHBoxLayout()
    window.clickerSoundEnabledCheck = QtWidgets.QCheckBox(window.i18n.t("clicker.sound.start.enabled", "Play start sound"))
    window.clickerSoundEnabledCheck.toggled.connect(window._sync_clicker_sound_controls)
    window.clickerSoundEnabledCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    sound_enabled_layout.addWidget(window.clickerSoundEnabledCheck)
    sound_enabled_layout.addStretch()
    layout.addLayout(sound_enabled_layout)

    sound_preset_layout = QtWidgets.QHBoxLayout()
    window.clickerSoundPresetLabel = QtWidgets.QLabel(window.i18n.t("clicker.sound.start.preset", "Start Sound"))
    sound_preset_layout.addWidget(window.clickerSoundPresetLabel)
    window.clickerSoundPresetCombo = QtWidgets.QComboBox()
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.systemAsterisk", "System Asterisk"), "systemAsterisk")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.systemExclamation", "System Exclamation"), "systemExclamation")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.systemQuestion", "System Question"), "systemQuestion")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.systemHand", "System Hand"), "systemHand")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.win10Notify", "Windows 10 Notify"), "win10Notify")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.win10Ding", "Windows 10 Ding"), "win10Ding")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.win10Chimes", "Windows 10 Chimes"), "win10Chimes")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.win11Notify", "Windows 11 Notify"), "win11Notify")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.win11Ding", "Windows 11 Ding"), "win11Ding")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.win11Chimes", "Windows 11 Chimes"), "win11Chimes")
    window.clickerSoundPresetCombo.addItem(window.i18n.t("clicker.sound.preset.custom", "Custom File"), "custom")
    window.clickerSoundPresetCombo.currentIndexChanged.connect(window._sync_clicker_sound_controls)
    window.clickerSoundPresetCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    sound_preset_layout.addWidget(window.clickerSoundPresetCombo)
    window.clickerSoundPreviewBtn = QtWidgets.QPushButton(window.i18n.t("clicker.sound.preview", "Preview"))
    window.clickerSoundPreviewBtn.clicked.connect(window._preview_clicker_sound)
    sound_preset_layout.addWidget(window.clickerSoundPreviewBtn)
    sound_preset_layout.addStretch()
    layout.addLayout(sound_preset_layout)

    custom_sound_layout = QtWidgets.QHBoxLayout()
    window.clickerCustomSoundPathEdit = QtWidgets.QLineEdit()
    window.clickerCustomSoundPathEdit.setPlaceholderText(window.i18n.t("clicker.sound.path.placeholder", "Select a local audio file"))
    window.clickerCustomSoundPathEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    custom_sound_layout.addWidget(window.clickerCustomSoundPathEdit)
    window.clickerCustomSoundBrowseBtn = QtWidgets.QPushButton(window.i18n.t("browse", "Browse"))
    window.clickerCustomSoundBrowseBtn.clicked.connect(window._browse_clicker_sound_file)
    custom_sound_layout.addWidget(window.clickerCustomSoundBrowseBtn)
    layout.addLayout(custom_sound_layout)

    stop_sound_enabled_layout = QtWidgets.QHBoxLayout()
    window.clickerStopSoundEnabledCheck = QtWidgets.QCheckBox(window.i18n.t("clicker.sound.stop.enabled", "Play stop sound"))
    window.clickerStopSoundEnabledCheck.toggled.connect(window._sync_clicker_sound_controls)
    window.clickerStopSoundEnabledCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    stop_sound_enabled_layout.addWidget(window.clickerStopSoundEnabledCheck)
    stop_sound_enabled_layout.addStretch()
    layout.addLayout(stop_sound_enabled_layout)

    stop_sound_preset_layout = QtWidgets.QHBoxLayout()
    window.clickerStopSoundPresetLabel = QtWidgets.QLabel(window.i18n.t("clicker.sound.stop.preset", "Stop Sound"))
    stop_sound_preset_layout.addWidget(window.clickerStopSoundPresetLabel)
    window.clickerStopSoundPresetCombo = QtWidgets.QComboBox()
    for key in (
        "systemAsterisk", "systemExclamation", "systemQuestion", "systemHand",
        "win10Notify", "win10Ding", "win10Chimes", "win11Notify", "win11Ding", "win11Chimes", "custom",
    ):
        window.clickerStopSoundPresetCombo.addItem(window.i18n.t(f"clicker.sound.preset.{key}", key), key)
    window.clickerStopSoundPresetCombo.currentIndexChanged.connect(window._sync_clicker_sound_controls)
    window.clickerStopSoundPresetCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    stop_sound_preset_layout.addWidget(window.clickerStopSoundPresetCombo)
    window.clickerStopSoundPreviewBtn = QtWidgets.QPushButton(window.i18n.t("clicker.sound.preview", "Preview"))
    window.clickerStopSoundPreviewBtn.clicked.connect(lambda: window._preview_clicker_sound("stop"))
    stop_sound_preset_layout.addWidget(window.clickerStopSoundPreviewBtn)
    stop_sound_preset_layout.addStretch()
    layout.addLayout(stop_sound_preset_layout)

    stop_custom_sound_layout = QtWidgets.QHBoxLayout()
    window.clickerStopCustomSoundPathEdit = QtWidgets.QLineEdit()
    window.clickerStopCustomSoundPathEdit.setPlaceholderText(window.i18n.t("clicker.sound.path.placeholder", "Select a local audio file"))
    window.clickerStopCustomSoundPathEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    stop_custom_sound_layout.addWidget(window.clickerStopCustomSoundPathEdit)
    window.clickerStopCustomSoundBrowseBtn = QtWidgets.QPushButton(window.i18n.t("browse", "Browse"))
    window.clickerStopCustomSoundBrowseBtn.clicked.connect(lambda: window._browse_clicker_sound_file("stop"))
    stop_custom_sound_layout.addWidget(window.clickerStopCustomSoundBrowseBtn)
    layout.addLayout(stop_custom_sound_layout)

    list_binding = window.settings.data.get("profileListBinding", {})
    if not isinstance(list_binding, dict):
        list_binding = {}
    window.profileListFollowCheck = QtWidgets.QCheckBox(
        window.i18n.t("profile.lists.follow", "Follow profile for clicker blacklist and target windows")
    )
    window.profileListFollowCheck.setChecked(bool(list_binding.get("followProfile", True)))
    window.profileListFollowCheck.toggled.connect(window._on_profile_list_follow_toggled)
    layout.addWidget(window.profileListFollowCheck)
    profile_list_follow_hint = QtWidgets.QLabel(
        window.i18n.t(
            "profile.lists.follow.hint",
            "On: profile switches load each profile's blacklist and target-window list. "
            "Off: current lists are frozen globally; profile copies are kept and restored when re-enabled.",
        )
    )
    profile_list_follow_hint.setWordWrap(True)
    profile_list_follow_hint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(profile_list_follow_hint)

    layout.addWidget(create_section_label(window.i18n.t("clicker.blacklist.title", "Auto Clicker Process Blacklist")))
    blacklist_hint = QtWidgets.QLabel(
        window.i18n.t(
            "clicker.blacklist.hint",
            "Auto clicker will not start or click while the foreground process matches this list."
        )
    )
    blacklist_hint.setWordWrap(True)
    blacklist_hint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(blacklist_hint)

    window.clickerProcessBlacklist = QtWidgets.QListWidget()
    window.clickerProcessBlacklist.setFixedHeight(96)
    window.clickerProcessBlacklist.setStyleSheet("""
        QListWidget {
            background: #2c2c2e;
            border: 1px solid #48484a;
            border-radius: 6px;
            color: #ebebf5;
            padding: 4px;
        }
    """)
    layout.addWidget(window.clickerProcessBlacklist)

    blacklist_input_layout = QtWidgets.QHBoxLayout()
    window.clickerBlacklistInputEdit = QtWidgets.QLineEdit()
    window.clickerBlacklistInputEdit.setPlaceholderText(
        window.i18n.t("clicker.blacklist.placeholder", "Process name, e.g. steam.exe")
    )
    blacklist_input_layout.addWidget(window.clickerBlacklistInputEdit)
    window.pickClickerBlacklistProcessBtn = QtWidgets.QPushButton(window.i18n.t("window.specific.pick", "Pick Process"))
    window.pickClickerBlacklistProcessBtn.clicked.connect(window._pick_clicker_blacklist_process)
    blacklist_input_layout.addWidget(window.pickClickerBlacklistProcessBtn)
    layout.addLayout(blacklist_input_layout)

    blacklist_btn_layout = QtWidgets.QHBoxLayout()
    window.addClickerBlacklistBtn = QtWidgets.QPushButton(window.i18n.t("window.specific.add", "Add"))
    window.addClickerBlacklistBtn.clicked.connect(window._add_clicker_blacklist_process)
    blacklist_btn_layout.addWidget(window.addClickerBlacklistBtn)
    window.removeClickerBlacklistBtn = QtWidgets.QPushButton(window.i18n.t("window.specific.remove", "Remove"))
    window.removeClickerBlacklistBtn.clicked.connect(window._remove_clicker_blacklist_process)
    blacklist_btn_layout.addWidget(window.removeClickerBlacklistBtn)
    blacklist_btn_layout.addStretch()
    layout.addLayout(blacklist_btn_layout)

    window.clickerConfigHint = QtWidgets.QLabel(
        window.i18n.t(
            "clicker.config.hint",
            "Restore defaults by deleting Mconfig.json. Legacy config.json is still read for compatibility."
        )
    )
    window.clickerConfigHint.setWordWrap(True)
    window.clickerConfigHint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(window.clickerConfigHint)
    window._populate_clicker_profiles()

    layout.addWidget(create_section_label(window.i18n.t("macro.section", "Macro")))

    macro_cfg = window.settings.data.get("mouseMacros", {})
    macro_rules = macro_cfg.get("rules", []) if isinstance(macro_cfg.get("rules", []), list) else []
    macro_rule = macro_rules[0] if macro_rules else {}
    macro_actions = macro_rule.get("actions", []) if isinstance(macro_rule.get("actions", []), list) else []
    macro_action = macro_actions[0] if macro_actions else {"type": "hotkey", "modCtrl": True, "key": "C"}

    window.mouseMacroEnabledCheck = QtWidgets.QCheckBox(window.i18n.t("macro.enabled", "Enable macro"))
    window.mouseMacroEnabledCheck.setChecked(bool(macro_cfg.get("enabled", False)))
    window.mouseMacroEnabledCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.mouseMacroEnabledCheck)

    macro_sound = macro_cfg.get("sound", {}) if isinstance(macro_cfg.get("sound", {}), dict) else {}
    macro_start_sound = macro_sound.get("start", {}) if isinstance(macro_sound.get("start", {}), dict) else {}
    macro_stop_sound = macro_sound.get("stop", {}) if isinstance(macro_sound.get("stop", {}), dict) else {}

    macro_sound_layout = QtWidgets.QGridLayout()
    macro_sound_layout.setHorizontalSpacing(8)
    macro_sound_layout.setVerticalSpacing(6)
    window.mouseMacroStartSoundEnabledCheck = QtWidgets.QCheckBox(window.i18n.t("macro.sound.start.enabled", "Play macro start sound"))
    window.mouseMacroStartSoundEnabledCheck.setChecked(bool(macro_start_sound.get("enabled", False)))
    window.mouseMacroStartSoundEnabledCheck.toggled.connect(window._sync_macro_sound_controls)
    window.mouseMacroStartSoundEnabledCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    macro_sound_layout.addWidget(window.mouseMacroStartSoundEnabledCheck, 0, 0)
    window.mouseMacroStartSoundPresetCombo = QtWidgets.QComboBox()
    for key in (
        "systemAsterisk", "systemExclamation", "systemQuestion", "systemHand",
        "win10Notify", "win10Ding", "win10Chimes", "win11Notify", "win11Ding", "win11Chimes", "custom",
    ):
        window.mouseMacroStartSoundPresetCombo.addItem(window.i18n.t(f"clicker.sound.preset.{key}", key), key)
    for i in range(window.mouseMacroStartSoundPresetCombo.count()):
        if window.mouseMacroStartSoundPresetCombo.itemData(i) == macro_start_sound.get("preset", "systemAsterisk"):
            window.mouseMacroStartSoundPresetCombo.setCurrentIndex(i)
            break
    window.mouseMacroStartSoundPresetCombo.currentIndexChanged.connect(window._sync_macro_sound_controls)
    window.mouseMacroStartSoundPresetCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    macro_sound_layout.addWidget(window.mouseMacroStartSoundPresetCombo, 0, 1)
    window.mouseMacroStartSoundPreviewBtn = QtWidgets.QPushButton(window.i18n.t("clicker.sound.preview", "Preview"))
    window.mouseMacroStartSoundPreviewBtn.clicked.connect(lambda: window._preview_macro_sound("start"))
    macro_sound_layout.addWidget(window.mouseMacroStartSoundPreviewBtn, 0, 2)
    window.mouseMacroStartCustomSoundPathEdit = QtWidgets.QLineEdit(str(macro_start_sound.get("customFile", "") or ""))
    window.mouseMacroStartCustomSoundPathEdit.setPlaceholderText(window.i18n.t("clicker.sound.path.placeholder", "Select a local audio file"))
    window.mouseMacroStartCustomSoundPathEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    macro_sound_layout.addWidget(window.mouseMacroStartCustomSoundPathEdit, 1, 1)
    window.mouseMacroStartCustomSoundBrowseBtn = QtWidgets.QPushButton(window.i18n.t("browse", "Browse"))
    window.mouseMacroStartCustomSoundBrowseBtn.clicked.connect(lambda: window._browse_macro_sound_file("start"))
    macro_sound_layout.addWidget(window.mouseMacroStartCustomSoundBrowseBtn, 1, 2)

    window.mouseMacroStopSoundEnabledCheck = QtWidgets.QCheckBox(window.i18n.t("macro.sound.stop.enabled", "Play macro stop sound"))
    window.mouseMacroStopSoundEnabledCheck.setChecked(bool(macro_stop_sound.get("enabled", False)))
    window.mouseMacroStopSoundEnabledCheck.toggled.connect(window._sync_macro_sound_controls)
    window.mouseMacroStopSoundEnabledCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    macro_sound_layout.addWidget(window.mouseMacroStopSoundEnabledCheck, 2, 0)
    window.mouseMacroStopSoundPresetCombo = QtWidgets.QComboBox()
    for key in (
        "systemAsterisk", "systemExclamation", "systemQuestion", "systemHand",
        "win10Notify", "win10Ding", "win10Chimes", "win11Notify", "win11Ding", "win11Chimes", "custom",
    ):
        window.mouseMacroStopSoundPresetCombo.addItem(window.i18n.t(f"clicker.sound.preset.{key}", key), key)
    for i in range(window.mouseMacroStopSoundPresetCombo.count()):
        if window.mouseMacroStopSoundPresetCombo.itemData(i) == macro_stop_sound.get("preset", "systemHand"):
            window.mouseMacroStopSoundPresetCombo.setCurrentIndex(i)
            break
    window.mouseMacroStopSoundPresetCombo.currentIndexChanged.connect(window._sync_macro_sound_controls)
    window.mouseMacroStopSoundPresetCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    macro_sound_layout.addWidget(window.mouseMacroStopSoundPresetCombo, 2, 1)
    window.mouseMacroStopSoundPreviewBtn = QtWidgets.QPushButton(window.i18n.t("clicker.sound.preview", "Preview"))
    window.mouseMacroStopSoundPreviewBtn.clicked.connect(lambda: window._preview_macro_sound("stop"))
    macro_sound_layout.addWidget(window.mouseMacroStopSoundPreviewBtn, 2, 2)
    window.mouseMacroStopCustomSoundPathEdit = QtWidgets.QLineEdit(str(macro_stop_sound.get("customFile", "") or ""))
    window.mouseMacroStopCustomSoundPathEdit.setPlaceholderText(window.i18n.t("clicker.sound.path.placeholder", "Select a local audio file"))
    window.mouseMacroStopCustomSoundPathEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    macro_sound_layout.addWidget(window.mouseMacroStopCustomSoundPathEdit, 3, 1)
    window.mouseMacroStopCustomSoundBrowseBtn = QtWidgets.QPushButton(window.i18n.t("browse", "Browse"))
    window.mouseMacroStopCustomSoundBrowseBtn.clicked.connect(lambda: window._browse_macro_sound_file("stop"))
    macro_sound_layout.addWidget(window.mouseMacroStopCustomSoundBrowseBtn, 3, 2)
    layout.addLayout(macro_sound_layout)
    window._sync_macro_sound_controls()

    panic_layout = QtWidgets.QHBoxLayout()
    panic_layout.addWidget(QtWidgets.QLabel(window.i18n.t("macro.panicHotkey", "Panic Stop")))
    window.mouseMacroPanicHotkeyCapture = HotkeyCapture(i18n=window.i18n)
    window.mouseMacroPanicHotkeyCapture.set_hotkey(
        macro_cfg.get("panicHotkey", {"modCtrl": False, "modAlt": False, "modShift": False, "modWin": False, "key": "F12"})
    )
    window.mouseMacroPanicHotkeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    panic_layout.addWidget(window.mouseMacroPanicHotkeyCapture)
    panic_hint = QtWidgets.QLabel(window.i18n.t("macro.panicHotkey.hint", "Default F12. Press it to force-stop running/toggled macro actions and release held outputs."))
    panic_hint.setWordWrap(True)
    panic_hint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    panic_layout.addWidget(panic_hint, 1)
    layout.addLayout(panic_layout)

    macro_source_layout = QtWidgets.QHBoxLayout()
    macro_source_layout.addWidget(QtWidgets.QLabel(window.i18n.t("macro.source", "Rule Source")))
    window.mouseMacroSourceCombo = QtWidgets.QComboBox()
    window.mouseMacroSourceCombo.addItem(window.i18n.t("macro.source.builder", "Build in UI"), "builder")
    window.mouseMacroSourceCombo.addItem(window.i18n.t("macro.source.file", "External JSON file"), "file")
    for i in range(window.mouseMacroSourceCombo.count()):
        if window.mouseMacroSourceCombo.itemData(i) == macro_cfg.get("source", "builder"):
            window.mouseMacroSourceCombo.setCurrentIndex(i)
            break
    window.mouseMacroSourceCombo.currentIndexChanged.connect(window._sync_mouse_macro_controls)
    window.mouseMacroSourceCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    macro_source_layout.addWidget(window.mouseMacroSourceCombo)
    macro_source_layout.addStretch()
    layout.addLayout(macro_source_layout)

    preset_layout = QtWidgets.QHBoxLayout()
    window.mouseMacroPresetLabel = QtWidgets.QLabel(window.i18n.t("macro.preset", "Built-in Macro"))
    preset_layout.addWidget(window.mouseMacroPresetLabel)
    window.mouseMacroPresetCombo = QtWidgets.QComboBox()
    window.mouseMacroPresetCombo.addItem(window.i18n.t("macro.preset.custom", "Custom / Manual path"), "")
    for label, preset_path in window._list_mouse_macro_presets():
        window.mouseMacroPresetCombo.addItem(label, preset_path)
    preset_layout.addWidget(window.mouseMacroPresetCombo)
    preset_layout.addStretch()
    layout.addLayout(preset_layout)

    file_layout = QtWidgets.QHBoxLayout()
    window.mouseMacroConfigFileEdit = QtWidgets.QLineEdit(str(macro_cfg.get("configFile", "") or ""))
    window.mouseMacroConfigFileEdit.setPlaceholderText(window.i18n.t("macro.file.placeholder", "Select macro JSON file"))
    window.mouseMacroConfigFileEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    window.mouseMacroConfigFileEdit.textChanged.connect(lambda _text: window._update_mouse_macro_file_preview())
    file_layout.addWidget(window.mouseMacroConfigFileEdit)
    window.mouseMacroBrowseBtn = QtWidgets.QPushButton(window.i18n.t("browse", "Browse"))
    window.mouseMacroBrowseBtn.clicked.connect(window._browse_mouse_macro_file)
    file_layout.addWidget(window.mouseMacroBrowseBtn)
    window.mouseMacroResetFileBtn = QtWidgets.QPushButton(window.i18n.t("macro.file.reset", "Reset"))
    window.mouseMacroResetFileBtn.setToolTip(window.i18n.t("macro.file.reset.tooltip", "Clear the selected macro JSON and return to UI builder mode."))
    window.mouseMacroResetFileBtn.clicked.connect(window._reset_mouse_macro_file_selection)
    file_layout.addWidget(window.mouseMacroResetFileBtn)
    layout.addLayout(file_layout)
    window.mouseMacroPresetCombo.currentIndexChanged.connect(window._on_mouse_macro_preset_changed)

    window.mouseMacroFileHint = QtWidgets.QLabel(window.i18n.t(
        "macro.file.hint",
        "JSON supports {\"rules\":[{\"holdMouseButton\":\"x2\",\"pressMouseButton\":\"left\",\"actions\":[{\"type\":\"hotkey\",\"modCtrl\":true,\"key\":\"C\"}]}]}"
    ))
    window.mouseMacroFileHint.setWordWrap(True)
    window.mouseMacroFileHint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(window.mouseMacroFileHint)

    window.mouseMacroFilePreviewLabel = QtWidgets.QLabel()
    window.mouseMacroFilePreviewLabel.setWordWrap(True)
    window.mouseMacroFilePreviewLabel.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
    window.mouseMacroFilePreviewLabel.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(window.mouseMacroFilePreviewLabel)

    window.mouseMacroBuilderGroup = QtWidgets.QGroupBox(window.i18n.t("macro.builder", "Builder Rule"))
    builder_layout = QtWidgets.QVBoxLayout(window.mouseMacroBuilderGroup)

    window.mouseMacroRuleEnabledCheck = QtWidgets.QCheckBox(window.i18n.t("macro.rule.enabled", "Enable this rule"))
    window.mouseMacroRuleEnabledCheck.setChecked(bool(macro_rule.get("enabled", False)))
    window.mouseMacroRuleEnabledCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    builder_layout.addWidget(window.mouseMacroRuleEnabledCheck)

    name_layout = QtWidgets.QHBoxLayout()
    name_layout.addWidget(QtWidgets.QLabel(window.i18n.t("macro.name", "Rule Name")))
    window.mouseMacroNameEdit = QtWidgets.QLineEdit(str(macro_rule.get("name", "X2 + Left") or ""))
    window.mouseMacroNameEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    name_layout.addWidget(window.mouseMacroNameEdit)
    builder_layout.addLayout(name_layout)

    trigger_mode_layout = QtWidgets.QHBoxLayout()
    trigger_mode_layout.addWidget(QtWidgets.QLabel(window.i18n.t("macro.triggerMode", "Trigger Mode")))
    window.mouseMacroTriggerModeCombo = QtWidgets.QComboBox()
    trigger_labels = {
        "hold": window.i18n.t("macro.trigger.hold", "Hold"),
        "toggle": window.i18n.t("macro.trigger.toggle", "Toggle"),
        "holdLoop": window.i18n.t("macro.trigger.holdLoop", "Hold Loop"),
        "toggleLoop": window.i18n.t("macro.trigger.toggleLoop", "Toggle Loop"),
    }
    for trigger_mode in MOUSE_MACRO_TRIGGER_MODES:
        window.mouseMacroTriggerModeCombo.addItem(trigger_labels.get(trigger_mode, trigger_mode), trigger_mode)
    for i in range(window.mouseMacroTriggerModeCombo.count()):
        if window.mouseMacroTriggerModeCombo.itemData(i) == macro_rule.get("triggerMode", "hold"):
            window.mouseMacroTriggerModeCombo.setCurrentIndex(i)
            break
    window.mouseMacroTriggerModeCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    trigger_mode_layout.addWidget(window.mouseMacroTriggerModeCombo)
    trigger_mode_layout.addStretch()
    builder_layout.addLayout(trigger_mode_layout)

    combo_layout = QtWidgets.QHBoxLayout()
    combo_layout.addWidget(QtWidgets.QLabel(window.i18n.t("macro.when", "When holding")))
    window.mouseMacroHoldCombo = QtWidgets.QComboBox()
    window.mouseMacroPressCombo = QtWidgets.QComboBox()
    for combo in (window.mouseMacroHoldCombo, window.mouseMacroPressCombo):
        button_labels = {
            "x1": window.i18n.t("clicker.mouse.x1", "Side Button X1 (usually Back)"),
            "x2": window.i18n.t("clicker.mouse.x2", "Side Button X2 (usually Forward)"),
            "left": window.i18n.t("clicker.mouse.left", "Left Button"),
            "right": window.i18n.t("clicker.mouse.right", "Right Button"),
            "middle": window.i18n.t("clicker.mouse.middle", "Middle Button"),
        }
        for button_key in MOUSE_BUTTONS:
            combo.addItem(button_labels.get(button_key, button_key), button_key)
        combo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    for i in range(window.mouseMacroHoldCombo.count()):
        if window.mouseMacroHoldCombo.itemData(i) == macro_rule.get("holdMouseButton", "x2"):
            window.mouseMacroHoldCombo.setCurrentIndex(i)
            break
    for i in range(window.mouseMacroPressCombo.count()):
        if window.mouseMacroPressCombo.itemData(i) == macro_rule.get("pressMouseButton", "left"):
            window.mouseMacroPressCombo.setCurrentIndex(i)
            break
    combo_layout.addWidget(window.mouseMacroHoldCombo)
    combo_layout.addWidget(QtWidgets.QLabel(window.i18n.t("macro.then.press", "then pressing")))
    combo_layout.addWidget(window.mouseMacroPressCombo)
    builder_layout.addLayout(combo_layout)

    action_layout = QtWidgets.QHBoxLayout()
    action_layout.addWidget(QtWidgets.QLabel(window.i18n.t("macro.action", "Action")))
    window.mouseMacroActionTypeCombo = QtWidgets.QComboBox()
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.hotkey", "Hotkey"), "hotkey")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.key", "Key"), "key")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.keyDown", "Key Down"), "keyDown")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.keyUp", "Key Up"), "keyUp")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.mouseDown", "Mouse Down"), "mouseDown")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.mouseUp", "Mouse Up"), "mouseUp")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.mouseClick", "Mouse Click"), "mouseClick")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.text", "Type Text"), "text")
    window.mouseMacroActionTypeCombo.addItem(window.i18n.t("macro.action.delay", "Delay"), "delay")
    for i in range(window.mouseMacroActionTypeCombo.count()):
        if window.mouseMacroActionTypeCombo.itemData(i) == macro_action.get("type", "hotkey"):
            window.mouseMacroActionTypeCombo.setCurrentIndex(i)
            break
    window.mouseMacroActionTypeCombo.currentIndexChanged.connect(window._sync_mouse_macro_controls)
    window.mouseMacroActionTypeCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    action_layout.addWidget(window.mouseMacroActionTypeCombo)
    window.mouseMacroActionHotkeyCapture = HotkeyCapture(i18n=window.i18n)
    window.mouseMacroActionHotkeyCapture.set_hotkey(macro_action)
    window.mouseMacroActionHotkeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    action_layout.addWidget(window.mouseMacroActionHotkeyCapture)
    window.mouseMacroActionMouseCombo = QtWidgets.QComboBox()
    for button_key in ("left", "right", "middle", "x1", "x2"):
        window.mouseMacroActionMouseCombo.addItem(window.i18n.t(f"clicker.mouse.{button_key}", button_key), button_key)
    for i in range(window.mouseMacroActionMouseCombo.count()):
        if window.mouseMacroActionMouseCombo.itemData(i) == macro_action.get("button", "left"):
            window.mouseMacroActionMouseCombo.setCurrentIndex(i)
            break
    window.mouseMacroActionMouseCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    action_layout.addWidget(window.mouseMacroActionMouseCombo)
    builder_layout.addLayout(action_layout)

    text_layout = QtWidgets.QHBoxLayout()
    window.mouseMacroActionTextEdit = QtWidgets.QLineEdit(str(macro_action.get("text", "") or ""))
    window.mouseMacroActionTextEdit.setPlaceholderText(window.i18n.t("macro.text.placeholder", "Text to type"))
    window.mouseMacroActionTextEdit.textChanged.connect(lambda _text: window._schedule_live_apply())
    text_layout.addWidget(window.mouseMacroActionTextEdit)
    window.mouseMacroDelaySpin = QtWidgets.QSpinBox()
    window.mouseMacroDelaySpin.setRange(0, 60000)
    window.mouseMacroDelaySpin.setSuffix(" ms")
    window.mouseMacroDelaySpin.setValue(int(macro_action.get("ms", 100)))
    window.mouseMacroDelaySpin.valueChanged.connect(lambda _value: window._schedule_live_apply())
    text_layout.addWidget(window.mouseMacroDelaySpin)
    builder_layout.addLayout(text_layout)
    layout.addWidget(window.mouseMacroBuilderGroup)
    window._sync_mouse_macro_controls()

    # Shortcuts & General category: global hotkeys, application settings
    layout = _make_tab(window.i18n.t("adv.category.general", "Shortcuts & General"))

    layout.addWidget(create_section_label(window.i18n.t("section.hotkeys", "Hotkeys")))

    hotkey_grid = QtWidgets.QGridLayout()
    hotkey_grid.setSpacing(12)

    hotkey_grid.addWidget(QtWidgets.QLabel(window.i18n.t("hotkey.lock", "Lock")), 0, 0)
    window.lockHotkeyCapture = HotkeyCapture(i18n=window.i18n)
    window.lockHotkeyCapture.set_hotkey(window.settings.data["hotkeys"]["lock"])
    window.lockHotkeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    hotkey_grid.addWidget(window.lockHotkeyCapture, 0, 1)

    hotkey_grid.addWidget(QtWidgets.QLabel(window.i18n.t("hotkey.unlock", "Unlock")), 1, 0)
    window.unlockHotkeyCapture = HotkeyCapture(i18n=window.i18n)
    window.unlockHotkeyCapture.set_hotkey(window.settings.data["hotkeys"]["unlock"])
    window.unlockHotkeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    hotkey_grid.addWidget(window.unlockHotkeyCapture, 1, 1)

    hotkey_grid.addWidget(QtWidgets.QLabel(window.i18n.t("hotkey.toggle", "Toggle")), 2, 0)
    window.toggleHotkeyCapture = HotkeyCapture(i18n=window.i18n)
    window.toggleHotkeyCapture.set_hotkey(window.settings.data["hotkeys"]["toggle"])
    window.toggleHotkeyCapture.hotkeyChanged.connect(lambda _cfg: window._schedule_live_apply())
    hotkey_grid.addWidget(window.toggleHotkeyCapture, 2, 1)

    hotkey_hint = QtWidgets.QLabel(
        window.i18n.t("clicker.hotkey.profileHint", "Auto clicker trigger keys are configured per clicker profile below.")
    )
    hotkey_hint.setWordWrap(True)
    hotkey_hint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    hotkey_grid.addWidget(hotkey_hint, 3, 0, 1, 2)
    layout.addLayout(hotkey_grid)

    layout.addWidget(create_section_label(window.i18n.t("section.settings", "Settings")))
    lang_layout = QtWidgets.QHBoxLayout()
    lang_layout.addWidget(QtWidgets.QLabel(window.i18n.t("language.title", "Language")))
    window.langCombo = QtWidgets.QComboBox()
    window.langCombo.addItem("English", "en")
    window.langCombo.addItem("简体中文", "zh-Hans")
    window.langCombo.addItem("繁體中文", "zh-Hant")
    window.langCombo.addItem("日本語", "ja")
    window.langCombo.addItem("한국어", "ko")
    current_lang = window.settings.data.get("language", "zh-Hans")
    for i in range(window.langCombo.count()):
        if window.langCombo.itemData(i) == current_lang:
            window.langCombo.setCurrentIndex(i)
            break
    lang_layout.addWidget(window.langCombo)
    window.langCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    lang_layout.addStretch()
    layout.addLayout(lang_layout)

    theme_layout = QtWidgets.QHBoxLayout()
    theme_layout.addWidget(QtWidgets.QLabel(window.i18n.t("theme.title", "Theme")))
    window.themeCombo = QtWidgets.QComboBox()
    window.themeCombo.addItem(window.i18n.t("theme.dark", "Dark"), "dark")
    window.themeCombo.addItem(window.i18n.t("theme.light", "Light"), "light")
    current_theme = window.settings.data.get("theme", "dark")
    for i in range(window.themeCombo.count()):
        if window.themeCombo.itemData(i) == current_theme:
            window.themeCombo.setCurrentIndex(i)
            break
    theme_layout.addWidget(window.themeCombo)
    window.themeCombo.currentIndexChanged.connect(lambda _index: window._schedule_live_apply())
    theme_layout.addStretch()
    layout.addLayout(theme_layout)

    window.restartRequiredHint = QtWidgets.QLabel(
        window.i18n.t(
            "settings.restartRequired",
            "Language and some interface text require restarting the app to fully refresh.",
        )
    )
    window.restartRequiredHint.setWordWrap(True)
    window.restartRequiredHint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(window.restartRequiredHint)

    window.rememberWindowSizeCheck = QtWidgets.QCheckBox(
        window.i18n.t("window.size.remember", "Remember last window size")
    )
    window.rememberWindowSizeCheck.setChecked(window.settings.data.get("ui", {}).get("rememberWindowSize", False))
    window.rememberWindowSizeCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.rememberWindowSizeCheck)

    taskbar_cfg = window.settings.data.get("taskbar", {})
    window.taskbarStateFlashCheck = QtWidgets.QCheckBox(
        window.i18n.t("taskbar.flash.enabled", "Flash green taskbar hint when unlocked")
    )
    window.taskbarStateFlashCheck.setChecked(bool(taskbar_cfg.get("stateFlashEnabled", True)))
    window.taskbarStateFlashCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.taskbarStateFlashCheck)

    taskbar_flash_layout = QtWidgets.QHBoxLayout()
    taskbar_flash_layout.addWidget(QtWidgets.QLabel(window.i18n.t("taskbar.flash.duration", "Unlock flash duration")))
    window.taskbarStateFlashSpin = QtWidgets.QSpinBox()
    window.taskbarStateFlashSpin.setRange(100, 10000)
    window.taskbarStateFlashSpin.setSingleStep(100)
    window.taskbarStateFlashSpin.setSuffix(" ms")
    window.taskbarStateFlashSpin.setValue(int(taskbar_cfg.get("stateFlashMs", 1000)))
    window.taskbarStateFlashSpin.valueChanged.connect(lambda _value: window._schedule_live_apply())
    taskbar_flash_layout.addWidget(window.taskbarStateFlashSpin)
    taskbar_flash_layout.addStretch()
    layout.addLayout(taskbar_flash_layout)

    close_action_layout = QtWidgets.QHBoxLayout()
    close_action_layout.addWidget(QtWidgets.QLabel(window.i18n.t("close.action.title", "Close Behavior")))
    window.resetCloseActionBtn = QtWidgets.QPushButton(window.i18n.t("close.action.reset", "Reset 'Don't ask again'"))
    window.resetCloseActionBtn.clicked.connect(window._reset_close_action)
    close_action_layout.addWidget(window.resetCloseActionBtn)
    close_action_layout.addStretch()
    layout.addLayout(close_action_layout)

    window.startupCheck = QtWidgets.QCheckBox(window.i18n.t("startup.autostart", "Launch on system startup"))
    window.startupCheck.setChecked(is_startup_enabled())
    window.startupCheck.toggled.connect(lambda _checked: window._schedule_live_apply())
    layout.addWidget(window.startupCheck)

    layout.addStretch()
    live_apply_hint = QtWidgets.QLabel(
        window.i18n.t("settings.liveApply", "Settings in this page take effect automatically.")
    )
    live_apply_hint.setWordWrap(True)
    live_apply_hint.setStyleSheet("color: rgba(142, 142, 147, 0.95); font-size: 12px;")
    layout.addWidget(live_apply_hint)

    return page
