/**
 * The design system. One source for colour, spacing, type and card finishes.
 *
 * The direction is a private bank statement rather than a dashboard: a deep
 * ink ground, warm bone type, and almost no chroma in the chrome. The cards
 * are the only saturated things on screen, which is the point -- the app is
 * about them, and a grey panel competing with them helps nobody.
 *
 * Two rules worth keeping:
 *
 * - Chroma is reserved for meaning. Jade is "you used the best card", amber is
 *   "money was left", red is a failure. Nothing decorative is allowed to be
 *   green or amber, or the signal stops reading as a signal.
 * - Vertical measurements come from `space`. Hand-picked paddings are how a
 *   screen ends up with six different gaps that are all nearly the same.
 */

import { Platform } from 'react-native';

export interface Theme {
  /** Page background, bottom of the ground gradient. */
  ground: string;
  /** Top of the ground gradient. Atmosphere, not decoration. */
  groundLift: string;
  surface: string;
  surfaceLift: string;
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
  /** Shadow colour; near-black on paper, pure black in the dark. */
  shade: string;
}

/** Warm paper, not grey. Grey reads as a tool; paper reads as a statement. */
export const light: Theme = {
  ground: '#F4F1EA',
  groundLift: '#FAF8F3',
  surface: '#FFFEFB',
  surfaceLift: '#FFFFFF',
  sunk: '#EAE5DA',
  ink: '#191714',
  inkSoft: '#5A554C',
  inkFaint: '#8C867A',
  rule: '#DDD7C9',
  ruleSoft: '#EBE6DA',
  accent: '#1F1C17',
  accentInk: '#FBF9F4',
  accentSoft: '#E8E3D6',
  ok: '#1F6B4F',
  okSoft: '#E0EDE6',
  warn: '#8A5A14',
  warnSoft: '#F5E9D5',
  stop: '#8E2F2F',
  stopSoft: '#F5E2E0',
  shade: '#191714',
};

/** Deep ink with a blue undertone. Reads as night, not as "dark mode grey". */
export const dark: Theme = {
  ground: '#080A10',
  groundLift: '#11141E',
  surface: '#141825',
  surfaceLift: '#1B2031',
  sunk: '#0D1018',
  ink: '#F2EEE5',
  inkSoft: '#A7A596',
  inkFaint: '#787868',
  rule: '#272C3C',
  ruleSoft: '#1D2231',
  accent: '#E8D9B0',
  accentInk: '#0B0D14',
  accentSoft: '#231F18',
  ok: '#58BE92',
  okSoft: '#11241D',
  warn: '#D9A441',
  warnSoft: '#241B0E',
  stop: '#D97070',
  stopSoft: '#241113',
  shade: '#000000',
};

/**
 * The vertical scale. Every margin, padding and gap is one of these.
 *
 * An earlier pass had paddings of 13, 14, 16 and 18 within one screen, which
 * is invisible individually and reads as sloppiness once stacked.
 */
export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 22,
  pill: 999,
} as const;

/**
 * Three faces, each with a job.
 *
 * Didot carries the display moments -- it is a high-contrast editorial serif,
 * and on a screen full of figures its one appearance per view is what stops
 * this looking like every other fintech app. Avenir Next runs the interface.
 * Menlo holds the figures in rows, because columns of money have to align.
 */
export const DISPLAY = Platform.select({
  ios: 'Didot',
  android: 'serif',
  default: 'Georgia',
});

export const UI = Platform.select({
  ios: 'Avenir Next',
  android: 'sans-serif',
  default: 'system-ui',
});

export const MONO = Platform.select({
  ios: 'Menlo',
  android: 'monospace',
  default: 'monospace',
});

/** Type sizes, paired with the line heights they actually need. */
export const type = {
  hero: { fontFamily: DISPLAY, fontSize: 52, lineHeight: 58 },
  title: { fontFamily: DISPLAY, fontSize: 27, lineHeight: 33 },
  section: { fontFamily: UI, fontSize: 12, lineHeight: 16 },
  body: { fontFamily: UI, fontSize: 15, lineHeight: 22 },
  label: { fontFamily: UI, fontSize: 13, lineHeight: 18 },
  small: { fontFamily: UI, fontSize: 11.5, lineHeight: 15 },
  figure: { fontFamily: MONO, fontSize: 15, lineHeight: 20 },
  figureSmall: { fontFamily: MONO, fontSize: 11.5, lineHeight: 15 },
} as const;

/** A section heading: small, spaced, upper. Used identically on every screen. */
export const SECTION_CAPS = {
  ...type.section,
  fontWeight: '600' as const,
  letterSpacing: 1.3,
  textTransform: 'uppercase' as const,
};

export interface CardFinish {
  /** Top-left to bottom-right. Three stops so the sheen is not a flat ramp. */
  gradient: readonly [string, string, string];
  /** Type colour on this finish. Champagne and titanium need dark ink. */
  on: string;
  /** Softer type on this finish. */
  onSoft: string;
  /** The hairline that separates sections inside the tile. */
  hairline: string;
  /** "Money left" text on this finish, which must stay legible and warm. */
  onWarn: string;
}

const DARK_ON = {
  on: '#FFFFFF',
  onSoft: 'rgba(255,255,255,0.68)',
  hairline: 'rgba(255,255,255,0.16)',
  onWarn: '#F3C97D',
} as const;

const LIGHT_ON = {
  on: '#20180A',
  onSoft: 'rgba(32,24,10,0.66)',
  hairline: 'rgba(32,24,10,0.18)',
  onWarn: '#6B4408',
} as const;

/**
 * What each card physically looks like.
 *
 * Keyed by card, not by issuer. Issuer colour is a brand guideline and has
 * almost nothing to do with the object in someone's wallet: Capital One's red
 * is on their logo, while a Venture X is dark gunmetal, and an Amex Gold is
 * champagne rather than Amex blue. Someone looking at this screen is matching
 * it against the card in their hand.
 */
export const CARD_FINISH: Record<string, CardFinish> = {
  'amex-gold': {
    gradient: ['#E2CB94', '#BFA059', '#8E7334'],
    ...LIGHT_ON,
  },
  'amex-platinum': {
    gradient: ['#DCE0E4', '#B4BCC4', '#868F99'],
    ...LIGHT_ON,
    on: '#1C2126',
    onSoft: 'rgba(28,33,38,0.64)',
    hairline: 'rgba(28,33,38,0.18)',
    onWarn: '#6B4408',
  },
  'amex-blue-cash-preferred': {
    gradient: ['#3C7FC4', '#235C9A', '#133C6C'],
    ...DARK_ON,
  },
  'capital-one-venture-x': {
    gradient: ['#434A55', '#262C36', '#11141A'],
    ...DARK_ON,
  },
  'capital-one-savor': {
    gradient: ['#C9414A', '#A32530', '#6E131C'],
    ...DARK_ON,
  },
  'chase-sapphire-preferred': {
    gradient: ['#3567AE', '#1C4484', '#0C2857'],
    ...DARK_ON,
  },
  'chase-freedom-flex': {
    gradient: ['#2E6DA8', '#1B4A7C', '#0D2E52'],
    ...DARK_ON,
  },
  'chase-freedom-unlimited': {
    gradient: ['#3A7CB8', '#215789', '#0F345C'],
    ...DARK_ON,
  },
  'citi-double-cash': {
    gradient: ['#2B4F86', '#193463', '#0B1D3E'],
    ...DARK_ON,
  },
  'citi-custom-cash': {
    gradient: ['#2E86B5', '#186288', '#09405C'],
    ...DARK_ON,
  },
  'discover-it': {
    gradient: ['#F08A2C', '#D1661A', '#9B4409'],
    ...DARK_ON,
  },
  'wells-fargo-active-cash': {
    gradient: ['#B8222F', '#8E1823', '#5E0D15'],
    ...DARK_ON,
  },
  'apple-card': {
    gradient: ['#F2F1EF', '#DCDAD7', '#BCBAB7'],
    ...LIGHT_ON,
    on: '#1D1D1F',
    onSoft: 'rgba(29,29,31,0.62)',
    hairline: 'rgba(29,29,31,0.16)',
    onWarn: '#6B4408',
  },
  'amazon-prime-visa': {
    gradient: ['#2B3440', '#1B222B', '#0E1319'],
    ...DARK_ON,
  },
};

/** A card the corpus has no finish for. Graphite, so it still looks deliberate. */
const DEFAULT_FINISH: CardFinish = {
  gradient: ['#4A5160', '#2E3440', '#171B23'],
  ...DARK_ON,
};

export function cardFinish(cardId: string): CardFinish {
  return CARD_FINISH[cardId] ?? DEFAULT_FINISH;
}

export function money(value: string | number): string {
  const n = Number(value);
  const body = Math.abs(n).toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return `${n < 0 ? '-' : ''}$${body}`;
}
