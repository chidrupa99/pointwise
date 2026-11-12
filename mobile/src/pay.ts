/**
 * Paying through PayPal on the card the engine picked.
 *
 * This is the line where advice becomes an action: every other screen tells
 * the user which card should have paid, after the fact. Here the app puts the
 * purchase on that card itself.
 */

import { API_BASE } from './api';

export interface Receipt {
  order_id: string | null;
  status: string;
  capture_id: string | null;
  category: string;
  charged_card: {
    card_id: string;
    card_name: string;
    net_value_dollars: string;
    effective_rate_percent: string;
  };
  funding: {
    kind: string;
    vault_id: string | null;
    last4: string | null;
    /**
     * A card can hold a real vault id and still be charged on a stand-in,
     * so the receipt says which happened rather than implying the first.
     */
    funded_from_vault: boolean;
  };
  advantage_dollars: string;
  runner_up: string | null;
  explain: string;
  /** False when the user overruled the engine; the miss is then recorded. */
  followed_recommendation: boolean;
  recommended_card_name: string | null;
  forgone_dollars: string;
}

export async function checkout(
  merchant: string,
  amount: string,
  cardId?: string | null,
): Promise<Receipt> {
  const response = await fetch(`${API_BASE}/api/checkout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      merchant,
      amount,
      ...(cardId ? { card_id: cardId } : {}),
    }),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Checkout failed (${response.status})`);
  }
  return response.json();
}
