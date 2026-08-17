# @fradser/pi-keyboard

Dynamic VIA/QMK keyboard RGB lighting indicator reflecting Pi's internal states.

Ambient physical awareness of what your AI coding agent is doing right on your mechanical keyboard:

| Pi State | Color & Effect | Trigger Condition |
| :--- | :--- | :--- |
| **Idle** | **White Breathing** (白色 呼吸灯) | Session started, ready & waiting for user input |
| **Thinking** | **Blue Breathing** (蓝色 呼吸灯) | Model generating, reasoning, or executing tools |
| **Unread Chat** | **Green Breathing** (绿色 呼吸灯) | Agent settled with a completed response for user |
| **Need Approval** | **Yellow Blinking** (黄色 闪烁) | User prompt, question, or interactive permission gate |
| **Error** | **Red Blinking** (红色 闪烁) | API failure, tool error, or abort |

---

## Zero Flash Wear (`--no-save`)

All hardware updates are executed strictly in memory (`--no-save` mode). Lighting changes modify active RAM state on the keyboard's MCU without writing to EEPROM/Flash, avoiding storage wear across thousands of state transitions.

---

## Multi-Zone Control

Supports discrete control for keyboard lighting channels:
- **All Zones** (`all`): Both per-key backlight and underglow/side strips.
- **Per-Key Matrix** (`matrix`): Keycap backlight (Channel 3 in VIA/QMK).
- **Underglow / Side Strips** (`underglow`): Bottom and edge light strips (Channel 2 in VIA/QMK).

---

## Installation

Install from this monorepo or local path:

```bash
pi install ~/Developer/FradSer/pi-packages/packages/keyboard
```

When published to npm:

```bash
pi install npm:@fradser/pi-keyboard
```

---

## Usage

### Interactive Menu

Type `/keyboard` in any Pi session:
- **Toggle On / Off**
- **Test Lighting States** (preview Idle, Thinking, Unread, Approval, Error)
- **Active Zone Selection** (`all`, `matrix`, `underglow`)
- **Brightness Scaling** (100%, 75%, 50%, 25%)
- **Hardware Connection Info**

### CLI Commands inside Pi

```bash
/keyboard on            # Enable lighting indicators
/keyboard off           # Disable lighting indicators
/keyboard status        # View active status and hardware info
/keyboard test thinking # Test blue thinking light
/keyboard test error    # Test red blinking light
/keyboard test unread   # Test green unread chat light
```

---

## Standalone CLI: `via-rgb`

This package coordinates with the native macOS/Linux `via-rgb` binary (`~/.local/bin/via-rgb`), allowing shell scripts, cron jobs, Raycast, and Hammerspoon to control lighting outside Pi as well:

```bash
# Query status
via-rgb status

# Turn off / on
via-rgb off
via-rgb on -b 200

# Set specific color & zone
via-rgb --zone matrix set -c blue
via-rgb --zone side set -c warmwhite
```

---

## Configuration

Settings are saved in `~/.pi/agent/keyboard.json`:

```json
{
  "enabled": true,
  "zone": "all",
  "brightnessScale": 1.0,
  "saveToEeprom": false
}
```
