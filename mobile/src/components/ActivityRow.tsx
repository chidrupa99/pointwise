/**
 * One transaction, with its verdict.
 *
 * Three verdicts and three appearances, deliberately not interchangeable.
 * Green means the best available card was used; amber means money was left on
 * the table; grey means Pointwise cannot say. That last one used to render
 * green — which told a user whose cards we could not identify that they were
 * playing perfectly.
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { formatDate, type Activity } from '../wallet';
import { MONO, money, type Theme } from '../theme';

export function ActivityRow({ item, theme }: { item: Activity; theme: Theme }) {
  const s = styles(theme);
  const missed = item.verdict === 'missed';
  const unknown = item.verdict === 'unknown';

  return (
    <View
      style={[s.row, missed ? s.rowMissed : unknown ? s.rowUnknown : s.rowOptimal]}
    >
      <View style={s.rowMid}>
        <Text style={s.rowMerchant}>{item.merchant_name}</Text>
        <Text style={s.rowMeta}>
          {formatDate(item.on)} ·{' '}
          {item.card_name ??
            (item.card_id ? 'card not in your wallet' : 'card unknown')}
        </Text>

        {/* A category read off the merchant's name is a guess, and the row
            says so rather than letting the figure imply a lookup. */}
        {item.category_confidence === 'inferred' && (
          <Text style={s.rowGuess}>
            read as {item.category.replace(/_/g, ' ')}
          </Text>
        )}
        {item.category_confidence === 'none' && (
          <Text style={s.rowGuess}>
            shop type unknown · scored at the base rate
          </Text>
        )}

        {missed ? (
          <Text style={s.rowMissedNote}>
            {item.best_card_name} would have earned {money(item.missed_dollars)}{' '}
            more
          </Text>
        ) : unknown ? (
          // Two different unknowns. We know which card paid for anything
          // Pointwise routed -- it is in the ledger -- so "not identified"
          // there would understate what we know and read as a fault. The
          // honest distinction is whether the card is one the user holds.
          <Text style={s.rowUnknownNote}>
            {item.card_id
              ? 'Add this card to score it'
              : 'No card reported for this payment'}
          </Text>
        ) : (
          <Text style={s.rowOkNote}>Best card used</Text>
        )}
      </View>

      <View style={s.rowEnd}>
        <Text style={s.rowAmount}>{money(item.amount)}</Text>
        {!unknown && (
          <Text style={[s.rowEarned, missed && { color: theme.warn }]}>
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
      gap: 12,
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      borderRadius: 11,
      padding: 13,
    },
    rowMissed: { borderLeftWidth: 3, borderLeftColor: t.warn },
    rowOptimal: { borderLeftWidth: 3, borderLeftColor: t.ok },
    rowUnknown: { borderLeftWidth: 3, borderLeftColor: t.rule },
    rowMid: { flex: 1, gap: 2 },
    rowMerchant: { fontSize: 16, fontWeight: '600', color: t.ink },
    rowMeta: { fontFamily: MONO, fontSize: 12, color: t.inkFaint },
    rowGuess: { fontSize: 12, color: t.inkFaint, fontStyle: 'italic' },
    rowMissedNote: { fontSize: 13, color: t.warn },
    rowOkNote: { fontSize: 13, color: t.ok, fontWeight: '600' },
    rowUnknownNote: { fontSize: 13, color: t.inkFaint },
    rowEnd: { alignItems: 'flex-end', gap: 2 },
    rowAmount: {
      fontFamily: MONO,
      fontSize: 16,
      color: t.ink,
      fontVariant: ['tabular-nums'],
    },
    rowEarned: {
      fontFamily: MONO,
      fontSize: 13,
      color: t.ok,
      fontVariant: ['tabular-nums'],
    },
  });
