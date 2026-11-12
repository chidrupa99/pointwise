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

import React, { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import {
  fetchNearby,
  getCurrentPosition,
  type BestCard,
  type MallStore,
  type NearbyPlace,
} from '../nearby';
import { PinIcon } from './PinIcon';
import { MONO, radius, space, type, money, type Theme } from '../theme';

/** How long a "nothing here" result stays before the banner resets. */
const EMPTY_LINGER_MS = 6000;

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
  const [picked, setPicked] = useState<string | null>(null);

  // Nothing found is not worth holding the top of the screen. Step back to
  // the invitation so the slot is useful again, and so a later tap can try
  // from a new position rather than re-reading the same dead end.
  useEffect(() => {
    if (state.kind !== 'empty') return;
    const t = setTimeout(() => setState({ kind: 'idle' }), EMPTY_LINGER_MS);
    return () => clearTimeout(t);
  }, [state.kind]);

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


  /**
   * What to do with a result: look again, or put it away.
   *
   * Named buttons rather than a cross in the corner. A cross on the
   * invitation was offering to remove the feature, which is not a thing
   * anyone wants from a banner they have not used yet; on a result it was
   * the only control, so "check again" had to be found elsewhere.
   *
   * Dismiss clears the result and goes back to the invitation rather than
   * hiding the banner for the session. Putting a result away is not the same
   * as saying you never want to be told where you are, and the second is not
   * recoverable without relaunching.
   */
  const actions = (
    <View style={s.actions}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Check this location again"
        onPress={locate}
        hitSlop={8}
        style={({ pressed }) => [s.action, pressed && { opacity: 0.6 }]}
      >
        <Text style={s.actionText}>Refresh</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Clear this location result"
        onPress={() => setState({ kind: 'idle' })}
        hitSlop={8}
        style={({ pressed }) => [s.action, pressed && { opacity: 0.6 }]}
      >
        <Text style={[s.actionText, s.actionQuiet]}>Dismiss</Text>
      </Pressable>
    </View>
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
          <View style={s.pin}>
            <PinIcon color={theme.accent} />
          </View>
          {/* The sentence says what you get; the button says what to tap.
              Before, the whole row was the target and nothing looked like a
              control, so it read as a notice you were meant to close. */}
          <View style={s.flex}>
            {/* Short enough to sit on one line beside the button. Two
                lines pushed the banner past the band's bottom edge. */}
            <Text style={s.inviteTitle} numberOfLines={1}>
              Best card where you are
            </Text>
          </View>
          <View style={s.cta}>
            <Text style={s.ctaText}>Check location</Text>
          </View>
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
        </View>
        {actions}
      </View>
    );
  }

  if (state.kind === 'empty') {
    // A null result is the one state with nothing to act on, so it gets the
    // least room: one line, and it steps back to the invitation on its own
    // rather than sitting at a dead end taking up the top of the screen.
    return (
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Look again"
        onPress={locate}
        style={({ pressed }) => [
          s.banner,
          s.inviteBanner,
          pressed && { opacity: 0.8 },
        ]}
      >
        <View style={s.row}>
          <View style={s.pin}>
            <PinIcon color={theme.accent} />
          </View>
          <Text style={[s.inviteTitle, s.flex]} numberOfLines={1}>
            No shop recognised here
          </Text>
          <View style={s.cta}>
            <Text style={s.ctaText}>Try again</Text>
          </View>
        </View>
      </Pressable>
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

        {actions}
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
      </View>
      {actions}
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    banner: {
      borderRadius: radius.lg,
      paddingVertical: space.md,
      paddingHorizontal: space.lg,
      marginBottom: space.md,
    },
    inviteBanner: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.ruleSoft,
    },
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

    row: { flexDirection: 'row', alignItems: 'center', gap: space.md },
    flex: { flex: 1 },
    pin: { marginTop: 1 },
    cta: {
      backgroundColor: t.accent,
      borderRadius: radius.pill,
      paddingVertical: 7,
      paddingHorizontal: space.md,
    },
    ctaText: {
      ...type.small,
      fontSize: 12.5,
      fontWeight: '700',
      color: t.accentInk,
    },
    actions: {
      flexDirection: 'row',
      gap: space.lg,
      marginTop: space.md,
      paddingTop: space.sm,
      borderTopWidth: 1,
      borderTopColor: t.ruleSoft,
    },
    action: { paddingVertical: 2 },
    actionText: { ...type.small, fontSize: 13, fontWeight: '700', color: t.accent },
    actionQuiet: { color: t.inkFaint, fontWeight: '600' },

    inviteTitle: { ...type.label, fontWeight: '600', color: t.ink },
    inviteBody: { ...type.small, color: t.inkSoft, marginTop: 2 },

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

  });
