/** Design tokens, shared with the web console and the feasibility brief. */

import { Platform } from 'react-native';

export interface Theme {
  ground: string;
  surface: string;
  sunk: string;
  ink: string;
  inkSoft: string;
  inkFaint: string;
  rule: string;
  ruleSoft: string;
  accent: string;
  accentInk: string;
  accentSoft: string;
  ok: string;
  okSoft: string;
  warn: string;
  warnSoft: string;
  stop: string;
  stopSoft: string;
}

export const light: Theme = {
  ground: '#f6f7f9',
  surface: '#ffffff',
  sunk: '#eef0f4',
  ink: '#14192b',
  inkSoft: '#4e576e',
  inkFaint: '#7d869b',
  rule: '#d8dce5',
  ruleSoft: '#e6e9f0',
  accent: '#1b3f8f',
  accentInk: '#ffffff',
  accentSoft: '#e8edf8',
  ok: '#0f6b57',
  okSoft: '#e2f0eb',
  warn: '#8e5308',
  warnSoft: '#f8eddc',
  stop: '#962038',
  stopSoft: '#fbe7eb',
};

export const dark: Theme = {
  ground: '#0d1020',
  surface: '#161b2e',
  sunk: '#1d2338',
  ink: '#e8ebf3',
  inkSoft: '#a7b0c6',
  inkFaint: '#7b85a0',
  rule: '#2c3450',
  ruleSoft: '#232a42',
  accent: '#8fb0f0',
  accentInk: '#0d1020',
  accentSoft: '#1b2440',
  ok: '#5fc4a5',
  okSoft: '#142c28',
  warn: '#e0a860',
  warnSoft: '#2e2415',
  stop: '#f08098',
  stopSoft: '#31161f',
};

/** Figures line up in columns, so they need a monospace face. */
export const MONO = Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' });

export function money(value: string | number): string {
  const n = Number(value);
  const body = Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${n < 0 ? '-' : ''}$${body}`;
}
