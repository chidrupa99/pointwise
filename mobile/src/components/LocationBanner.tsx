/** The contextual banner at the top of Home.
 *
 * Collapses both in-person journeys into one strip: outside a single shop it
 * names the merchant and the card; inside a mall, where GPS cannot separate a
 * food court from a department store, it asks instead of guessing.
 *
 * Location is never requested on launch. The banner starts as an invitation
 * and only asks the system for a fix once the user taps it, because a cold
 * permission prompt on first open is how apps get their location access
 * denied permanently.
 */

import React, { useCallback, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  fetchNearby,
  getCurrentPosition,
  type BestCard,
  type MallStore,
  type NearbyPlace,
} from '../nearby';
import { MONO, money, type Theme } from '../theme';

type State =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'denied'; detail: string }
  | { kind: 'error'; detail: string }
  | { kind: 'empty' }
  | { kind: 'store'; place: NearbyPlace; demo: boolean }
  | { kind: 'mall'; name: string; stores: MallStore[]; demo: boolean };

const BASKET = '120';

interface Props {
  theme: Theme;
}

export function LocationBanner({ theme }: Props) {
  const s = styles(theme);
  const [state, setState] = useState<State>({ kind: 'idle' });
  const [dismissed, setDismissed] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);

  const locate = useCallback(async () => {
    setState({ kind: 'loading' });
    setPicked(null);

    const position = await getCurrentPosition();
    if (!position.ok) {
      setState({ kind: position.reason === 'denied' ? 'denied' : 'error', detail: position.detail });
      return;
    }

    try {
      const data = await fetchNearby(position.lat, position.lon, BASKET);
      if (data.in_mall) {
        setState({
          kind: 'mall',
          name: data.in_mall.name,
          stores: data.in_mall.stores,
          demo: data.is_demo_data,
        });
        return;
      }
      const nearest = data.places.find((p) => !p.is_mall);
      setState(
        nearest
          ? { kind: 'store', place: nearest, demo: data.is_demo_data }
          : { kind: 'empty' },
      );
    } catch (e) {
      setState({
        kind: 'error',
        detail: e instanceof Error ? e.message : 'Could not reach the engine',
      });
    }
  }, []);

  if (dismissed) return null;

  const close = (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel="Dismiss location suggestion"
      hitSlop={10}
      onPress={() => setDismissed(true)}
      style={({ pressed }) => [s.close, pressed && { opacity: 0.5 }]}
    >
      <Text style={s.closeText}>✕</Text>
    </Pressable>
  );

  const renderBest = (best: BestCard | null) => {
    if (!best) return <Text style={s.body}>No eligible card here.</Text>;
    return (
      <>
        <Text style={s.cardLine}>
          Use <Text style={s.cardName}>{best.card_name}</Text>
        </Text>
        <Text style={s.value}>
          {money(best.net_value_dollars)}
          <Text style={s.rate}>
            {'  '}
            {best.effective_rate_percent}%
          </Text>
        </Text>
        {best.runner_up && Number(best.advantage_dollars) > 0 && (
          <Text style={s.gap}>
            {money(best.advantage_dollars)} better than {best.runner_up}
          </Text>
        )}
      </>
    );
  };

  // --- invitation -----------------------------------------------------
  if (state.kind === 'idle') {
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Use my location to suggest a card"
        onPress={locate}
        style={({ pressed }) => [s.banner, s.inviteBanner, pressed && { opacity: 0.8 }]}
      >
        <View style={s.row}>
          <Text style={s.pin}>◎</Text>
          <View style={s.flex}>
            <Text style={s.inviteTitle}>Which card, where you are</Text>
            <Text style={s.inviteBody}>
              Tap to check the shop you're in and the card that earns most there.
            </Text>
          </View>
          {close}
        </View>
      </Pressable>
    );
  }

  if (state.kind === 'loading') {
    return (
      <View style={[s.banner, s.inviteBanner]}>
        <View style={s.row}>
          <ActivityIndicator color={theme.accent} />
          <Text style={[s.inviteBody, s.flex]}>Finding you…</Text>
        </View>
      </View>
    );
  }

  if (state.kind === 'denied' || state.kind === 'error') {
    return (
      <View style={[s.banner, s.warnBanner]}>
        <View style={s.row}>
          <View style={s.flex}>
            <Text style={s.warnTitle}>
              {state.kind === 'denied' ? 'Location is off' : "Couldn't check"}
            </Text>
            <Text style={s.warnBody}>{state.detail}</Text>
          </View>
          {close}
        </View>
      </View>
    );
  }

  if (state.kind === 'empty') {
    return (
      <View style={[s.banner, s.inviteBanner]}>
        <View style={s.row}>
          <View style={s.flex}>
            <Text style={s.inviteTitle}>Nothing recognised nearby</Text>
            <Text style={s.inviteBody}>Ask Pointwise by name instead.</Text>
          </View>
          {close}
        </View>
      </View>
    );
  }

  // --- in a mall: ask, don't guess ------------------------------------
  if (state.kind === 'mall') {
    const chosen = state.stores.find((store) => store.name === picked) ?? null;
    return (
      <View style={[s.banner, s.mallBanner]}>
        <View style={s.row}>
          <View style={s.flex}>
            <Text style={s.eyebrow}>LOOKS LIKE YOU'RE IN</Text>
            <Text style={s.title}>{state.name}</Text>
            <Text style={s.body}>
              GPS can't tell which shop you're in here. Pick one.
            </Text>
          </View>
          {close}
        </View>

        <View style={s.chips}>
          {state.stores.map((store) => (
            <Pressable
              key={store.name}
              accessibilityRole="button"
              accessibilityState={{ selected: picked === store.name }}
              onPress={() => setPicked(store.name)}
              style={({ pressed }) => [
                s.chip,
                picked === store.name && s.chipOn,
                pressed && { opacity: 0.6 },
              ]}
            >
              <Text style={[s.chipText, picked === store.name && s.chipTextOn]}>
                {store.name}
              </Text>
            </Pressable>
          ))}
        </View>

        {chosen && (
          <View style={s.picked}>
            <Text style={s.pickedLabel}>
              {chosen.name} · {chosen.category}
            </Text>
            {renderBest(chosen.best)}
          </View>
        )}

        {state.demo && <Text style={s.demo}>demo place data</Text>}
      </View>
    );
  }

  // --- outside one shop: name it --------------------------------------
  return (
    <View style={[s.banner, s.storeBanner]}>
      <View style={s.row}>
        <View style={s.flex}>
          <Text style={s.eyebrow}>YOU'RE AT</Text>
          <Text style={s.title}>{state.place.name}</Text>
          <Text style={s.meta}>
            {state.place.distance_m} m · {state.place.category}
          </Text>
          <View style={s.divider} />
          {renderBest(state.place.best)}
        </View>
        {close}
      </View>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Check again"
        onPress={locate}
        style={({ pressed }) => [s.again, pressed && { opacity: 0.6 }]}
      >
        <Text style={s.againText}>Check again</Text>
      </Pressable>
      {state.demo && <Text style={s.demo}>demo place data</Text>}
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    banner: { borderRadius: 12, padding: 15, marginBottom: 14 },
    inviteBanner: { backgroundColor: t.accentSoft },
    storeBanner: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderLeftWidth: 3,
      borderLeftColor: t.ok,
    },
    mallBanner: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderLeftWidth: 3,
      borderLeftColor: t.warn,
    },
    warnBanner: { backgroundColor: t.warnSoft },

    row: { flexDirection: 'row', alignItems: 'flex-start', gap: 11 },
    flex: { flex: 1 },
    pin: { fontSize: 18, color: t.accent, marginTop: 1 },
    close: { paddingHorizontal: 2 },
    closeText: { fontSize: 15, color: t.inkFaint, fontWeight: '600' },

    inviteTitle: { fontSize: 14.5, fontWeight: '700', color: t.accent },
    inviteBody: { fontSize: 12.5, color: t.inkSoft, marginTop: 2, lineHeight: 17 },

    warnTitle: { fontSize: 13.5, fontWeight: '700', color: t.warn },
    warnBody: { fontSize: 12.5, color: t.warn, marginTop: 2, lineHeight: 17 },

    eyebrow: {
      fontSize: 9.5,
      fontWeight: '700',
      letterSpacing: 1.2,
      color: t.inkFaint,
      marginBottom: 4,
    },
    title: { fontSize: 19, fontWeight: '700', color: t.ink, letterSpacing: -0.3 },
    meta: { fontFamily: MONO, fontSize: 11, color: t.inkFaint, marginTop: 2 },
    body: { fontSize: 12.5, color: t.inkSoft, marginTop: 4, lineHeight: 17 },
    divider: { height: 1, backgroundColor: t.ruleSoft, marginVertical: 11 },

    cardLine: { fontSize: 13.5, color: t.inkSoft },
    cardName: { fontWeight: '700', color: t.ink, fontSize: 15 },
    value: { fontFamily: MONO, fontSize: 26, color: t.ink, marginTop: 3, letterSpacing: -0.6 },
    rate: { fontFamily: MONO, fontSize: 12, color: t.inkFaint },
    gap: { fontSize: 12.5, color: t.ok, fontWeight: '600', marginTop: 3 },

    chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 12 },
    chip: {
      backgroundColor: t.sunk,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 999,
      paddingHorizontal: 11,
      paddingVertical: 6,
    },
    chipOn: { backgroundColor: t.accentSoft, borderColor: t.accent },
    chipText: { fontSize: 12.5, color: t.inkSoft },
    chipTextOn: { color: t.accent, fontWeight: '600' },
    picked: {
      marginTop: 12,
      paddingTop: 12,
      borderTopWidth: 1,
      borderTopColor: t.ruleSoft,
    },
    pickedLabel: {
      fontFamily: MONO,
      fontSize: 10.5,
      color: t.inkFaint,
      marginBottom: 6,
    },

    again: { alignSelf: 'flex-start', marginTop: 11 },
    againText: { color: t.accent, fontSize: 13, fontWeight: '600' },
    demo: { fontFamily: MONO, fontSize: 9.5, color: t.inkFaint, marginTop: 9 },
  });
