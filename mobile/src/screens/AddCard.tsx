/**
 * Your cards, grouped by the bank that issues them.
 *
 * A checkbox rather than a one-way "add": the list is a statement of what you
 * carry, and that is something you correct as well as extend. Until this
 * screen there was no way to take a card out of the wallet at all.
 *
 * Grouping by issuer is what makes the disabled rows make sense. A bank sits
 * above its cards with what we know about it -- connected or not -- so a row
 * that cannot be ticked has its explanation directly above it instead of
 * looking like an arbitrary refusal.
 *
 * A card with a welcome offer still asks when it was opened, because the
 * window has to start somewhere. One without an offer is added on the tap.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
  fetchCatalog,
  removeCard,
  type CatalogCard,
} from '../wallet';
import {
  MONO_MED,
  UI,
  UI_BOLD,
  UI_SEMI,
  cardFinish,
  dark,
  light,
  radius,
  space,
  type,
  type Theme,
} from '../theme';

interface Props {
  onDone: (changed: boolean) => void;
  onConnect: () => void;
}

/** Recent months, newest first — the window that matters for a welcome offer. */
function recentMonths(count: number): { label: string; iso: string }[] {
  const out: { label: string; iso: string }[] = [];
  const now = new Date();
  for (let i = 0; i < count; i += 1) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    out.push({
      label: d.toLocaleDateString('en-US', { month: 'short', year: '2-digit' }),
      iso: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`,
    });
  }
  return out;
}

export function AddCard({ onDone, onConnect }: Props) {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [catalog, setCatalog] = useState<CatalogCard[] | null>(null);
  const [dating, setDating] = useState<CatalogCard | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);

  const load = useCallback(async () => {
    try {
      setCatalog((await fetchCatalog()).cards);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** Issuers in catalogue order, each with its own cards. */
  const banks = useMemo(() => {
    const order: string[] = [];
    const by: Record<string, CatalogCard[]> = {};
    for (const c of catalog ?? []) {
      if (!by[c.issuer]) {
        by[c.issuer] = [];
        order.push(c.issuer);
      }
      by[c.issuer].push(c);
    }
    return order.map((issuer) => ({
      issuer,
      cards: by[issuer],
      // A bank counts as connected when any of its cards has a statement
      // behind it. That is the same fact the blocked rows are derived from,
      // so the heading and the rows can never disagree.
      connected: by[issuer].some((c) => c.statement_linked),
    }));
  }, [catalog]);

  const apply = useCallback(
    async (card: CatalogCard, openedOn: string | null) => {
      setBusyId(card.card_id);
      setError(null);
      try {
        if (card.held) {
          await removeCard(card.card_id);
        } else {
          await addCard(card.card_id, openedOn);
        }
        setChanged(true);
        await load();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusyId(null);
        setDating(null);
      }
    },
    [load],
  );

  const toggle = useCallback(
    (card: CatalogCard) => {
      if (card.blocked_reason) return;
      // Only an offer needs a date, and only when adding: removing a card
      // never has a window to place.
      if (!card.held && card.signup_bonus) {
        setDating(card);
        return;
      }
      void apply(card, null);
    },
    [apply],
  );

  // When did you open it? Asked only for a card that carries an offer.
  if (dating) {
    const finish = cardFinish(dating.card_id);
    return (
      <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
        <View style={s.bar}>
          <Pressable accessibilityRole="button" onPress={() => setDating(null)}>
            <Text style={s.back}>Back</Text>
          </Pressable>
          <Text style={s.title}>When did you open it?</Text>
          <View style={s.barSpacer} />
        </View>
        <ScrollView contentContainerStyle={s.scroll}>
          <View style={[s.chosen, { backgroundColor: finish.gradient[0] }]}>
            <Text style={[s.chosenName, { color: finish.on }]}>{dating.name}</Text>
            <Text style={[s.chosenIssuer, { color: finish.onSoft }]}>
              {dating.issuer}
            </Text>
          </View>
          <Text style={s.why}>
            {dating.name} has a welcome offer worth about $
            {Math.round(Number(dating.signup_bonus!.worth_dollars))} — spend $
            {Number(dating.signup_bonus!.spend_required).toLocaleString('en-US')}{' '}
            within {dating.signup_bonus!.within_months} months. Tell Pointwise
            when you opened the account and it will track how far along you are.
          </Text>
          <View style={s.months}>
            {recentMonths(18).map((m) => (
              <Pressable
                key={m.iso}
                accessibilityRole="button"
                disabled={busyId !== null}
                onPress={() => void apply(dating, m.iso)}
                style={({ pressed }) => [s.month, pressed && { opacity: 0.6 }]}
              >
                <Text style={s.monthText}>{m.label}</Text>
              </Pressable>
            ))}
          </View>
          <Pressable
            accessibilityRole="button"
            disabled={busyId !== null}
            onPress={() => void apply(dating, null)}
            style={({ pressed }) => [s.noDate, pressed && { opacity: 0.6 }]}
          >
            <Text style={s.noDateText}>
              I do not remember — add it without a date
            </Text>
          </Pressable>
          {error && <Text style={s.error}>{error}</Text>}
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
      <View style={s.bar}>
        <Pressable accessibilityRole="button" onPress={() => onDone(changed)}>
          <Text style={s.back}>Done</Text>
        </Pressable>
        <Text style={s.title}>Your cards</Text>
        <View style={s.barSpacer} />
      </View>

      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={s.lead}>
          Tick the cards you carry. Pointwise ranks every one of them on every
          purchase, so a card you take out stops being recommended.
        </Text>

        {!catalog && !error && (
          <ActivityIndicator style={s.spinner} color={theme.inkFaint} />
        )}
        {error && <Text style={s.error}>{error}</Text>}

        {banks.map((bank) => (
          <View key={bank.issuer} style={s.bank}>
            <View style={s.bankHead}>
              <Text style={s.bankName}>{bank.issuer}</Text>
              <Text style={[s.bankState, bank.connected && s.bankStateOn]}>
                {bank.connected ? 'Connected' : 'Not connected'}
              </Text>
            </View>

            {bank.cards.map((card) => {
              const finish = cardFinish(card.card_id);
              const blocked = card.blocked_reason !== null;
              return (
                <Pressable
                  key={card.card_id}
                  accessibilityRole="checkbox"
                  accessibilityState={{ checked: card.held, disabled: blocked }}
                  accessibilityLabel={
                    blocked
                      ? `${card.name}. ${card.blocked_reason}.`
                      : `${card.name}, ${card.held ? 'in wallet' : 'not in wallet'}`
                  }
                  disabled={blocked || busyId !== null}
                  onPress={() => toggle(card)}
                  style={({ pressed }) => [
                    s.row,
                    blocked && s.rowOff,
                    pressed && !blocked && { opacity: 0.6 },
                  ]}
                >
                  <View style={[s.box, card.held && s.boxOn, blocked && s.boxOff]}>
                    {busyId === card.card_id ? (
                      <ActivityIndicator size="small" color={theme.accentInk} />
                    ) : card.held ? (
                      <Text style={s.tick}>✓</Text>
                    ) : null}
                  </View>

                  <View
                    style={[s.chip, { backgroundColor: finish.gradient[0] }]}
                  />

                  <View style={s.flex}>
                    <Text style={s.rowName} numberOfLines={1}>
                      {card.name}
                    </Text>
                    <Text style={s.rowMeta} numberOfLines={1}>
                      {Number(card.annual_fee) > 0
                        ? `$${Number(card.annual_fee)}/yr`
                        : 'no annual fee'}
                      {' · '}
                      {card.headline}
                    </Text>
                    {/* The reason sits on the row it disables. A greyed row
                        with the explanation elsewhere reads as a bug. */}
                    {blocked && (
                      <Text style={s.rowBlocked}>{card.blocked_reason}</Text>
                    )}
                  </View>

                  {card.signup_bonus && !card.held && !blocked && (
                    <View style={s.offer}>
                      <Text style={s.offerValue}>
                        {Math.round(Number(card.signup_bonus.points) / 1000)}k
                      </Text>
                      <Text style={s.offerLabel}>bonus</Text>
                    </View>
                  )}
                </Pressable>
              );
            })}

            {!bank.connected && (
              <Pressable
                accessibilityRole="button"
                onPress={onConnect}
                style={({ pressed }) => [s.connect, pressed && { opacity: 0.6 }]}
              >
                <Text style={s.connectText}>
                  Connect {bank.issuer} to read these statements &rarr;
                </Text>
              </Pressable>
            )}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1, backgroundColor: t.ground },
    bar: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: space.lg,
      paddingVertical: space.md,
      borderBottomWidth: 1,
      borderBottomColor: t.rule,
    },
    back: { fontFamily: UI_SEMI, fontSize: 16, color: t.accent },
    barSpacer: { width: 44 },
    title: { fontFamily: UI, fontSize: 17, fontWeight: '700', color: t.ink },
    scroll: { padding: space.lg, gap: space.lg, paddingBottom: space.xxxl },
    lead: { ...type.small, lineHeight: 18, color: t.inkSoft },
    spinner: { marginTop: space.xl },
    error: { ...type.small, color: t.stop },
    flex: { flex: 1 },

    bank: { gap: space.xs },
    bankHead: {
      flexDirection: 'row',
      alignItems: 'baseline',
      justifyContent: 'space-between',
      marginBottom: 2,
    },
    bankName: { fontFamily: UI_BOLD, fontSize: 15, color: t.ink },
    bankState: { ...type.small, fontSize: 11, color: t.inkFaint },
    bankStateOn: { color: t.ok },

    row: {
      flexDirection: 'row',
      alignItems: 'center',
      gap: space.md,
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      borderRadius: radius.md,
      padding: space.md,
    },
    rowOff: { opacity: 0.45 },
    box: {
      width: 22,
      height: 22,
      borderRadius: 6,
      borderWidth: 1.5,
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
    },
    boxOn: { backgroundColor: t.accent, borderColor: t.accent },
    boxOff: { borderColor: t.ruleSoft },
    tick: { color: t.accentInk, fontSize: 14, fontWeight: '700' },
    chip: { width: 30, height: 20, borderRadius: 4 },
    rowName: { fontFamily: UI_SEMI, fontSize: 15, color: t.ink },
    rowMeta: { ...type.small, fontSize: 11.5, color: t.inkFaint, marginTop: 1 },
    rowBlocked: { ...type.small, fontSize: 11.5, color: t.warn, marginTop: 2 },

    offer: { alignItems: 'flex-end' },
    offerValue: { fontFamily: MONO_MED, fontSize: 14, color: t.accent },
    offerLabel: { ...type.small, fontSize: 9.5, color: t.inkFaint },

    connect: { paddingVertical: space.sm, paddingHorizontal: space.xs },
    connectText: { ...type.small, fontSize: 12, color: t.accent },

    chosen: { borderRadius: radius.md, padding: space.lg },
    chosenName: { fontFamily: UI_BOLD, fontSize: 20 },
    chosenIssuer: { fontFamily: UI, fontSize: 13, marginTop: 2 },
    why: { ...type.small, lineHeight: 19, color: t.inkSoft },
    months: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
    month: {
      borderWidth: 1,
      borderColor: t.rule,
      backgroundColor: t.surface,
      borderRadius: radius.pill,
      paddingVertical: space.sm,
      paddingHorizontal: space.md,
    },
    monthText: { fontFamily: UI, fontSize: 14, color: t.ink },
    noDate: { alignItems: 'center', paddingVertical: space.md },
    noDateText: { fontFamily: UI, fontSize: 14, color: t.accent },
  });
