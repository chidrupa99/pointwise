/** Linking a card issuer. The access token lives on the server; this never sees it. */

import { API_BASE } from './api';

export interface PlaidAccountRow {
  account_id: string;
  label: string;
  /** Which catalog card the user says this is. Null until confirmed. */
  card_id: string | null;
}

export interface PlaidLinkRow {
  item_id: string;
  institution_name: string;
  linked_at: string;
  has_cursor: boolean;
  access_token_length: number;
  accounts: PlaidAccountRow[];
  /** Rows cached for this bank alone, so each connection can account for
   *  itself rather than hiding inside a single total. */
  transaction_count: number;
}

export interface PlaidStatus {
  configured: boolean;
  environment: string;
  hint: string | null;
  sandbox_shortcut_available: boolean;
  connected: boolean;
  links: PlaidLinkRow[];
  transactions_cached: number;
  unmapped_accounts: number;
}

export interface SyncResult {
  added: number;
  modified: number;
  removed: number;
  transactions_cached: number;
  unmapped: number;
}

async function call<T>(path: string, method = 'POST', body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body === undefined ? undefined : { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Server returned ${response.status}`);
  }
  return response.json();
}

export async function fetchPlaidStatus(): Promise<PlaidStatus> {
  const response = await fetch(`${API_BASE}/api/plaid/status`);
  if (!response.ok) throw new Error(`Server returned ${response.status}`);
  return response.json();
}

/** Plaid's own hosted Link page: the bank list, the sign-in, the consent. */
export const startLink = () =>
  call<{ link_token: string; hosted_link_url: string | null }>(
    '/api/plaid/link-token',
  );

/**
 * Read back what a finished Link session produced.
 *
 * `linked: false` is the ordinary outcome of someone closing Link without
 * picking a bank, not a failure.
 */
export const completeLink = (linkToken: string) =>
  call<{ linked: boolean; transactions?: number }>(
    '/api/plaid/link-complete',
    'POST',
    { link_token: linkToken },
  );

/** Sandbox only: mints a linked test issuer with no Link UI at all. */
export const linkSandboxIssuer = () => call<{ linked: boolean }>('/api/plaid/sandbox-link');

export const mapAccount = (itemId: string, accountId: string, cardId: string | null) =>
  call('/api/plaid/map', 'POST', {
    item_id: itemId,
    account_id: accountId,
    card_id: cardId,
  });

export const syncIssuers = () => call<SyncResult>('/api/plaid/sync');

export const unlinkIssuer = (itemId: string) =>
  call(`/api/plaid/link/${encodeURIComponent(itemId)}`, 'DELETE');
