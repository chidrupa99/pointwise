/** Location → nearby merchants → the card to use at each one. */

import * as Location from 'expo-location';

import { API_BASE } from './api';

export interface BestCard {
  card_id: string;
  card_name: string;
  net_value_dollars: string;
  effective_rate_percent: string;
  advantage_dollars: string;
  runner_up: string | null;
  headline: string;
}

export interface NearbyPlace {
  id: string;
  name: string;
  category: string;
  provenance: string;
  distance_m: number;
  is_mall: boolean;
  stores: string[];
  best: BestCard | null;
}

export interface MallStore {
  name: string;
  category: string;
  provenance: string;
  best: BestCard | null;
}

export interface InMall {
  id: string;
  name: string;
  distance_m: number;
  stores: MallStore[];
}

export interface NearbyResponse {
  source: string;
  is_demo_data: boolean;
  in_mall: InMall | null;
  places: NearbyPlace[];
}

export type LocationOutcome =
  | { ok: true; lat: number; lon: number }
  | { ok: false; reason: 'denied' | 'unavailable'; detail: string };

/**
 * Ask for foreground location only.
 *
 * Background geofencing needs "Always" permission plus a development build,
 * and it is among the most common App Store rejections. The foreground path
 * works everywhere and is what a user can always fall back to, so it ships
 * first and on its own.
 */
export async function getCurrentPosition(): Promise<LocationOutcome> {
  const { status } = await Location.requestForegroundPermissionsAsync();
  if (status !== 'granted') {
    return {
      ok: false,
      reason: 'denied',
      detail: 'Location access is off. Turn it on in Settings, or pick a store by hand.',
    };
  }
  try {
    const position = await Location.getCurrentPositionAsync({
      accuracy: Location.Accuracy.Balanced,
    });
    return { ok: true, lat: position.coords.latitude, lon: position.coords.longitude };
  } catch (error) {
    return {
      ok: false,
      reason: 'unavailable',
      detail: error instanceof Error ? error.message : 'Could not get a fix.',
    };
  }
}

export async function fetchNearby(
  lat: number,
  lon: number,
  amount: string,
  radiusM = 400,
): Promise<NearbyResponse> {
  const response = await fetch(`${API_BASE}/api/nearby`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat, lon, radius_m: radiusM, amount }),
  });
  if (!response.ok) throw new Error(`Engine returned ${response.status}`);
  return response.json();
}

/**
 * Coordinates only if location was already granted.
 *
 * Deliberately never prompts. The chat sheet is the wrong place to ask for a
 * permission -- the user came to type a question -- so if they have not shared
 * location the advisor is told so and says so.
 */
export async function quietPosition(): Promise<{ lat: number; lon: number } | undefined> {
  try {
    const { granted } = await Location.getForegroundPermissionsAsync();
    if (!granted) return undefined;
    const last = await Location.getLastKnownPositionAsync();
    if (!last) return undefined;
    return { lat: last.coords.latitude, lon: last.coords.longitude };
  } catch {
    return undefined;
  }
}
