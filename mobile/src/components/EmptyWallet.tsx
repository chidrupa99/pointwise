/**
 * What a new user sees first.
 *
 * Pointwise cannot say anything useful until it knows what you carry -- every
 * recommendation is a ranking of your own cards -- so this screen's whole job
 * is to make adding the first one the obvious next action, and to be straight
 * about what it does and does not connect to.
 *
 * Three sentences, once each. An earlier version explained the ranking in the
 * body and then explained it again in the footnote, which reads as a product
 * that is nervous about itself.
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { UI, radius, space, type, type Theme } from '../theme';

export function EmptyWallet({
  theme,
  onAddCard,
}: {
  theme: Theme;
  onAddCard: () => void;
}) {
  const s = styles(theme);
  return (
    <View style={s.panel}>
      <Text style={s.title}>No cards yet</Text>
      <Text style={s.body}>
        Pointwise ranks the cards you actually carry, and shows the arithmetic
        behind every answer.
      </Text>
      <Pressable
        accessibilityRole="button"
        onPress={onAddCard}
        style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
      >
        <Text style={s.ctaText}>Add your first card</Text>
      </Pressable>
      <Text style={s.note}>
        Nothing connects to your bank. You choose the card at checkout --
        Pointwise only tells you which one earns most.
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
      fontFamily: UI,
      color: t.accentInk,
      fontSize: 16,
      fontWeight: '600',
    },
    note: { ...type.small, lineHeight: 17, color: t.inkFaint },
  });
