# @fradser/pi-keyboard

基于 VIA/QMK 协议的 Pi 键盘 RGB 状态指示灯插件。

通过机械键盘的 RGB 灯光，实时提供 AI Coding Agent 运行状态的环境感知：

| Pi 运行状态 | 灯光颜色与效果 | 触发时机 |
| :--- | :--- | :--- |
| **Idle (待命)** | **白色 呼吸灯** | 启动完成、等待用户输入新任务 |
| **Thinking (运行)** | **蓝色 呼吸灯** | 模型生成中、深度思考中或正在执行工具 |
| **Unread Chat (未读)** | **绿色 呼吸灯** | Agent 回答完成，等待用户查阅 |
| **Need Approval (确认)** | **黄色 闪烁** | 提问、等待用户输入或交互式权限确认 |
| **Error (异常)** | **红色 闪烁** | API 报错、工具执行失败或异常中断 |

---

## 零 Flash 损耗设计（`--no-save`）

所有状态变更均以 `--no-save` 纯内存模式向键盘 MCU 发送指令，**不写入 Flash / EEPROM**。即使每天触发数千次思考与交互状态切换，也不会产生硬件擦写寿命损耗。

---

## 多分区独立控制

支持精准控制键盘的不同发光区域：
- **全部区域** (`all`)：按键背光与侧边底灯联动。
- **按键背光矩阵** (`matrix`)：仅控制键帽背光（QMK 通道 3）。
- **侧边底灯** (`underglow`)：仅控制外壳侧边/底部灯带（QMK 通道 2）。

---

## 安装方式

从本地仓库安装：

```bash
pi install ~/Developer/FradSer/pi-packages/packages/keyboard
```

当发布到 npm 后也可直接安装：

```bash
pi install npm:@fradser/pi-keyboard
```

---

## 使用指南

### 交互式菜单

在 Pi 对话框中输入 `/keyboard`：
- **开关切换**：开启或关闭状态指示灯
- **状态效果测试**：预览测试待命、思考、未读、确认、错误各状态
- **活动分区配置**：选择全部、仅背光或仅侧灯
- **亮度比例调节**：100%、75%、50%、25% 亮度随心调节
- **硬件连接信息**：查看识别到的键盘型号与 VIA 协议版本

### 对话内快捷指令

```bash
/keyboard on            # 启用指示灯
/keyboard off           # 关闭指示灯
/keyboard status        # 查看当前配置与键盘硬件状态
/keyboard test thinking # 预览测试蓝色思考呼吸灯
/keyboard test error    # 预览测试红色报错闪烁灯
/keyboard test unread   # 预览测试绿色未读呼吸灯
```

---

## 独立命令行工具：`via-rgb`

本插件配套安装了系统级命令 `via-rgb`（位于 `~/.local/bin/via-rgb`），在 Pi 之外也可用于 Shell、Raycast、Hammerspoon 或睡眠唤醒脚本：

```bash
# 查询当前状态
via-rgb status

# 开关灯光
via-rgb off
via-rgb on -b 200

# 自定义颜色与分区
via-rgb --zone matrix set -c blue
via-rgb --zone side set -c warmwhite
```

---

## 配置文件

配置自动保存在 `~/.pi/agent/keyboard.json`：

```json
{
  "enabled": true,
  "zone": "all",
  "brightnessScale": 1.0,
  "saveToEeprom": false
}
```
