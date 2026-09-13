# MouseControlLayer

<div align="center">

[![Windows CI](https://github.com/EricDasha/MouseControlLayer/actions/workflows/windows-ci.yml/badge.svg)](https://github.com/EricDasha/MouseControlLayer/actions/workflows/windows-ci.yml)
[![Latest Release](https://img.shields.io/github/v/release/EricDasha/MouseControlLayer?color=2ea44f&label=release)](https://github.com/EricDasha/MouseControlLayer/releases/latest)
[![License](https://img.shields.io/github/license/EricDasha/MouseControlLayer)](LICENSE)
[![Windows](https://img.shields.io/badge/Windows-10%2B-0078d4?logo=windows)](#运行要求)

把鼠标固定在屏幕或窗口中心，也顺手解决连点、热键和简单键鼠动作。

[下载最新版](https://github.com/EricDasha/MouseControlLayer/releases/latest) · [宏配置示例](examples/mouse-macros/README.md) · [反馈问题](https://github.com/EricDasha/MouseControlLayer/issues)

<img src="docs/assets/mouse-control-layer.png" width="578" alt="MouseControlLayer 简单模式界面">

</div>

## 这是做什么的

MouseControlLayer（MCL）最初只为一个需求写：**把鼠标锁在屏幕中心**。

后来实际使用时又缺连点、侧键触发、窗口规则和几段简单宏，于是这些功能被放进了同一个小工具里。它更适合需要快速切换配置的游戏或桌面场景，而不是拿一套复杂脚本系统来解决一个按键问题。

- **鼠标锁定**：虚拟屏幕中心、主显示器中心、当前窗口中心或自定义坐标
- **自动连点**：切换启动、按住键盘启动、按住鼠标键启动，按住交换键时可左右互换连点按钮，多方案独立保存
- **简单宏**：鼠标点击/按下/松开、键盘按键、延迟、循环、移动和滚轮
- **窗口规则**：只在指定进程或窗口生效，支持前台切换时自动锁定/解锁
- **日常使用**：系统托盘、全局热键、开机启动、深浅主题和多语言

## 下载和使用

1. 打开 [Releases](https://github.com/EricDasha/MouseControlLayer/releases/latest)。
2. 下载 `MCL-*-windows-x64.zip`。
3. 解压后运行 `MouseControlLayer.exe`。
4. 在“高级”页设置热键、连点方案和目标窗口；平时留在“简单”页开关即可。

配置保存在程序目录的 `Mconfig.json`。升级时可以保留这个文件；想恢复默认设置时，退出 MCL 后删除它再重新启动。

> [!TIP]
> MCL 有单实例保护。如果双击新版后没有出现新窗口，先检查系统托盘并彻底退出正在运行的旧版。

## 连点器怎么调

连点不是只有一个“每隔多少毫秒”。一个完整周期里还有鼠标保持按下的时间，部分游戏会漏掉过短的点击。

| 设置 | 实际含义 | 建议 |
|---|---|---|
| 点击间隔 | 一次点击开始到下一次点击开始 | `100ms` 约等于每秒 10 个点击周期 |
| 鼠标按住时长 | `mouseDown` 到 `mouseUp` 之间保持多久 | 设为 `0` 时自动使用约 50% 周期，并限制在 `8–50ms` |
| 连点器后端 | 当前连点方案发送鼠标事件的方式 | 先用 `Auto`；目标不接受时再试其他后端 |
| 触发模式 | 如何启动或停止连点 | 可选择切换、按住键盘或按住鼠标键 |
| 交换连点按钮 | 按住某个快捷键或鼠标键时把连点按钮在左键/右键间互换 | 需要经常在左右键连点间切换时，可绑定一个侧键作为交换来源 |

例如点击间隔为 `100ms`、鼠标按住时长为 `0` 时，MCL 会生成大致这样的周期：

```text
按下 50ms → 松开约 50ms → 下一次按下
```

这比把按下和松开同时塞进一次调用更容易被按帧读取输入的程序识别。需要蓄力后松开发射的操作，可以直接填写更长的按住时间。

## 输入后端

宏和连点方案可以分别选择后端。一般保持 `Auto` 即可，只有目标程序不响应时才需要调整。

| 后端 | 用途 |
|---|---|
| `native-sendinput` | 默认路径，使用随程序打包的 Rust DLL 发送鼠标事件、扫描码和 Unicode 输入 |
| `python-sendinput` | Python/ctypes 实现的 SendInput 兼容路径 |
| `window-message` | 将消息发送给当前前台窗口；部分普通窗口可用，游戏不一定接受 |
| `virtual-hid` | 预留接口，目前没有可用驱动 |
| `hardware-hid` | 预留外部硬件输入接口 |

“高级”页里部分容易混淆的名称支持悬停说明：把光标停在名称上 3 秒会出现解释，移开后自动关闭。

## 简单宏

宏可以直接在界面中组合，也可以加载外部 JSON。下面是一段“按下左键、等待、再松开”的动作：

```json
[
  { "type": "mouseDown", "button": "left" },
  { "type": "delay", "ms": 300 },
  { "type": "mouseUp", "button": "left" }
]
```

项目已经附带不同语言的配置示例，完整字段和可用动作见 [examples/mouse-macros/README.md](examples/mouse-macros/README.md)。宏默认使用 `F12` 作为紧急停止键，停止时会释放由 MCL 保持按下的键鼠输出。

## 兼容性

MCL 使用 Windows `SendInput`、窗口消息和全局 Hook，属于用户态输入工具，不是虚拟 HID 驱动。

以下场景可能无法接收模拟输入：

- 以更高管理员权限运行的窗口
- 只读取 Raw Input 或驱动层输入的程序
- 主动过滤 injected input 的游戏或反作弊环境
- 对前台焦点、按下时长或帧采样时机要求严格的程序

遇到问题时建议依次检查：目标程序与 MCL 的权限是否一致、连点按住时长是否过短、当前方案选择了哪个后端。仍无法工作时，可在 [Issues](https://github.com/EricDasha/MouseControlLayer/issues) 附上目标程序、配置和日志。

## 从源码运行

### 运行要求

- Windows 10 或更新版本
- Python 3.9+
- 依赖见 `requirements.txt`

```powershell
python -m pip install -r requirements.txt
python mouse_center_lock_gui.py
```

运行测试：

```powershell
python -m unittest discover -s tests -v
```

完整打包（语法检查、JSON 校验、测试、Rust 后端和 PyInstaller）：

```powershell
python build.py
```

产物位于：

```text
dist/MouseControlLayer.exe
release/MCL-<version>-windows-x64.zip
```

## 相关文档

- [更新记录](CHANGELOG.md)
- [输入后端路线图](docs/backend-roadmap.md)
- [鼠标宏配置与示例](examples/mouse-macros/README.md)
- [English](README.en.md) · [繁體中文](README.zh-Hant.md) · [日本語](README.ja.md) · [한국어](README.ko.md)

## 版本历史

### v1.2.0

- 高级设置改为分类标签页：窗口、鼠标、快捷键与常规，设置项不再挤成一列
- 连点「交换按钮」：按住绑定的快捷键或鼠标键时，连点按钮在左键与右键之间互换（支持任意按键、可单独按键而不弹「简单热键」警告）
- 修复关窗行为：默认在用户第一次点击关闭时询问「退出程序 / 最小化到托盘」，可勾选记住选择；系统托盘不可用时最小化自动回退为退出
- 简单模式信息栏显示已配置的交换按钮来源

## License

[GNU General Public License v3.0](LICENSE)
