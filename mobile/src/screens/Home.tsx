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
import { Brand } from '../components/Brand';
import { CardTile, TILE_HEIGHT, TILE_WIDTH } from '../components/CardTile';
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

/**
 * The band is burnt orange, dark at the bottom where the page meets it.
 * Type on it is always a warm off-white -- the headline figure included,
 * which has to invert here or it vanishes into its own background.
 */
/**
 * The band's own ink, fixed in both themes. Built from theme tokens it
 * came out the same colour as the page in dark mode and the header simply
 * vanished; against warm paper in light mode it has to stay dark anyway.
 */
const BAND_TOP = '#C2561E';
const BAND_MID = '#8A3A14';
const BAND_BOTTOM = '#3A1709';

const BAND_INK = '#FDF6EE';
const BAND_INK_SOFT = 'rgba(253,246,238,0.78)';
const BAND_INK_FAINT = 'rgba(253,246,238,0.62)';
const BAND_RULE = 'rgba(253,246,238,0.34)';

/** How far the card rail lifts into the band. */
const RAIL_LIFT = 56;

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
          {/* The band. Everything the screen is about -- who you are, what it
              cost you -- sits on ink, and the cards lift off its bottom edge
              into the page. The old version put all of this on the same flat
              paper as the feed, so nothing led. */}
          <LinearGradient
            colors={[BAND_TOP, BAND_MID, BAND_BOTTOM] as const}
            start={{ x: 0.1, y: 0 }}
            end={{ x: 0.9, y: 1 }}
            style={s.band}
          >
            <SafeAreaView edges={['top']}>
              <View style={s.nav}>
                <View style={s.brand}>
                  <Brand
                    size={30}
                    theme={theme}
                    plateColor={BAND_BOTTOM}
                    markColor={BAND_INK}
                  />
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

              {wallet && !empty && (
                <View style={s.hero}>
                  {/* "Earned on your cards", not "earned with Pointwise".
                      These rewards were earned whether or not this app
                      existed -- it reads the statement, it does not cause the
                      spending. Claiming the credit would be the easiest lie
                      on the screen and the first one a reader would catch. */}
                  {/* "Rewards", not "points": the total includes cash back
                      from two Citi cards, which earn no points at all. */}
                  <Text style={s.heroLabel}>Total rewards</Text>
                  <Text style={s.heroValue}>
                    {money(wallet.totals.value_earned_dollars)}
                  </Text>
                  {/* The app's own finding, in the colour that means money
                      left. A total of points was here and has gone: it added
                      Amex points to Capital One miles, two currencies at two
                      valuations, and counted the cash-back cards as zero. */}
                  <Text style={s.heroSub}>
                    You could have had{' '}
                    <Text style={s.heroSubStrong}>
                      {money(wallet.totals.missed_dollars)}
                    </Text>{' '}
                    more
                  </Text>
                </View>
              )}
            </SafeAreaView>
          </LinearGradient>

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

          {empty && <EmptyWallet theme={theme} onAddCard={onAddCard} />}

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

    band: {
      paddingHorizontal: space.lg,
      paddingBottom: RAIL_LIFT + space.lg,
      borderBottomLeftRadius: radius.xl,
      borderBottomRightRadius: radius.xl,
    },
    // Everything below the band sits on paper and is lifted up over its edge.
    page: { marginTop: -RAIL_LIFT, paddingHorizontal: space.lg },

    nav: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingTop: space.sm,
    },
    brand: { flexDirection: 'row', alignItems: 'center', gap: space.md },
    brandName: {
      fontFamily: UI_BOLD,
      fontSize: 19,
      color: BAND_INK,
      letterSpacing: -0.3,
    },
    navActions: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
    askBtn: {
      paddingHorizontal: space.lg,
      height: 36,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: BAND_RULE,
      alignItems: 'center',
      justifyContent: 'center',
    },
    askText: { fontFamily: UI_SEMI, fontSize: 14, color: BAND_INK },
    iconBtn: {
      width: 36,
      height: 36,
      borderRadius: radius.pill,
      borderWidth: 1,
      borderColor: BAND_RULE,
      alignItems: 'center',
      justifyContent: 'center',
      gap: 3.5,
    },
    bar: { width: 14, height: 1.5, borderRadius: 1, backgroundColor: BAND_INK },

    hero: { paddingTop: space.xxl, paddingBottom: space.sm },
    heroLabel: { ...SECTION_CAPS, color: BAND_INK_FAINT },
    heroValue: {
      ...type.hero,
      color: BAND_INK,
      marginTop: space.sm,
      letterSpacing: -2,
    },
    heroSub: {
      ...type.body,
      color: BAND_INK_SOFT,
      marginTop: space.sm,
      fontVariant: ['tabular-nums'],
    },
    heroSubStrong: { fontFamily: UI_BOLD, color: BAND_INK },

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
