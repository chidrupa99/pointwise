/** Wallet and activity: the two sections of the home screen. */

import { API_BASE } from './api';

export type RewardUnit = 'points' | 'miles' | 'cashback_percent';

export interface SignupBonus {
  points: string;
  unit: RewardUnit;
  worth_dollars: string;
  spend_required: string;
  spent: string;
  remaining: string;
  percent: number;
  window_ends_on: string;
  days_left: number;
  earned: boolean;
  expired: boolean;
  verified: boolean;
}

export interface WalletCard {
  card_id: string;
  name: string;
  issuer: string;
  annual_fee: string;
  point_value_cents: string;
  reward_unit: RewardUnit;
  points_earned: string;
  value_earned_dollars: string;
  missed_dollars: string;
  missed_points: string;
  transaction_count: number;
  opened_on: string | null;
  signup_bonus: SignupBonus | null;
}

export interface WalletResponse {
  source: string;
  is_demo_data: boolean;
  is_empty: boolean;
  cards: WalletCard[];
  totals: {
    points_earned: string;
    value_earned_dollars: string;
    missed_dollars: string;
  };
}

export interface CatalogCard {
  card_id: string;
  name: string;
  issuer: string;
  network: string | null;
  annual_fee: string;
  point_value_cents: string;
  held: boolean;
  headline: string;
  signup_bonus: {
    points: string;
    unit: RewardUnit;
    spend_required: string;
    within_months: number;
    worth_dollars: string;
  } | null;
}

export type Verdict = 'optimal' | 'missed' | 'unknown';

export interface Activity {
  transaction_id: string;
  merchant_name: string;
  amount: string;
  on: string;
  category: string;
  provenance: string;
  /** "known" | "inferred" | "none" — how the category was arrived at. */
  category_confidence: string;
  /** "plaid" | "pointwise" | "paypal" | "fixture" — not equally real. */
  source: string;
  card_id: string | null;
  card_name: string | null;
  earned_dollars: string;
  best_card_name: string;
  best_dollars: string;
  missed_dollars: string;
  verdict: Verdict;
}

export interface ActivityResponse {
  source: string;
  is_demo_data: boolean;
  missed_total: string;
  activity: Activity[];
}

export interface PayPalStatus {
  configured: boolean;
  environment: string;
  hint: string | null;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(`Engine returned ${response.status}`);
  return response.json();
}

export const fetchWallet = () => getJson<WalletResponse>('/api/wallet');

export const fetchActivity = (cardId?: string | null) =>
  getJson<ActivityResponse>(
    `/api/activity${cardId ? `?card_id=${encodeURIComponent(cardId)}` : ''}`,
  );

export const fetchPayPalStatus = () => getJson<PayPalStatus>('/api/paypal/status');

export const fetchCatalog = () =>
  getJson<{ cards: CatalogCard[] }>('/api/catalog');

export async function addCard(cardId: string, openedOn: string | null) {
  const response = await fetch(`${API_BASE}/api/wallet/cards`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ card_id: cardId, opened_on: openedOn }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Engine returned ${response.status}`);
  }
  return response.json();
}

export async function removeCard(cardId: string) {
  const response = await fetch(
    `${API_BASE}/api/wallet/cards/${encodeURIComponent(cardId)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) throw new Error(`Engine returned ${response.status}`);
  return response.json();
}

/**
 * How many whole units a card's figure is worth, in that card's own currency.
 *
 * A cashback card earns no points, so its tile talks in dollars; a points card
 * talks in points. Mixing the two on one tile is what made "1,321 points" sit
 * next to "$2.98 missed" and ask the reader to do the conversion.
 */
export function inCardUnit(card: WalletCard, which: 'earned' | 'missed'): string {
  const cash = which === 'earned' ? card.value_earned_dollars : card.missed_dollars;
  if (card.reward_unit === 'cashback_percent') {
    return `$${Number(cash).toFixed(2)}`;
  }
  const points = which === 'earned' ? card.points_earned : card.missed_points;
  return `${Math.round(Number(points)).toLocaleString('en-US')}`;
}

/**
 * What a card's missed value reads as on its tile.
 *
 * Still an equivalence, never "175 miles missed": the better card earns a
 * different currency, so the user did not forgo miles on this card. This is
 * what the lost value amounts to in the unit the tile already speaks.
 *
 * "worth 175 more miles" left the obvious question unanswered -- more than
 * what? "elsewhere" answers it in one word, which is all the room a 228pt
 * tile has: the longer phrasing ran to the edge and clipped.
 */
export function missedPhrase(card: WalletCard): string {
  const amount = inCardUnit(card, 'missed');
  return card.reward_unit === 'cashback_percent'
    ? `+${amount} elsewhere`
    : `+${amount} ${unitLabel(card.reward_unit)} elsewhere`;
}

/** The word for a card's unit, singular-agnostic and short enough for a tile. */
export function unitLabel(unit: RewardUnit): string {
  switch (unit) {
    case 'miles':
      return 'miles';
    case 'cashback_percent':
      return 'cash back';
    default:
      return 'points';
  }
}

/** Per-issuer colour, so a stacked card is recognisable at a glance. */
export function cardColor(issuer: string, cardId: string): string {
  if (cardId === 'apple-card') return '#2c2c2e';
  switch (issuer) {
    case 'American Express':
      return '#1a6b8f';
    case 'Chase':
      return '#124a8b';
    case 'Citi':
      return '#1b4ea8';
    case 'Capital One':
      return '#9c2a2a';
    case 'Discover':
      return '#c25600';
    case 'Wells Fargo':
      return '#8a1c2b';
    default:
      return '#3a4256';
  }
}

export function formatDate(iso: string): string {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString('en-US', { day: 'numeric', month: 'short' });
}
