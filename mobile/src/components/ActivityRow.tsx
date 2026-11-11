/**
 * One transaction, with its verdict.
 *
 * Three verdicts and three appearances, deliberately not interchangeable.
 * Jade means the best available card was used; amber means money was left on
 * the table; grey means Pointwise cannot say. That last one used to render
 * green -- which told a user whose cards we could not identify that they were
 * playing perfectly.
 *
 * The verdict is carried by a short rule at the left edge rather than a tinted
 * panel. A row is mostly figures, and a wash of colour behind them makes the
 * feed look like a spreadsheet with conditional formatting.
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { formatDate, type Activity } from '../wallet';
import { MONO, UI, money, radius, space, type, type Theme } from '../theme';

export function ActivityRow({ item, theme }: { item: Activity; theme: Theme }) {
  const s = styles(theme);
  const missed = item.verdict === 'missed';
  const unknown = item.verdict === 'unknown';
  const edge = missed ? theme.warn : unknown ? theme.rule : theme.ok;

  return (
    <View style={s.row}>
      <View style={[s.edge, { backgroundColor: edge }]} />
      <View style={s.mid}>
        <Text style={s.merchant} numberOfLines={1}>
          {item.merchant_name}
        </Text>
        <Text style={s.meta}>
          {formatDate(item.on)} ·{' '}
          {item.card_name ??
            (item.card_id ? 'card not in your wallet' : 'card unknown')}
        </Text>

        {/* A category read off the merchant's name is a guess, and the row
            says so rather than letting the figure imply a lookup. */}
        {item.category_confidence === 'inferred' && (
          <Text style={s.guess}>read as {item.category.replace(/_/g, ' ')}</Text>
        )}
        {item.category_confidence === 'none' && (
          <Text style={s.guess}>shop type unknown · scored at the base rate</Text>
        )}

        {missed ? (
          <Text style={[s.note, { color: theme.warn }]}>
            {item.best_card_name} would have earned {money(item.missed_dollars)} more
          </Text>
        ) : unknown ? (
          // Two different unknowns. We know which card paid for anything
          // Pointwise routed -- it is in the ledger -- so "not identified"
          // there would understate what we know and read as a fault. The
          // honest distinction is whether the card is one the user holds.
          <Text style={[s.note, { color: theme.inkFaint }]}>
            {item.card_id
              ? 'Add this card to score it'
              : 'No card reported for this payment'}
          </Text>
        ) : (
          <Text style={[s.note, { color: theme.ok }]}>Best card used</Text>
        )}
      </View>

      <View style={s.end}>
        <Text style={s.amount}>{money(item.amount)}</Text>
        {!unknown && (
          <Text style={[s.earned, { color: missed ? theme.warn : theme.ok }]}>
            +{money(item.earned_dollars)}
          </Text>
        )}
      </View>
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    row: {
      flexDirection: 'row',
      gap: space.md,
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      borderRadius: radius.lg,
      padding: space.lg,
      paddingLeft: space.md,
    },
    edge: { width: 3, borderRadius: 2 },
    mid: { flex: 1, gap: 2 },
    merchant: {
      fontFamily: UI,
      fontSize: 16,
      fontWeight: '600',
      color: t.ink,
      letterSpacing: -0.2,
    },
    meta: { ...type.figureSmall, color: t.inkFaint },
    guess: { ...type.small, color: t.inkFaint, fontStyle: 'italic' },
    note: { ...type.label, marginTop: space.xs },
    end: { alignItems: 'flex-end', gap: 2 },
    amount: {
      fontFamily: MONO,
      fontSize: 16,
      color: t.ink,
      fontVariant: ['tabular-nums'],
    },
    earned: { ...type.figureSmall, fontVariant: ['tabular-nums'] },
  });
