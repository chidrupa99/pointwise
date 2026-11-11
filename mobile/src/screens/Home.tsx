/** The home screen: the headline, the card rail, the audited feed.
 *
 * Activity rows are coloured by verdict -- jade where the best card was
 * already used, amber where money was left -- because the whole point of the
 * audit is that the misses are findable at a glance.
 *
 * Everything vertical comes from `space` in the theme. Chroma is reserved for
 * the cards and for the two verdicts; the chrome around them is ink and bone.
 */

import { LinearGradient } from 'expo-linear-gradient';
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ActivityRow } from '../components/ActivityRow';
import { Brand } from '../components/Brand';
import { CardTile } from '../components/CardTile';
import { EmptyWallet } from '../components/EmptyWallet';
import { LocationBanner } from '../components/LocationBanner';
import {
  fetchActivity,
  fetchPayPalStatus,
  fetchWallet,
  type Activity,
  type PayPalStatus,
  type WalletResponse,
} from '../wallet';
import {
  SECTION_CAPS,
  UI,
  dark,
  light,
  money,
  radius,
  space,
  type,
  type Theme,
} from '../theme';

/** Rows shown before the feed is collapsed. */
const PREVIEW_ROWS = 6;

interface Props {
  onOpenChat: () => void;
  onOpenAccount: () => void;
  onAddCard: () => void;
  /** Bumped by the parent after a card is added, to force a refetch. */
  reloadKey?: number;
}

export function Home({ onOpenChat, onOpenAccount, onAddCard, reloadKey }: Props) {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [wallet, setWallet] = useState<WalletResponse | null>(null);
  const [activity, setActivity] = useState<Activity[]>([]);
  const [missedTotal, setMissedTotal] = useState('0');
  //: Which sources the feed drew on, e.g. 'plaid+pointwise'. The scope note
  //: is a claim about coverage, so it has to follow this rather than be
  //: written once and left to go stale when an issuer is linked.
  const [activitySource, setActivitySource] = useState('');
  const [filter, setFilter] = useState<string | null>(null);
  const [paypal, setPayPal] = useState<PayPalStatus | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(async (cardId: string | null) => {
    setError(null);
    try {
      const [w, a, p] = await Promise.all([
        fetchWallet(),
        fetchActivity(cardId),
        fetchPayPalStatus(),
      ]);
      setWallet(w);
      setActivity(a.activity);
      setMissedTotal(a.missed_total);
      setActivitySource(a.source);
      setPayPal(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach the engine');
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void load(filter);
  }, [filter, load, reloadKey]);

  const shown = showAll ? activity : activity.slice(0, PREVIEW_ROWS);
  const empty = wallet?.is_empty ?? false;
  const filtered = wallet?.cards.find((c) => c.card_id === filter);

  return (
    <View style={s.root}>
      <LinearGradient
        colors={[theme.groundLift, theme.ground]}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
        <View style={s.nav}>
          <View style={s.brand}>
            <Brand size={30} theme={theme} />
            <Text style={s.brandName}>Pointwise</Text>
          </View>
          <View style={s.navActions}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Ask Pointwise"
              onPress={onOpenChat}
              style={({ pressed }) => [s.askBtn, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.askText}>Ask</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Account and settings"
              onPress={onOpenAccount}
              style={({ pressed }) => [s.iconBtn, pressed && { opacity: 0.6 }]}
            >
              <View style={s.bar} />
              <View style={s.bar} />
              <View style={[s.bar, { width: 9 }]} />
            </Pressable>
          </View>
        </View>

        <ScrollView
          contentContainerStyle={s.scroll}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={busy}
              onRefresh={() => load(filter)}
              tintColor={theme.inkFaint}
            />
          }
        >
          {error && (
            <View style={s.errorBox}>
              <Text style={s.errorText}>{error}</Text>
            </View>
          )}

          <LocationBanner theme={theme} />

          {paypal && !paypal.configured && (
            <View style={s.banner}>
              <Text style={s.bannerText}>
                Showing sample activity until an issuer is linked.
              </Text>
            </View>
          )}

          {busy && !wallet && (
            <ActivityIndicator style={s.spinner} color={theme.inkFaint} />
          )}

          {empty && <EmptyWallet theme={theme} onAddCard={onAddCard} />}

          {wallet && !empty && (
            <View style={s.hero}>
              <Text style={s.heroLabel}>Left on the table</Text>
              <Text style={s.heroValue}>
                {money(wallet.totals.missed_dollars)}
              </Text>
              <Text style={s.heroSub}>
                {money(wallet.totals.value_earned_dollars)} earned ·{' '}
                {Math.round(Number(wallet.totals.points_earned)).toLocaleString(
                  'en-US',
                )}{' '}
                pts
              </Text>
            </View>
          )}

          {wallet && !empty && (
            <>
              <Text style={[s.section, s.sectionPad]}>Cards</Text>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={s.rail}
                style={s.railOuter}
              >
                {wallet.cards.map((card) => (
                  <CardTile
                    key={card.card_id}
                    card={card}
                    theme={theme}
                    active={filter === card.card_id}
                    onPress={() =>
                      setFilter(filter === card.card_id ? null : card.card_id)
                    }
                  />
                ))}
                <Pressable
                  accessibilityRole="button"
                  accessibilityLabel="Add a card"
                  onPress={onAddCard}
                  style={({ pressed }) => [s.add, pressed && { opacity: 0.6 }]}
                >
                  <Text style={s.addPlus}>+</Text>
                  <Text style={s.addText}>Add a card</Text>
                </Pressable>
              </ScrollView>
            </>
          )}

          {!empty && (
            <View style={s.feedHead}>
              <View style={s.feedHeadRow}>
                <Text style={s.section}>Activity</Text>
                {filter && (
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Clear card filter"
                    onPress={() => setFilter(null)}
                  >
                    <Text style={s.clear}>Clear</Text>
                  </Pressable>
                )}
              </View>
              {/* "Activity" alone invites the reader to assume this is all
                  their spending. One quiet line says what it actually covers,
                  and it changes the moment an issuer is linked. */}
              {activity.length > 0 && (
                <Text style={s.scope}>
                  {filtered
                    ? `${filtered.name} · ${money(missedTotal)} left`
                    : activitySource.includes('plaid')
                      ? 'Read from your linked card issuer'
                      : 'Link an issuer in Account to audit real spending'}
                </Text>
              )}
            </View>
          )}

          <View style={s.feed}>
            {!empty &&
              shown.map((item) => (
                <ActivityRow key={item.transaction_id} item={item} theme={theme} />
              ))}
          </View>

          {!empty && activity.length > PREVIEW_ROWS && (
            <Pressable
              accessibilityRole="button"
              onPress={() => setShowAll((v) => !v)}
              style={({ pressed }) => [s.more, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.moreText}>
                {showAll ? 'Show less' : `See all ${activity.length}`}
              </Text>
            </Pressable>
          )}

          {!empty && activity.length === 0 && !busy && (
            <Text style={s.none}>Nothing on this card yet.</Text>
          )}
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: t.ground },
    safe: { flex: 1 },
    scroll: { paddingHorizontal: space.lg, paddingBottom: space.xxxl },

    nav: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: space.lg,
      paddingBottom: space.md,
      paddingTop: space.xs,
    },
    brand: { flexDirection: 'row', alignItems: 'center', gap: space.md },
    brandName: {
      fontFamily: UI,
      fontSize: 19,
      fontWeight: '600',
      color: t.ink,
      letterSpacing: -0.3,
    },
    navActions: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
    askBtn: {
      paddingHorizontal: space.lg,
      height: 36,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
    },
    askText: { fontFamily: UI, fontSize: 14, fontWeight: '600', color: t.ink },
    iconBtn: {
      width: 36,
      height: 36,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
      gap: 3.5,
    },
    bar: { width: 14, height: 1.5, borderRadius: 1, backgroundColor: t.ink },

    errorBox: {
      backgroundColor: t.stopSoft,
      borderRadius: radius.md,
      padding: space.md,
      marginBottom: space.md,
    },
    errorText: { ...type.label, color: t.stop },
    banner: {
      backgroundColor: t.surface,
      borderRadius: radius.md,
      paddingVertical: space.md,
      paddingHorizontal: space.lg,
      marginBottom: space.md,
      borderWidth: 1,
      borderColor: t.ruleSoft,
    },
    bannerText: { ...type.label, color: t.inkSoft },
    spinner: { marginTop: space.xxl },

    hero: { paddingTop: space.xl, paddingBottom: space.xxl },
    heroLabel: { ...SECTION_CAPS, color: t.inkFaint },
    heroValue: {
      ...type.hero,
      color: t.ink,
      marginTop: space.sm,
      // Didot's figures are drawn tight; a touch of negative tracking keeps a
      // five-character amount from reading as five separate glyphs.
      letterSpacing: -1.5,
    },
    heroSub: {
      ...type.label,
      color: t.inkFaint,
      marginTop: space.xs,
      fontVariant: ['tabular-nums'],
    },

    section: { ...SECTION_CAPS, color: t.inkFaint },
    sectionPad: { marginBottom: space.md },

    railOuter: { marginHorizontal: -space.lg, marginBottom: space.xxl },
    // Top-aligned, so a tile is only as tall as what it holds. Stretching
    // them to match left a void on any card with no live welcome offer.
    rail: {
      gap: space.md,
      paddingHorizontal: space.lg,
      paddingVertical: space.xs,
      alignItems: 'flex-start',
    },
    add: {
      width: 132,
      minHeight: 150,
      borderRadius: radius.xl,
      borderWidth: 1,
      borderStyle: 'dashed',
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
      gap: space.xs,
    },
    addPlus: { fontFamily: UI, fontSize: 24, color: t.inkFaint, fontWeight: '300' },
    addText: { ...type.small, color: t.inkFaint },

    feedHead: { gap: space.xs, marginBottom: space.md },
    feedHeadRow: {
      flexDirection: 'row',
      alignItems: 'baseline',
      justifyContent: 'space-between',
    },
    clear: { ...type.label, color: t.accent, fontWeight: '600' },
    scope: { ...type.small, color: t.inkFaint },

    feed: { gap: space.sm },
    more: { alignItems: 'center', paddingVertical: space.lg },
    moreText: { ...type.label, color: t.accent, fontWeight: '600' },
    none: {
      ...type.label,
      color: t.inkFaint,
      textAlign: 'center',
      paddingVertical: space.xl,
    },
  });
