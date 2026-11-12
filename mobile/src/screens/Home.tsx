/** The home screen: the headline, the card rail, the audited feed.
 *
 * Activity rows are coloured by verdict -- jade where the best card was
 * already used, amber where money was left -- because the whole point of the
 * audit is that the misses are findable at a glance.
 *
 * Everything vertical comes from `space` in the theme. Chroma is reserved for
 * the cards and for the two verdicts; the chrome around them is ink and bone.
 */

import React, { useCallback, useEffect, useMemo, useState } from 'react';
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
import { CardTile, TILE_HEIGHT, TILE_WIDTH } from '../components/CardTile';
import { BAND_INK_FAINT, HeroBand, RAIL_LIFT } from '../components/HeroBand';
import { EmptyWallet } from '../components/EmptyWallet';
import { LocationBanner } from '../components/LocationBanner';
import {
  SPANS,
  fetchActivity,
  fetchPayPalStatus,
  fetchWallet,
  type Activity,
  withinPeriod,
  type PayPalStatus,
  type Span,
  type WalletResponse,
} from '../wallet';
import {
  SECTION_CAPS,
  UI,
  UI_BOLD,
  UI_SEMI,
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
  /** Opens the connect flow straight from the empty state. */
  onConnectIssuer: () => void;
  onOpenPay: () => void;
  /** Bumped by the parent after a card is added, to force a refetch. */
  reloadKey?: number;
}

export function Home({
  onOpenChat,
  onOpenAccount,
  onAddCard,
  onConnectIssuer,
  onOpenPay,
  reloadKey,
}: Props) {
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
  //: Which tile the rail is resting on, for the dots beneath it.
  const [cardIndex, setCardIndex] = useState(0);
  //: Which window the feed is showing. Starts wide: a demo wallet or a
  //: new user's first week would otherwise open on an empty list.
  const [span, setSpan] = useState<Span>('all');

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

  // Filtering happens here rather than at the API: every row is already
  // loaded, so a period change is instant and costs no round trip.
  const inPeriod = useMemo(
    () => activity.filter((a) => withinPeriod(a.on, span)),
    [activity, span],
  );
  const shown = showAll ? inPeriod : inPeriod.slice(0, PREVIEW_ROWS);
  const empty = wallet?.is_empty ?? false;

  const filtered = wallet?.cards.find((c) => c.card_id === filter);

  return (
    <View style={s.root}>
      <SafeAreaView style={s.safe} edges={['left', 'right']}>
        <ScrollView
          contentContainerStyle={s.scroll}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={busy}
              onRefresh={() => load(filter)}
              tintColor={BAND_INK_FAINT}
            />
          }
        >
          <HeroBand
            theme={theme}
            earned={wallet && !empty ? wallet.totals.value_earned_dollars : null}
            missed={wallet && !empty ? wallet.totals.missed_dollars : null}
            cardCount={wallet?.cards.length ?? 0}
            onOpenChat={onOpenChat}
            onOpenAccount={onOpenAccount}
            onOpenPay={onOpenPay}
          />

          <View style={s.page}>
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

          {empty && (
            <EmptyWallet
              theme={theme}
              onConnect={onConnectIssuer}
              onAddCard={onAddCard}
            />
          )}

          {wallet && !empty && (
            <>
              <Text style={[s.section, s.sectionPad]}>Your cards</Text>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                snapToInterval={TILE_WIDTH + space.md}
                decelerationRate="fast"
                onScroll={(e) =>
                  setCardIndex(
                    Math.round(
                      e.nativeEvent.contentOffset.x / (TILE_WIDTH + space.md),
                    ),
                  )
                }
                scrollEventThrottle={32}
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
                    onConnect={onConnectIssuer}
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

              {/* Which card you are on. Without it the rail gives no sign that
                  anything is off the right edge, and on a four-card wallet two
                  of them are never discovered. */}
              <View style={s.dots}>
                {wallet.cards.map((card, i) => (
                  <View
                    key={card.card_id}
                    style={[s.dot, i === cardIndex && s.dotOn]}
                  />
                ))}
              </View>

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

              <ScrollView
                horizontal
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={s.spans}
                style={s.spansOuter}
              >
                {SPANS.map((option) => {
                  const on = option.key === span;
                  return (
                    <Pressable
                      key={option.key}
                      accessibilityRole="button"
                      accessibilityState={{ selected: on }}
                      onPress={() => {
                        setSpan(option.key);
                        setShowAll(false);
                      }}
                      style={({ pressed }) => [
                        s.span,
                        on && s.spanOn,
                        pressed && { opacity: 0.7 },
                      ]}
                    >
                      <Text style={[s.spanText, on && s.spanTextOn]}>
                        {option.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </ScrollView>
            </View>
          )}

          <View style={s.feed}>
            {!empty &&
              shown.map((item) => (
                <ActivityRow key={item.transaction_id} item={item} theme={theme} />
              ))}
          </View>

          {!empty && inPeriod.length > PREVIEW_ROWS && (
            <Pressable
              accessibilityRole="button"
              onPress={() => setShowAll((v) => !v)}
              style={({ pressed }) => [s.more, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.moreText}>
                {showAll ? 'Show less' : `See all ${inPeriod.length}`}
              </Text>
            </Pressable>
          )}

          {!empty && inPeriod.length === 0 && !busy && (
            <Text style={s.none}>
              {activity.length === 0
                ? 'Nothing on this card yet.'
                : 'No purchases in this period.'}
            </Text>
          )}
          </View>
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    root: { flex: 1, backgroundColor: t.ground },
    safe: { flex: 1 },
    scroll: { paddingBottom: space.xxxl },

    // Everything below the band sits on paper and is lifted up over its edge.
    page: { marginTop: -RAIL_LIFT, paddingHorizontal: space.lg },



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

    section: { ...SECTION_CAPS, color: t.inkFaint },
    sectionPad: { marginTop: space.xl, marginBottom: space.md },

    railOuter: { marginHorizontal: -space.lg, marginBottom: space.md },
    dots: {
      flexDirection: 'row',
      justifyContent: 'center',
      gap: space.sm,
      marginBottom: space.xl,
    },
    dot: {
      width: 6,
      height: 6,
      borderRadius: 3,
      backgroundColor: t.rule,
    },
    dotOn: { backgroundColor: t.accent, width: 18 },
    rail: {
      gap: space.md,
      paddingHorizontal: space.lg,
      paddingVertical: space.sm,
    },
    add: {
      width: 132,
      height: TILE_HEIGHT,
      borderRadius: radius.xl,
      borderWidth: 1,
      borderStyle: 'dashed',
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
      gap: space.xs,
    },
    addPlus: { fontFamily: UI, fontSize: 24, color: t.inkFaint },
    addText: { ...type.small, color: t.inkFaint },

    feedHead: { gap: space.xs, marginBottom: space.md },
    feedHeadRow: {
      flexDirection: 'row',
      alignItems: 'baseline',
      justifyContent: 'space-between',
    },
    clear: { ...type.label, fontFamily: UI_SEMI, color: t.accent },
    scope: { ...type.small, color: t.inkFaint },

    // The period chips sit between the heading and the rows they govern.
    spansOuter: { marginHorizontal: -space.lg, marginTop: space.md },
    spans: { gap: space.sm, paddingHorizontal: space.lg },
    span: {
      paddingHorizontal: space.md,
      height: 32,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: t.rule,
      alignItems: 'center',
      justifyContent: 'center',
    },
    spanOn: { backgroundColor: t.accent, borderColor: t.accent },
    spanText: { ...type.small, fontFamily: UI_SEMI, color: t.inkSoft },
    spanTextOn: { color: t.accentInk },

    feed: { gap: space.sm },
    more: { alignItems: 'center', paddingVertical: space.lg },
    moreText: { ...type.label, fontFamily: UI_SEMI, color: t.accent },
    none: {
      ...type.label,
      color: t.inkFaint,
      textAlign: 'center',
      paddingVertical: space.xl,
    },
  });
