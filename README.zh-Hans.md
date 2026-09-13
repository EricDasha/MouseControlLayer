**语言 / Language / 日本語 / 언어**: [简体中文](README.zh-Hans.md) | [繁體中文](README.zh-Hant.md) | [English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

---

# MouseControlLayer

MouseControlLayer 是一个 Windows 鼠标 / 键盘控制工具，主要用于鼠标锁定、自动点击和简单宏操作。

它最开始只是想做一个“把鼠标锁在屏幕中心”的小工具。后来因为实际使用里还需要连点、快捷键、窗口规则和一些宏动作，所以逐渐整理成了现在这个项目。

它适合这些场景：

- 需要把鼠标固定到屏幕中心或窗口中心
- 需要用热键切换连点状态
- 需要给鼠标侧键、键盘按键绑定一组简单动作
- 需要针对不同窗口使用不同规则

它不是驱动级输入工具，也不是反作弊绕过工具。

如果目标程序不接受 Windows API / SendInput 模拟输入，那么这个项目也无法保证生效。

## 功能

### 鼠标锁定

可以把鼠标锁定到指定位置，例如：

- 屏幕中心
- 主显示器中心
- 当前窗口中心
- 自定义位置

适合需要固定鼠标位置的窗口或游戏场景。

### 自动点击

支持通过热键启用 / 停止自动点击，也可以设置为按住某个按键时持续点击。连点过程中还可按住一个「交换」来源（快捷键或侧键）把连点按钮在左键与右键之间互换，适合一边打一边切换左右键连点的场景。连点方案可在「更多」中导入、导出、删除或清空；切换方案前若有未保存改动，会询问是否保存。

连点和宏的鼠标点击现在都通过统一输入链按“按下 → 保持 → 松开”分开发送，避免 down/up 落在同一个 `SendInput` 批次而被按帧读取输入的游戏漏掉。**Mouse down hold (ms)** 设为 `0` 时使用自动 50% 占空比并限制在 `8` ~ `50ms`；因此点击间隔为 `100ms` 时，会按下 `50ms`、松开约 `50ms`，更接近按键精灵的完整点击周期。蓄力/松开发射武器可显式填写更长的按住时间。

常见用途包括：

- 长按触发连点
- 快捷键切换连点状态
- 调整点击间隔

### 简单宏

可以把鼠标或键盘输入组合成一组动作，例如：

- 点击鼠标，也可设置点击保持时间
- 按下 / 松开键盘按键
- 移动鼠标、相对移动鼠标、滚轮
- 延迟指定时间
- 按顺序执行一组输入
- 重复执行动作块

宏功能主要面向简单、可控的输入流程，不是复杂脚本引擎。

### 窗口规则

可以为不同窗口设置不同规则，让锁定、连点或宏只在指定程序中生效。

### 其它功能

- 系统托盘运行
- 开机自启
- 深色 / 浅色主题
- 多语言界面
- 多显示器支持

## 系统要求

- Windows 10+
- Python 3.9+
- 依赖项：见 `requirements.txt`

安装依赖：
```bash
python -m pip install -r requirements.txt
```

运行：
```bash
python mouse_center_lock_gui.py
```

测试：
```bash
python -m unittest discover tests
```

## 构建（PyInstaller）

创建虚拟环境（推荐）并构建窗口化 exe：
```bash
python build.py
```
或使用 PyInstaller 直接构建：
```bash
pyinstaller --noconfirm --clean MCL.spec
```
exe 文件将位于 `dist/MouseControlLayer.exe`。

打包脚本选项：
- `python build.py` — 完整构建（清理 + 测试 + 打包）
- `python build.py --skip-test` — 跳过单元测试
- `python build.py --dev` — 开发构建（含调试信息）
- `python build.py --clean-only` — 仅清理构建产物

如需恢复默认设置，请删除本地 `Mconfig.json`，程序会回退读取 `Mconfig.example.json`。如果程序目录中仍有旧版 `config.json`，新版本也会兼容读取。

## 宏配置

宏支持「界面拼装」和「外部 JSON 配置文件」两种方式。完整写法、示例文件、鼠标键名与键盘 `key` 名称见：

- [宏示例与配置说明](examples/mouse-macros/zh-Hans/README.md)

后端阶段、fallback 策略与非目标见：[输入后端路线图](docs/backend-roadmap.md)。

## 已知限制

MouseControlLayer 主要依赖 Windows API / SendInput 实现输入模拟，不属于驱动层输入。

因此在以下场景中可能无法正常工作：

- 管理员权限窗口
- 使用 Raw Input 的游戏
- 带有反作弊保护的游戏
- 主动过滤模拟输入的软件
- 对前台窗口和输入焦点要求较严格的程序

这些限制来自 Windows 输入机制和目标程序本身，不一定是项目 bug。

## 输入后端

项目目前提供多个输入后端，用于在不同场景下尽量提高兼容性。
宏输出后端默认是 `auto`，可在高级设置里手动选择。连点器也有独立后端选项，并按连点方案保存；如果目标程序无视瞬时点击，可先尝试 `native-sendinput` 并给连点器设置 8-20ms 的「鼠标按住时长」，再尝试 `window-message`。

| 后端 | 状态 | 说明 |
|---|---|---|
| `native-sendinput` | 默认 | 基于 Rust DLL，优先使用 scan code / Unicode 输入 |
| `python-sendinput` | 兜底 | Python 实现的 SendInput 路径，兼容性较保守 |
| `window-message` | 兼容 | 向前台窗口消息链发送输入消息 |
| `virtual-hid` | 预留 | 为后续虚拟 HID / 驱动输入预留 |
| `hardware-hid` | 预留 | 为外部硬件输入模式预留 |

这些后端不能保证绕过游戏、反作弊或系统权限限制。

## 项目结构

- `mouse_center_lock_gui.py` – GUI 应用（PySide6）
- `win_api.py` – Windows API 封装模块
- `widgets.py` – 自定义 UI 组件（快捷键捕获、进程选择器）
- `services/` – 运行期服务（连点器、锁定状态机、宏执行链）
- `ui/pages/` – 简单 / 高级页面构建模块
- `tests/` – 最小单元测试集
- `i18n/` – 语言文件
- `assets/` – 图标和资源
- `Mconfig.example.json` – 可提交的默认配置模板；运行时 `Mconfig.json` 仅作本地配置（兼容读取旧版 `config.json`）

## 更新日志

完整更新记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

[GPL-3.0](LICENSE)
