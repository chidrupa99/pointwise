/**
 * Client for the Pointwise engine.
 *
 * The app never computes a reward. It asks the engine and renders the answer,
 * which keeps one source of truth for the rules across web and mobile.
 */

import { Platform } from 'react-native';

/**
 * The iOS Simulator reaches the host machine's server at localhost directly.
 * Android's emulator maps the host to 10.0.2.2. A physical device needs the
 * machine's LAN address, so that is overridable.
 */
const HOST = Platform.select({
  ios: 'http://localhost:8077',
  android: 'http://10.0.2.2:8077',
  default: 'http://localhost:8077',
});

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE ?? HOST;

export interface Component {
  rule_label: string;
  spend_applied: string;
  rate: string;
  unit: 'cashback_percent' | 'points' | 'miles';
  reward_quantity: string;
  value_dollars: string;
  reason: string;
}

export interface Evaluation {
  card_id: string;
  card_name: string;
  issuer: string;
  annual_fee: string;
  net_value_dollars: string;
  gross_value_dollars: string;
  fees_dollars: string;
  effective_rate_percent: string;
  caveats: string[];
  unverified_rules: string[];
  disqualified: boolean;
  disqualified_reason: string | null;
  components: Component[];
}

export interface RecommendResponse {
  category: string;
  provenance: string;
  resolved: boolean;
  explain: string;
  advantage_dollars: string;
  ranked: Evaluation[];
  excluded: Evaluation[];
}

export interface RecommendRequest {
  merchant: string;
  amount: string;
  portal?: string | null;
  is_foreign?: boolean;
  category_spend_to_date?: string;
  activated_rule_ids?: string[];
}

export async function recommend(req: RecommendRequest): Promise<RecommendResponse> {
  const response = await fetch(`${API_BASE}/api/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  });
  if (!response.ok) {
    throw new Error(`Engine returned ${response.status}`);
  }
  return response.json();
}

export interface Audit {
  summary: string;
  total_rules: number;
  verified_rules: number;
  percent_verified: number;
}

export async function fetchAudit(): Promise<Audit> {
  const response = await fetch(`${API_BASE}/api/cards`);
  if (!response.ok) throw new Error(`Engine returned ${response.status}`);
  const body = await response.json();
  return body.audit;
}

/** One consultation the advisor made, as the UI shows it. */
export interface TraceEntry {
  name: string;
  summary: string;
  ok: boolean;
}

export interface ChatTurn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ChatResponse {
  text: string;
  /** Quick replies for a question the advisor just asked; usually empty. */
  suggestions: string[];
  truncated: boolean;
  trace: TraceEntry[];
  usage: { input_tokens: number; output_tokens: number };
}

export interface AgentStatus {
  configured: boolean;
  model: string;
  effort: string;
  hint: string | null;
}

export async function fetchAgentStatus(): Promise<AgentStatus> {
  const response = await fetch(`${API_BASE}/api/agent/status`);
  if (!response.ok) throw new Error(`Engine returned ${response.status}`);
  return response.json();
}

/**
 * Ask the advisor.
 *
 * The whole conversation goes up each time: the endpoint is stateless, so the
 * client owns the history. Coordinates are sent only when the user has already
 * granted location, and are what the `whats_nearby` tool reads -- the model is
 * never given a chance to invent them.
 */
export async function chat(
  messages: ChatTurn[],
  position?: { lat: number; lon: number },
): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, ...position }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Advisor returned ${response.status}`);
  }
  return response.json();
}
