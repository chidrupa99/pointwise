/**
 * The header band: the brand, the two actions, and the headline figure.
 *
 * Burnt orange, dark at the bottom where the page meets it, and the same in
 * either theme -- which is why its type colours are fixed here rather than
 * taken from the theme. Built from theme tokens the band came out the colour
 * of the page in dark mode and the whole header vanished.
 *
 * The page below is pulled up over its bottom edge by RAIL_LIFT, so the first
 * card sits across the seam instead of starting under it.
 */

import { LinearGradient } from 'expo-linear-gradient';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Brand } from './Brand';
import {
  SECTION_CAPS,
  UI_BOLD,
  UI_SEMI,
  money,
  radius,
  space,
  type,
  type Theme,
} from '../theme';

const BAND_TOP = '#C2561E';
const BAND_MID = '#8A3A14';
const BAND_BOTTOM = '#3A1709';

export const BAND_INK = '#FDF6EE';
const BAND_INK_SOFT = 'rgba(253,246,238,0.78)';
export const BAND_INK_FAINT = 'rgba(253,246,238,0.62)';
const BAND_RULE = 'rgba(253,246,238,0.34)';

/**
 * How far the page below is pulled up over the band's bottom edge.
 *
 * This, not the band's padding, is what decides how much orange is left
 * under the first thing on the page: the page's top sits RAIL_LIFT above the
 * band's bottom, so the gap underneath is RAIL_LIFT minus that element's
 * height. Growing the band's bottom padding moves the edge and the element
 * down together and changes nothing.
 *
 * The location banner is about 53 tall, so this leaves roughly 16 beneath
 * it, matching the rest of the page's rhythm.
 */
export const RAIL_LIFT = 70;

export function HeroBand({
  theme,
  earned,
  missed,
  cardCount,
  onOpenChat,
  onOpenAccount,
}: {
  theme: Theme;
  /** What the cards earned. Null while the wallet is still loading. */
  earned: string | null;
  missed: string | null;
  /** How many cards are in the wallet. One card has nothing to lose to. */
  cardCount: number;
  onOpenChat: () => void;
  onOpenAccount: () => void;
}) {
  return (
    <LinearGradient
      colors={[BAND_TOP, BAND_MID, BAND_BOTTOM] as const}
      start={{ x: 0.1, y: 0 }}
      end={{ x: 0.9, y: 1 }}
      style={s.band}
    >
      <SafeAreaView edges={['top']}>
        <View style={s.nav}>
          <View style={s.brand}>
            {/* The mark takes the band's dark ink, not the accent: orange
                on orange is not a mark. */}
            <Brand
              size={30}
              theme={theme}
              plateColor={BAND_BOTTOM}
              markColor={BAND_INK}
            />
            <Text style={s.brandName}>Pointwise</Text>
          </View>
          <View style={s.actions}>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Ask Pointwise"
              onPress={onOpenChat}
              style={({ pressed }) => [s.ask, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.askText}>Ask</Text>
            </Pressable>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Account and settings"
              onPress={onOpenAccount}
              style={({ pressed }) => [s.icon, pressed && { opacity: 0.6 }]}
            >
              <View style={s.bar} />
              <View style={s.bar} />
              <View style={[s.bar, { width: 9 }]} />
            </Pressable>
          </View>
        </View>

        {earned !== null && (
          <View style={s.hero}>
            {/* "Rewards", not "points": the total includes cash back from
                cards that earn no points at all. */}
            <Text style={s.label}>Total rewards</Text>
            <Text style={s.value}>{money(earned)}</Text>
            {/* Three different facts, not one sentence with a zero in it.
                Money was left; or every purchase already went on the best
                card; or there is only one card, in which case there was
                never an alternative and "nothing left behind" would be
                praise for a race with one runner. */}
            {missed !== null && Number(missed) > 0 ? (
              <Text style={s.sub}>
                You could have had{' '}
                <Text style={s.subStrong}>{money(missed)}</Text> more
              </Text>
            ) : missed !== null && cardCount > 1 ? (
              <Text style={s.sub}>Nothing left behind</Text>
            ) : missed !== null ? (
              <Text style={s.sub}>
                Add a second card and Pointwise can start comparing
              </Text>
            ) : null}
          </View>
        )}
      </SafeAreaView>
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  band: {
    paddingHorizontal: space.lg,
    paddingBottom: RAIL_LIFT + space.md,
    borderBottomLeftRadius: radius.xl,
    borderBottomRightRadius: radius.xl,
  },
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
  actions: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  ask: {
    paddingHorizontal: space.lg,
    height: 36,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: BAND_RULE,
    alignItems: 'center',
    justifyContent: 'center',
  },
  askText: { fontFamily: UI_SEMI, fontSize: 14, color: BAND_INK },
  icon: {
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

  hero: { paddingTop: space.xl, paddingBottom: space.sm },
  label: { ...SECTION_CAPS, color: BAND_INK_FAINT },
  value: {
    ...type.hero,
    color: BAND_INK,
    marginTop: space.sm,
    letterSpacing: -2,
  },
  sub: {
    ...type.body,
    color: BAND_INK_SOFT,
    marginTop: space.sm,
    fontVariant: ['tabular-nums'],
  },
  subStrong: { fontFamily: UI_BOLD, color: BAND_INK },
});
