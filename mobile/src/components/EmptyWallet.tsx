/**
 * What a new user sees first.
 *
 * Pointwise cannot say anything useful until it knows what you carry — every
 * recommendation is a ranking of your own cards — so this screen's whole job is
 * to make adding the first one the obvious next action, and to be straight
 * about what it does and does not connect to.
 */

import React from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Theme } from '../theme';

export function EmptyWallet({
  theme,
  onAddCard,
}: {
  theme: Theme;
  onAddCard: () => void;
}) {
  const s = styles(theme);
  return (
    <View style={s.blank}>
      <Text style={s.blankTitle}>No cards yet</Text>
      <Text style={s.blankBody}>
        Pointwise needs to know what is in your wallet before it can tell you
        which card to use. Add the cards you carry and it will rank them on
        every purchase, and show you the arithmetic behind the answer.
      </Text>
      <Pressable
        accessibilityRole="button"
        onPress={onAddCard}
        style={({ pressed }) => [s.blankCta, pressed && { opacity: 0.8 }]}
      >
        <Text style={s.blankCtaText}>Add your first card</Text>
      </Pressable>
      <Text style={s.blankNote}>
        Nothing is connected to your bank or to PayPal's wallet. You pick
        cards from a list, Pointwise ranks them, and you choose the card at
        checkout yourself. It cannot pick it for you.
      </Text>
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    blank: {
      backgroundColor: t.surface,
      borderRadius: 16,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      padding: 20,
      marginTop: 8,
      gap: 12,
    },
    blankTitle: { fontSize: 22, fontWeight: '700', color: t.ink },
    blankBody: { fontSize: 15, lineHeight: 22, color: t.inkSoft },
    blankCta: {
      backgroundColor: t.accent,
      borderRadius: 12,
      paddingVertical: 14,
      alignItems: 'center',
      marginTop: 4,
    },
    blankCtaText: { color: t.accentInk, fontSize: 16, fontWeight: '600' },
    blankNote: { fontSize: 12, lineHeight: 18, color: t.inkFaint },
  });
