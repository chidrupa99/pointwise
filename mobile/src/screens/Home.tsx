/** The home screen: navbar, My cards, My activity.
 *
 * Activity rows are coloured by verdict -- green where the best card was
 * already used, amber where money was left on the table -- because the whole
 * point of the audit is that the misses are findable at a glance.
 */

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
import { BonusBar } from '../components/BonusBar';
import { EmptyWallet } from '../components/EmptyWallet';
import { LocationBanner } from '../components/LocationBanner';
import {
  cardColor,
  fetchActivity,
  fetchPayPalStatus,
  fetchWallet,
  formatDate,
  inCardUnit,
  missedPhrase,
  unitLabel,
  type Activity,
  type PayPalStatus,
  type WalletResponse,
} from '../wallet';
import { MONO, dark, light, money, type Theme } from '../theme';

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

  const shown = showAll ? activity : activity.slice(0, 6);
  const empty = wallet?.is_empty ?? false;

  return (
    <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
      {/* Navbar */}
      <View style={s.nav}>
        <View style={s.brand}>
          <View style={s.mark}>
            <Text style={s.markText}>P</Text>
          </View>
          <Text style={s.brandName}>Pointwise</Text>
        </View>
        <View style={s.navActions}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Ask Pointwise"
            onPress={onOpenChat}
            style={({ pressed }) => [s.navBtn, pressed && { opacity: 0.6 }]}
          >
            <Text style={s.navBtnIcon}>✦</Text>
          </Pressable>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Account and settings"
            onPress={onOpenAccount}
            style={({ pressed }) => [s.navBtn, pressed && { opacity: 0.6 }]}
          >
            <Text style={s.navBtnIcon}>☰</Text>
          </Pressable>
        </View>
      </View>

      <ScrollView
        contentContainerStyle={s.scroll}
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
            <Text style={s.bannerTitle}>PayPal not connected</Text>
            <Text style={s.bannerBody}>
              Activity below is demo data. {paypal.hint}
            </Text>
          </View>
        )}

        {busy && !wallet && <ActivityIndicator style={s.spinner} color={theme.inkFaint} />}

        {empty && <EmptyWallet theme={theme} onAddCard={onAddCard} />}

        {/* Headline */}
        {wallet && !empty && (
          <View style={s.summary}>
            <Text style={s.summaryLabel}>LEFT ON THE TABLE</Text>
            <Text style={s.summaryValue}>{money(wallet.totals.missed_dollars)}</Text>
            <Text style={s.summarySub}>
              {money(wallet.totals.value_earned_dollars)} earned ·{' '}
              {Math.round(Number(wallet.totals.points_earned)).toLocaleString(
                'en-US',
              )}{' '}
              pts
            </Text>
          </View>
        )}

        {/* My cards */}
        {!empty && <Text style={s.section}>My cards</Text>}
        {wallet && !empty && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={s.cards}
            style={s.cardsRail}
          >
            {wallet.cards.map((card) => {
              const active = filter === card.card_id;
              return (
                <Pressable
                  key={card.card_id}
                  accessibilityRole="button"
                  accessibilityState={{ selected: active }}
                  accessibilityLabel={`${card.name}, ${card.points_earned} points earned`}
                  onPress={() => setFilter(active ? null : card.card_id)}
                  style={({ pressed }) => [
                    s.card,
                    { backgroundColor: cardColor(card.issuer, card.card_id) },
                    active && s.cardActive,
                    pressed && { opacity: 0.85 },
                  ]}
                >
                  <View style={s.cardTop}>
                    <Text style={s.cardName}>{card.name}</Text>
                    <Text style={s.cardIssuer}>{card.issuer}</Text>
                  </View>
                  <View style={s.cardBottom}>
                    <View>
                      <Text style={s.cardPoints}>
                        {inCardUnit(card, 'earned')}
                      </Text>
                      <Text style={s.cardPointsLabel}>
                        {unitLabel(card.reward_unit)}
                      </Text>
                    </View>
                    {Number(card.missed_dollars) > 0 && (
                      <Text style={s.cardMissed}>{missedPhrase(card)}</Text>
                    )}
                  </View>

                  {card.signup_bonus && (
                    <BonusBar bonus={card.signup_bonus} theme={theme} />
                  )}
                </Pressable>
              );
            })}

            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Add a card"
              onPress={onAddCard}
              style={({ pressed }) => [s.addCard, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.addCardPlus}>+</Text>
              <Text style={s.addCardText}>Add a card</Text>
            </Pressable>
          </ScrollView>
        )}

        {/* My activity */}
        {!empty && <View style={s.activityHead}>
          <Text style={s.section}>My activity</Text>
          {filter && (
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Clear card filter"
              onPress={() => setFilter(null)}
            >
              <Text style={s.clear}>Clear filter</Text>
            </Pressable>
          )}
        </View>}

        {/* "Activity" invites the reader to assume this is all their
            spending. Say what it actually covers, which changes the moment a
            card issuer is linked. */}
        {!empty && activity.length > 0 && (
          <Text style={s.scopeNote}>
            {activitySource.includes('plaid')
              ? 'Read from your linked card issuer.'
              : 'Link a card issuer in Account to see your real spending.'}
          </Text>
        )}

        {filter && (
          <Text style={s.filterNote}>
            {wallet?.cards.find((c) => c.card_id === filter)?.name} ·{' '}
            {money(missedTotal)} missed
          </Text>
        )}

        <View style={s.feed}>
          {!empty &&
            shown.map((item) => (
              <ActivityRow key={item.transaction_id} item={item} theme={theme} />
            ))}
        </View>

        {!empty && activity.length > 6 && (
          <Pressable
            accessibilityRole="button"
            onPress={() => setShowAll((v) => !v)}
            style={({ pressed }) => [s.seeAll, pressed && { opacity: 0.6 }]}
          >
            <Text style={s.seeAllText}>
              {showAll ? 'Show less' : `See all ${activity.length}`}
            </Text>
          </Pressable>
        )}

        {!empty && activity.length === 0 && !busy && (
          <Text style={s.empty}>No activity for this card yet.</Text>
        )}

      </ScrollView>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1, backgroundColor: t.ground },
    scroll: { paddingHorizontal: 16, paddingBottom: 48 },

    nav: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 16,
      paddingBottom: 12,
      paddingTop: 4,
    },
    brand: { flexDirection: 'row', alignItems: 'center', gap: 9 },
    mark: {
      width: 30,
      height: 30,
      borderRadius: 9,
      backgroundColor: t.accent,
      alignItems: 'center',
      justifyContent: 'center',
    },
    markText: { color: t.accentInk, fontWeight: '800', fontSize: 16 },
    brandName: { fontSize: 18, fontWeight: '700', color: t.ink, letterSpacing: -0.3 },
    navActions: { flexDirection: 'row', gap: 8 },
    navBtn: {
      width: 36,
      height: 36,
      borderRadius: 18,
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
    },
    navBtnIcon: { fontSize: 15, color: t.ink },

    errorBox: {
      backgroundColor: t.stopSoft,
      borderWidth: 1,
      borderColor: t.stop,
      borderRadius: 9,
      padding: 12,
      marginBottom: 12,
    },
    errorText: { color: t.stop, fontSize: 13 },
    banner: {
      backgroundColor: t.warnSoft,
      borderRadius: 10,
      padding: 13,
      marginBottom: 14,
    },
    bannerTitle: { color: t.warn, fontWeight: '700', fontSize: 13 },
    bannerBody: { color: t.warn, fontSize: 12.5, marginTop: 2, lineHeight: 17 },
    spinner: { marginTop: 40 },

    summary: { marginBottom: 22, marginTop: 4 },
    summaryLabel: {
      fontSize: 10,
      fontWeight: '700',
      letterSpacing: 1.3,
      color: t.inkFaint,
    },
    summaryValue: {
      fontFamily: MONO,
      fontSize: 38,
      color: t.warn,
      letterSpacing: -1,
      marginTop: 4,
    },
    summarySub: { fontSize: 13, color: t.inkSoft, marginTop: 2 },

    section: {
      fontSize: 16,
      fontWeight: '700',
      color: t.ink,
      letterSpacing: -0.2,
      marginBottom: 10,
    },

    cardsRail: { marginHorizontal: -16, marginBottom: 24 },
    cards: { gap: 10, paddingHorizontal: 16 },
    card: {
      width: 220,
      borderRadius: 14,
      padding: 16,
      minHeight: 132,
      justifyContent: 'space-between',
    },
    cardActive: { borderWidth: 2, borderColor: t.ink },
    cardBottom2: {},
    cardTop: {},
    cardName: { color: '#fff', fontSize: 16, fontWeight: '700', letterSpacing: -0.2 },
    cardIssuer: { color: 'rgba(255,255,255,0.72)', fontSize: 12, marginTop: 1 },
    cardBottom: { marginTop: 16 },
    cardPoints: { color: '#fff', fontFamily: MONO, fontSize: 22, letterSpacing: -0.5 },
    cardPointsLabel: { color: 'rgba(255,255,255,0.72)', fontSize: 11, marginTop: 1 },
    cardMissed: { color: '#ffd9a0', fontSize: 11.5, fontWeight: '600', marginTop: 5 },

    activityHead: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    clear: { color: t.accent, fontSize: 13, fontWeight: '600', marginBottom: 10 },
    filterNote: {
      fontFamily: MONO,
      fontSize: 11,
      color: t.inkFaint,
      marginBottom: 10,
      marginTop: -4,
    },

    feed: { gap: 8 },

    seeAll: { alignSelf: 'center', paddingVertical: 14 },
    seeAllText: { color: t.accent, fontSize: 14, fontWeight: '600' },
    empty: { color: t.inkFaint, fontSize: 13.5, textAlign: 'center', marginTop: 20 },
    scopeNote: {
      fontSize: 12,
      lineHeight: 17,
      color: t.inkFaint,
      marginTop: -4,
      marginBottom: 10,
    },

    // The add tile that sits at the end of the cards rail.
    addCard: {
      width: 150,
      borderRadius: 16,
      borderWidth: 1,
      borderStyle: 'dashed',
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
      gap: 4,
    },
    addCardPlus: { fontSize: 28, color: t.inkFaint, lineHeight: 32 },
    addCardText: { fontSize: 13, color: t.inkSoft, fontWeight: '600' },
  });
