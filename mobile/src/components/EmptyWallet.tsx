/**
 * What a new user sees first.
 *
 * Connecting is the front door, and adding by hand is the way round it. That
 * order matters: connecting answers both questions at once -- which cards you
 * carry, and what you have spent on them -- while the catalogue answers only
 * the first and leaves the feed empty. Leading with the catalogue made the
 * user add a card and then go and link it, two journeys asking the same
 * question with the reconciling left to them.
 *
 * The fallback is not decoration. Not every issuer can be linked, and someone
 * who would rather not connect a bank should still get ranked cards.
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { UI, UI_SEMI, radius, space, type, type Theme } from '../theme';

export function EmptyWallet({
  theme,
  onConnect,
  onAddCard,
}: {
  theme: Theme;
  onConnect: () => void;
  onAddCard: () => void;
}) {
  const s = styles(theme);
  return (
    <View style={s.panel}>
      <Text style={s.title}>Let&rsquo;s find your cards</Text>
      <Text style={s.body}>
        Connect your bank and Pointwise picks up the cards you carry and what
        you have spent on them, then shows which card should have paid.
      </Text>
      <Pressable
        accessibilityRole="button"
        onPress={onConnect}
        style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
      >
        <Text style={s.ctaText}>Connect your bank</Text>
      </Pressable>
      <Pressable
        accessibilityRole="button"
        onPress={onAddCard}
        style={({ pressed }) => [s.alt, pressed && { opacity: 0.6 }]}
      >
        <Text style={s.altText}>Add a card without connecting</Text>
      </Pressable>
      <Text style={s.note}>
        You sign in on your bank&rsquo;s own screen. Pointwise never sees your
        banking password, never asks for a card number, and cannot move money.
      </Text>
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    panel: {
      backgroundColor: t.surface,
      borderRadius: radius.xl,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      padding: space.xl,
      marginTop: space.lg,
      gap: space.md,
    },
    title: { ...type.title, color: t.ink },
    body: { ...type.body, color: t.inkSoft },
    cta: {
      backgroundColor: t.accent,
      borderRadius: radius.md,
      paddingVertical: space.lg,
      alignItems: 'center',
      marginTop: space.xs,
    },
    ctaText: {
      fontFamily: UI_SEMI,
      color: t.accentInk,
      fontSize: 16,
    },
    alt: { alignItems: 'center', paddingVertical: space.sm },
    altText: { ...type.label, fontFamily: UI_SEMI, color: t.accent },
    note: { ...type.small, lineHeight: 17, color: t.inkFaint },
  });
