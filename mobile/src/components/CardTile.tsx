/**
 * One card in the rail, finished to look like the object in your wallet.
 *
 * The finish comes from the card, not the issuer: a Venture X is gunmetal and
 * an Amex Gold is champagne, whatever colour sits on the issuer's logo. That
 * also decides the type colour -- champagne and titanium need dark ink on
 * them, and an earlier flat-fill version put white text on both.
 *
 * Tiles are sized by their own content rather than stretched to match, so a
 * card with no live welcome offer is simply a shorter tile instead of a tall
 * one with a hole where the bar would be.
 */

import { LinearGradient } from 'expo-linear-gradient';
import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { BonusBar } from './BonusBar';
import {
  MONO,
  UI,
  UI_BOLD,
  UI_SEMI,
  cardFinish,
  radius,
  space,
  type Theme,
} from '../theme';
import { inCardUnit, missedPhrase, unitLabel, type WalletCard } from '../wallet';

export const TILE_WIDTH = 228;
/** Tall enough for a card carrying a welcome offer; the rest match it. */
export const TILE_HEIGHT = 190;

export function CardTile({
  card,
  theme,
  active,
  onPress,
}: {
  card: WalletCard;
  theme: Theme;
  active: boolean;
  onPress: () => void;
}) {
  const finish = cardFinish(card.card_id);
  const s = styles(finish.on, finish.onSoft);
  const missed = Number(card.missed_dollars) > 0;

  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
      accessibilityLabel={`${card.name}, ${inCardUnit(card, 'earned')} ${unitLabel(
        card.reward_unit,
      )} earned`}
      onPress={onPress}
      style={({ pressed }) => [
        s.shell,
        { shadowColor: theme.shade },
        active && { borderColor: theme.ink, borderWidth: 2 },
        pressed && { opacity: 0.9, transform: [{ scale: 0.99 }] },
      ]}
    >
      <LinearGradient
        colors={finish.gradient}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={s.face}
      >
        <Text style={s.name} numberOfLines={1}>
          {card.name}
        </Text>
        <Text style={s.issuer} numberOfLines={1}>
          {card.issuer}
        </Text>

        <View style={s.figures}>
          {/* Amount and unit share a baseline. Stacked they cost a line of
              height the tile does not have once an offer is on it. */}
          <View style={s.amountRow}>
            <Text style={s.earned}>{inCardUnit(card, 'earned')}</Text>
            <Text style={s.unit}>{unitLabel(card.reward_unit)}</Text>
          </View>
          {missed ? (
            <Text style={[s.missed, { color: finish.onWarn }]} numberOfLines={1}>
              {missedPhrase(card)}
            </Text>
          ) : (
            // A card with nothing left on it has earned the right to say so.
            // Blank here read as missing data rather than a clean sheet.
            <Text style={[s.clean, { color: finish.onSoft }]} numberOfLines={1}>
              Nothing left behind
            </Text>
          )}
        </View>

        {/* The spacer is what keeps the rail even. Tiles are all the height of
            the tallest, the figures sit at the same offset on every one, and
            an offer is pinned to the bottom edge rather than extending the
            card. Sizing each tile to its own content instead gave a row of
            three different heights, which looks like a layout fault. */}
        <View style={s.gap} />

        {card.signup_bonus && (
          <BonusBar bonus={card.signup_bonus} finish={finish} />
        )}
      </LinearGradient>
    </Pressable>
  );
}

const styles = (on: string, onSoft: string) =>
  StyleSheet.create({
    shell: {
      width: TILE_WIDTH,
      borderRadius: radius.xl,
      overflow: 'hidden',
      borderWidth: 2,
      borderColor: 'transparent',
      // A card is a physical object; it should sit above the page, not in it.
      shadowOpacity: 0.3,
      shadowRadius: 18,
      shadowOffset: { width: 0, height: 10 },
      elevation: 6,
    },
    // Fixed, not minimum: every tile in the rail is this tall, so the row
    // reads as one object instead of a staircase.
    face: { padding: space.lg, height: TILE_HEIGHT },
    name: {
      fontFamily: UI_BOLD,
      fontSize: 17,
      letterSpacing: -0.3,
      color: on,
    },
    issuer: {
      fontFamily: UI,
      fontSize: 11,
      letterSpacing: 0.4,
      color: onSoft,
      marginTop: 1,
    },
    figures: { marginTop: space.lg },
    amountRow: { flexDirection: 'row', alignItems: 'baseline', gap: space.sm },
    gap: { flex: 1, minHeight: space.md },
    earned: {
      fontFamily: MONO,
      fontSize: 26,
      letterSpacing: -1,
      color: on,
      fontVariant: ['tabular-nums'],
    },
    unit: { fontFamily: UI, fontSize: 12, color: onSoft },
    missed: { fontFamily: UI_SEMI, fontSize: 12, marginTop: space.sm },
    clean: { fontFamily: UI, fontSize: 12, marginTop: space.sm },
  });
