import type { KeyboardZone } from "./types";

export const VIA_RAW_USAGE_PAGE = 0xff60;
export const VIA_RAW_USAGE = 0x0061;

export const CMD_GET_PROTOCOL_VERSION = 0x01;
export const CMD_CUSTOM_SET_VALUE = 0x07;
export const CMD_CUSTOM_GET_VALUE = 0x08;
export const CMD_CUSTOM_SAVE = 0x09;

export const CH_RGBLIGHT = 2; // Zone 1: Side strip / Underglow
export const CH_RGB_MATRIX = 3; // Zone 2: Per-key RGB Matrix

export const VAL_BRIGHTNESS = 1;
export const VAL_EFFECT = 2;
export const VAL_EFFECT_SPEED = 3;
export const VAL_COLOR = 4;

export function resolveChannels(zone: KeyboardZone): number[] {
  switch (zone) {
    case "underglow":
      return [CH_RGBLIGHT];
    case "matrix":
      return [CH_RGB_MATRIX];
    case "all":
    default:
      return [CH_RGBLIGHT, CH_RGB_MATRIX];
  }
}

export function buildPacket(payload: number[]): Uint8Array {
  const packet = new Uint8Array(32);
  for (let i = 0; i < payload.length && i < 32; i++) {
    packet[i] = payload[i];
  }
  return packet;
}

export function buildSetBrightnessPacket(channel: number, brightness: number): Uint8Array {
  const val = Math.max(0, Math.min(255, Math.round(brightness)));
  return buildPacket([CMD_CUSTOM_SET_VALUE, channel, VAL_BRIGHTNESS, val]);
}

export function buildSetEffectPacket(channel: number, effect: number): Uint8Array {
  const val = Math.max(0, Math.min(255, Math.round(effect)));
  return buildPacket([CMD_CUSTOM_SET_VALUE, channel, VAL_EFFECT, val]);
}

export function buildSetSpeedPacket(channel: number, speed: number): Uint8Array {
  const val = Math.max(0, Math.min(255, Math.round(speed)));
  return buildPacket([CMD_CUSTOM_SET_VALUE, channel, VAL_EFFECT_SPEED, val]);
}

export function buildSetColorPacket(channel: number, hue: number, sat: number): Uint8Array {
  const h = Math.max(0, Math.min(255, Math.round(hue)));
  const s = Math.max(0, Math.min(255, Math.round(sat)));
  return buildPacket([CMD_CUSTOM_SET_VALUE, channel, VAL_COLOR, h, s]);
}

export function buildSavePacket(channel: number): Uint8Array {
  return buildPacket([CMD_CUSTOM_SAVE, channel]);
}
