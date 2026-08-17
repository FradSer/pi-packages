export type KeyboardState =
  | "idle"
  | "unread_chat"
  | "thinking"
  | "need_approval"
  | "error";

export type KeyboardZone = "all" | "underglow" | "matrix";

export type KeyboardPattern = "breathing" | "blinking" | "solid";

export interface KeyboardStateDefinition {
  state: KeyboardState;
  label: string;
  labelZh: string;
  hue: number;
  sat: number;
  effect: number; // 1 = solid, 2 = breathing
  speed: number;
  brightness: number;
  pattern: KeyboardPattern;
  blinkCount?: number;
}

export interface KeyboardConfig {
  enabled: boolean;
  zone: KeyboardZone;
  brightnessScale: number; // 0.1 to 1.0 (default 1.0)
  saveToEeprom: boolean; // default false: strictly in-memory (--no-save)
  cliPath?: string;
}

export interface KeyboardDeviceInfo {
  vendorId: string;
  productId: string;
  product?: string;
  manufacturer?: string;
}

export const KEYBOARD_STATE_DEFINITIONS: Record<KeyboardState, KeyboardStateDefinition> = {
  idle: {
    state: "idle",
    label: "White Breathing (Idle)",
    labelZh: "白色 呼吸灯 (空闲待命)",
    hue: 0,
    sat: 0, // White
    effect: 2, // Breathing
    speed: 100,
    brightness: 180,
    pattern: "breathing",
  },
  unread_chat: {
    state: "unread_chat",
    label: "Green Breathing (Unread Chat)",
    labelZh: "绿色 呼吸灯 (未读消息)",
    hue: 85, // Green
    sat: 255,
    effect: 2, // Breathing
    speed: 150,
    brightness: 220,
    pattern: "breathing",
  },
  thinking: {
    state: "thinking",
    label: "Blue Breathing (Thinking)",
    labelZh: "蓝色 呼吸灯 (正在思考/执行)",
    hue: 170, // Blue
    sat: 255,
    effect: 2, // Breathing
    speed: 200,
    brightness: 255,
    pattern: "breathing",
  },
  need_approval: {
    state: "need_approval",
    label: "Yellow Blinking (Need Approval / Question)",
    labelZh: "黄色 闪烁 (需要确认/提问)",
    hue: 43, // Yellow
    sat: 255,
    effect: 1, // Alert / Fast pulse
    speed: 255,
    brightness: 255,
    pattern: "blinking",
    blinkCount: 4,
  },
  error: {
    state: "error",
    label: "Red Blinking (Error)",
    labelZh: "红色 闪烁 (异常错误)",
    hue: 0, // Red
    sat: 255,
    effect: 1, // Alert / Fast pulse
    speed: 255,
    brightness: 255,
    pattern: "blinking",
    blinkCount: 4,
  },
};
