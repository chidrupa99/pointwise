/**
 * Picking a card to add.
 *
 * A list, not a form. Pointwise can only price cards whose rules it holds, so
 * letting someone type a card name would mostly produce cards the engine
 * cannot score -- and a rewards app that shrugs at your card is worse than one
 * that never offered. Fourteen rows fit on a phone; a search box would be
 * ceremony.
 *
 * The open date is asked for second, and is skippable. It exists only to track
 * a welcome offer, and a user who does not remember should not be blocked --
 * they lose the progress bar, not the card.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  addCard,
  cardColor,
  fetchCatalog,
  type CatalogCard,
} from '../wallet';
import { MONO, UI, dark, light, radius, space, type Theme } from '../theme';

interface Props {
  onDone: (added: boolean) => void;
}

/** Recent months, newest first — the window that matters for a welcome offer. */
function recentMonths(count: number): { label: string; iso: string }[] {
  const out: { label: string; iso: string }[] = [];
  const now = new Date();
  for (let i = 0; i < count; i += 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push({
      label: d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      // The 1st of the month. A welcome window is counted in months, so the
      // day barely moves the deadline, and asking for it would be a date
      // picker nobody wants to operate at a kitchen table.
      iso: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`,
    });
  }
  return out;
}

export function AddCard({ onDone }: Props) {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [catalog, setCatalog] = useState<CatalogCard[] | null>(null);
  const [chosen, setChosen] = useState<CatalogCard | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCatalog()
      .then((r) => setCatalog(r.cards))
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const save = useCallback(
    async (openedOn: string | null) => {
      if (!chosen) return;
      setBusy(true);
      setError(null);
      try {
        await addCard(chosen.card_id, openedOn);
        onDone(true);
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
        setBusy(false);
      }
    },
    [chosen, onDone],
  );

  // Step two: when did you open it?
  if (chosen) {
    return (
      <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
        <View style={s.head}>
          <Pressable accessibilityRole="button" onPress={() => setChosen(null)}>
            <Text style={s.back}>Back</Text>
          </Pressable>
          <Text style={s.title}>When did you open it?</Text>
          <View style={s.headSpacer} />
        </View>

        <ScrollView contentContainerStyle={s.scroll}>
          <View
            style={[
              s.chosen,
              { backgroundColor: cardColor(chosen.issuer, chosen.card_id) },
            ]}
          >
            <Text style={s.chosenName}>{chosen.name}</Text>
            <Text style={s.chosenIssuer}>{chosen.issuer}</Text>
          </View>

          {chosen.signup_bonus ? (
            <Text style={s.why}>
              {chosen.name} has a welcome offer worth about{' '}
              {`$${Math.round(Number(chosen.signup_bonus.worth_dollars))}`} —
              spend ${Number(chosen.signup_bonus.spend_required).toLocaleString(
                'en-US',
              )}{' '}
              within {chosen.signup_bonus.within_months} months. Tell Pointwise
              when you opened the account and it will track how far along you
              are.
            </Text>
          ) : (
            <Text style={s.why}>
              Pointwise holds no welcome offer for this card, so the date is
              only for your own record.
            </Text>
          )}

          <View style={s.months}>
            {recentMonths(18).map((m) => (
              <Pressable
                key={m.iso}
                accessibilityRole="button"
                disabled={busy}
                onPress={() => void save(m.iso)}
                style={({ pressed }) => [s.month, pressed && s.monthOn]}
              >
                <Text style={s.monthText}>{m.label}</Text>
              </Pressable>
            ))}
          </View>

          <Pressable
            accessibilityRole="button"
            disabled={busy}
            onPress={() => void save(null)}
            style={({ pressed }) => [s.skip, pressed && { opacity: 0.6 }]}
          >
            <Text style={s.skipText}>
              I do not remember — add it without a date
            </Text>
          </Pressable>

          {busy && <ActivityIndicator color={theme.inkFaint} />}
          {error && <Text style={s.error}>{error}</Text>}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // Step one: which card?
  return (
    <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
      <View style={s.head}>
        <Pressable accessibilityRole="button" onPress={() => onDone(false)}>
          <Text style={s.back}>Cancel</Text>
        </Pressable>
        <Text style={s.title}>Add a card</Text>
        <View style={s.headSpacer} />
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        {!catalog && !error && (
          <ActivityIndicator style={s.spinner} color={theme.inkFaint} />
        )}
        {error && <Text style={s.error}>{error}</Text>}

        {catalog?.map((card) => (
          <Pressable
            key={card.card_id}
            accessibilityRole="button"
            accessibilityState={{ disabled: card.held }}
            disabled={card.held}
            onPress={() => setChosen(card)}
            style={({ pressed }) => [
              s.row,
              card.held && s.rowHeld,
              pressed && !card.held && { opacity: 0.7 },
            ]}
          >
            <View
              style={[
                s.swatch,
                { backgroundColor: cardColor(card.issuer, card.card_id) },
              ]}
            />
            <View style={s.rowMid}>
              <Text style={s.rowName}>{card.name}</Text>
              <Text style={s.rowMeta}>
                {card.issuer}
                {Number(card.annual_fee) > 0
                  ? ` · $${Number(card.annual_fee).toFixed(0)}/yr`
                  : ' · no annual fee'}
              </Text>
              {card.headline ? (
                <Text style={s.rowHeadline}>{card.headline}</Text>
              ) : null}
            </View>
            {card.held ? (
              <Text style={s.held}>In wallet</Text>
            ) : card.signup_bonus ? (
              <Text style={s.offer}>
                {Math.round(
                  Number(card.signup_bonus.points) / 1000,
                )}
                k
              </Text>
            ) : null}
          </Pressable>
        ))}

        <Text style={s.foot}>
          These are the cards Pointwise can price. Every rate comes from the
          rules corpus, and none of it has been checked by a person yet. Adding
          a card tells Pointwise you hold it; it does not connect to the
          issuer.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1, backgroundColor: t.ground },
    head: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: space.lg,
      paddingVertical: space.md,
      borderBottomWidth: StyleSheet.hairlineWidth,
      borderBottomColor: t.rule,
    },
    back: { color: t.accent, fontFamily: UI, fontSize: 16, minWidth: 64 },
    headSpacer: { minWidth: 64 },
    title: { fontFamily: UI, fontSize: 17, fontWeight: '700', color: t.ink },
    scroll: { padding: space.lg, paddingBottom: space.xxxl, gap: space.sm },
    spinner: { marginTop: space.xxl },

    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: space.md,
      backgroundColor: t.surface,
      borderRadius: radius.md,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      padding: space.md,
    },
    rowHeld: { opacity: 0.45 },
    swatch: { width: 34, height: 22, borderRadius: radius.sm },
    rowMid: { flex: 1, gap: space.xs },
    rowName: { fontFamily: UI, fontSize: 15, fontWeight: '600', color: t.ink },
    rowMeta: { fontFamily: UI, fontSize: 12, color: t.inkFaint },
    rowHeadline: { fontFamily: UI, fontSize: 12, color: t.inkSoft },
    held: { fontFamily: UI, fontSize: 11, color: t.inkFaint, fontWeight: '600' },
    offer: {
      fontFamily: MONO,
      fontSize: 13,
      color: t.ok,
      fontWeight: '700',
    },
    foot: { fontFamily: UI, fontSize: 12, lineHeight: 18, color: t.inkFaint, marginTop: space.md },

    chosen: { borderRadius: radius.md, padding: space.lg, gap: space.xs },
    chosenName: { color: '#fff', fontFamily: UI, fontSize: 19, fontWeight: '700' },
    chosenIssuer: { color: 'rgba(255,255,255,0.8)', fontFamily: UI, fontSize: 13 },
    why: { fontFamily: UI, fontSize: 14, lineHeight: 21, color: t.inkSoft, marginTop: space.xs },

    months: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.sm },
    month: {
      paddingVertical: space.sm,
      paddingHorizontal: space.md,
      borderRadius: radius.xl,
      borderWidth: 1,
      borderColor: t.rule,
      backgroundColor: t.surface,
    },
    monthOn: { backgroundColor: t.accentSoft, borderColor: t.accent },
    monthText: { fontFamily: UI, fontSize: 14, color: t.ink, fontVariant: ['tabular-nums'] },

    skip: { paddingVertical: space.md, alignItems: 'center' },
    skipText: { fontFamily: UI, fontSize: 14, color: t.accent },
    error: { fontFamily: UI, fontSize: 13, color: t.stop, marginTop: space.sm },
  });
