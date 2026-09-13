**语言 / Language / 日本語 / 언어**: [简体中文](README.zh-Hans.md) | [繁體中文](README.zh-Hant.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

---

# MouseControlLayer

MouseControlLayer is a Windows mouse / keyboard control utility for cursor locking, auto clicking, and simple macro actions.

It started as a small tool for locking the cursor near the screen center, then grew into a practical control layer with click automation, hotkeys, window rules, and macro presets.

Good for:

- locking the cursor to the screen or window center
- toggling auto clicker states with hotkeys
- binding simple action sequences to mouse side buttons or keyboard keys
- applying behavior only to selected windows

## Features

### Mouse locking

Lock the cursor to the virtual screen center, primary display center, current window center, or a custom position.

### Auto clicker profiles

Supports toggle/hold triggers, click interval, process blacklist, startup sound, click hold duration, an optional "swap click button" source (a shortcut or mouse side button held to swap the clicked button between left and right while the clicker runs), and multiple profiles. The **More** menu can import, export, delete, or clear saved profiles. If a profile has unsaved edits, switching profiles asks whether to save them.

Clicker and macro mouse clicks now share a down → hold → up route instead of placing down/up in one `SendInput` batch. With **Mouse down hold (ms)** set to `0`, the clicker uses an automatic 50% duty cycle clamped to `8` ~ `50ms`; a `100ms` click interval therefore becomes roughly `50ms` down and `50ms` released, closer to a full Key Wizard-style click cycle. Use an explicit longer hold for charge-on-release weapons.

### Simple macros

Build ordered input sequences: mouse clicks with optional hold duration, mouse move/relative move/scroll, key down/up, delays, repeats, hotkeys, and text. Macros include a default `F12` panic stop key to force-stop running/toggled actions and release held outputs.

### Window rules

Apply locking, clicker, or macro behavior only when matching windows are active.

### Other features

- system tray operation
- launch on startup
- dark / light theme
- multilingual UI
- multi-monitor support

## Requirements

- Windows 10+
- Python 3.9+
- Dependencies: `requirements.txt`

```bash
python -m pip install -r requirements.txt
python mouse_center_lock_gui.py
python -m unittest discover tests
```

## Build (PyInstaller)

```bash
python build.py
```

The exe is created at `dist/MouseControlLayer.exe`. Local release archives are created under `release/`, with `MouseControlLayer.exe` inside the zip.

Common options:

- `python build.py` — full build: clean + tests + package + release zip
- `python build.py --skip-test` — skip unit tests
- `python build.py --no-archive` — skip local release zip
- `python build.py --dev` — development build
- `python build.py --clean-only` — clean only

## Mouse macro configuration

Mouse macros support both the UI builder and external JSON files.

- [Mouse macro examples and configuration reference](examples/mouse-macros/en/README.md)
- [Input Backend Roadmap](docs/backend-roadmap.md)

## Known limitations

MouseControlLayer mainly uses Windows API / SendInput. It is not driver-level input. Elevated windows, Raw Input games, anti-cheat protected games, or apps that filter simulated input may not work.

## Input backends

Macro output defaults to `auto` and can be changed in Advanced Settings. Auto clicker has its own per-profile backend selector; if a target ignores instant clicks, try `native-sendinput` with an 8-20ms mouse hold duration, then try `window-message`.

| Backend | Status | Notes |
|---|---|---|
| `native-sendinput` | default | Rust DLL backend, scan-code / Unicode first |
| `python-sendinput` | fallback | Python SendInput path |
| `window-message` | compatible | sends messages to the foreground window chain |
| `virtual-hid` | reserved | placeholder for future virtual HID / driver path |
| `hardware-hid` | reserved | placeholder for external hardware mode |

## Project layout

- `mouse_center_lock_gui.py` – GUI app (PySide6)
- `win_api.py` – Windows API wrapper
- `widgets.py` – custom UI widgets
- `services/` – runtime services
- `ui/pages/` – Simple / Advanced page builders
- `tests/` – unit tests
- `i18n/` – language files
- `examples/mouse-macros/` – macro examples
- `Mconfig.example.json` – default template; runtime `Mconfig.json` is local-only

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

[GPL-3.0](LICENSE)
