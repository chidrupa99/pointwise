/** Sign-in client. The server owns the OAuth flow; the app only opens a URL. */

import { API_BASE } from './api';

export interface AuthProfile {
  name: string;
  email: string | null;
  method: 'paypal' | 'local';
  /** True only when PayPal vouched for the identity. The UI says which. */
  verified: boolean;
  signed_in_at: string;
}

export interface AuthStatus {
  signed_in: boolean;
  profile: AuthProfile | null;
  paypal_login_available: boolean;
  paypal_login_hint: string | null;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(detail?.detail ?? `Server returned ${response.status}`);
  }
  return response.json();
}

export async function fetchAuthStatus(): Promise<AuthStatus> {
  const response = await fetch(`${API_BASE}/api/auth/status`);
  if (!response.ok) throw new Error(`Server returned ${response.status}`);
  return response.json();
}

export const startPayPalLogin = () =>
  post<{ url: string; state: string }>('/api/auth/paypal/start');

export const localSignIn = (name: string, email?: string) =>
  post<{ profile: AuthProfile }>('/api/auth/local', { name, email: email ?? null });

export const signOut = () => post<{ signed_in: boolean }>('/api/auth/signout');
