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
  cardFinish,
  radius,
  space,
  type Theme,
} from '../theme';
import { inCardUnit, missedPhrase, unitLabel, type WalletCard } from '../wallet';

export const TILE_WIDTH = 228;

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
          <Text style={s.earned}>{inCardUnit(card, 'earned')}</Text>
          <Text style={s.unit}>{unitLabel(card.reward_unit)}</Text>
          {missed && (
            <Text style={[s.missed, { color: finish.onWarn }]}>
              {missedPhrase(card)}
            </Text>
          )}
        </View>

        {card.signup_bonus && (
          <>
            <View style={[s.hairline, { backgroundColor: finish.hairline }]} />
            <BonusBar bonus={card.signup_bonus} finish={finish} />
          </>
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
    face: { padding: space.lg, minHeight: 150 },
    name: {
      fontFamily: UI,
      fontSize: 16.5,
      fontWeight: '600',
      letterSpacing: -0.2,
      color: on,
    },
    issuer: {
      fontFamily: UI,
      fontSize: 11.5,
      letterSpacing: 0.9,
      textTransform: 'uppercase',
      color: onSoft,
      marginTop: 2,
    },
    figures: { marginTop: space.xl },
    earned: {
      fontFamily: MONO,
      fontSize: 28,
      letterSpacing: -1,
      color: on,
      fontVariant: ['tabular-nums'],
    },
    unit: { fontFamily: UI, fontSize: 12, color: onSoft, marginTop: 1 },
    missed: { fontFamily: UI, fontSize: 12, fontWeight: '600', marginTop: space.sm },
    hairline: { height: 1, marginTop: space.lg },
  });
