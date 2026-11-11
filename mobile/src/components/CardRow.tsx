/** One ranked card. Collapsed it shows the answer; expanded it shows the working. */

import React, { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { Evaluation } from '../api';
import { MONO, money, type Theme } from '../theme';

interface Props {
  evaluation: Evaluation;
  rank: number;
  theme: Theme;
  startExpanded?: boolean;
}

export function CardRow({ evaluation: ev, rank, theme, startExpanded = false }: Props) {
  const [open, setOpen] = useState(startExpanded);
  const s = styles(theme);
  const negative = Number(ev.net_value_dollars) < 0;

  return (
    <View style={s.card}>
      <Pressable
        onPress={() => setOpen((v) => !v)}
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        accessibilityLabel={`${ev.card_name}, ${money(ev.net_value_dollars)} back, ${ev.effective_rate_percent} percent effective`}
        style={({ pressed }) => [s.head, pressed && { backgroundColor: theme.sunk }]}
      >
        <Text style={s.rank}>{String(rank).padStart(2, '0')}</Text>
        <View style={s.headMid}>
          <Text style={s.name}>{ev.card_name}</Text>
          <Text style={s.meta}>
            {ev.issuer}
            {Number(ev.annual_fee) > 0 ? ` · $${ev.annual_fee}/yr` : ' · no annual fee'}
          </Text>
        </View>
        <View style={s.headEnd}>
          <Text style={[s.value, negative && { color: theme.stop }]}>
            {money(ev.net_value_dollars)}
          </Text>
          <Text style={s.rate}>{ev.effective_rate_percent}%</Text>
        </View>
      </Pressable>

      {open && (
        <View style={s.body}>
          {ev.components.map((c, i) => {
            const unit = c.unit === 'cashback_percent' ? '%' : 'x';
            const qty =
              c.unit === 'cashback_percent'
                ? ''
                : ` → ${Number(c.reward_quantity).toLocaleString('en-US')} pts`;
            return (
              <View key={`${c.rule_label}-${i}`} style={s.leg}>
                <Text style={s.legLeft} numberOfLines={2}>
                  <Text style={s.legStrong}>
                    {money(c.spend_applied)} @ {c.rate}
                    {unit}
                  </Text>
                  {qty}
                  <Text style={s.legWhy}> · {c.reason}</Text>
                </Text>
                <Text style={s.legRight}>{money(c.value_dollars)}</Text>
              </View>
            );
          })}

          {Number(ev.fees_dollars) > 0 && (
            <View style={s.leg}>
              <Text style={[s.legLeft, s.legStrong]}>foreign transaction fee</Text>
              <Text style={[s.legRight, { color: theme.stop }]}>
                −{money(ev.fees_dollars)}
              </Text>
            </View>
          )}

          {ev.caveats.map((caveat, i) => (
            <View key={i} style={s.caveat}>
              <Text style={s.caveatMark}>!</Text>
              <Text style={s.caveatText}>{caveat}</Text>
            </View>
          ))}

          {ev.unverified_rules.length > 0 && (
            <Text style={s.unverified}>
              unverified: {ev.unverified_rules.join(', ')}
            </Text>
          )}
        </View>
      )}
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    card: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 10,
      overflow: 'hidden',
    },
    head: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
    rank: { fontFamily: MONO, fontSize: 11, color: t.inkFaint, width: 20 },
    headMid: { flex: 1 },
    name: { fontSize: 15, fontWeight: '600', color: t.ink },
    meta: { fontSize: 11.5, color: t.inkFaint, marginTop: 1 },
    headEnd: { alignItems: 'flex-end' },
    value: { fontFamily: MONO, fontSize: 16, color: t.ink },
    rate: { fontFamily: MONO, fontSize: 10.5, color: t.inkFaint, marginTop: 1 },
    body: {
      paddingHorizontal: 14,
      paddingBottom: 13,
      paddingTop: 11,
      borderTopWidth: 1,
      borderTopColor: t.ruleSoft,
      gap: 5,
    },
    leg: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
    legLeft: { flex: 1, fontFamily: MONO, fontSize: 11.5, color: t.inkSoft },
    legStrong: { color: t.ink },
    legWhy: { color: t.inkFaint, fontSize: 11 },
    legRight: { fontFamily: MONO, fontSize: 11.5, color: t.inkSoft },
    caveat: {
      flexDirection: 'row',
      gap: 7,
      backgroundColor: t.warnSoft,
      borderRadius: 7,
      padding: 9,
      marginTop: 5,
    },
    caveatMark: { color: t.warn, fontWeight: '700', fontSize: 12 },
    caveatText: { flex: 1, color: t.warn, fontSize: 12, lineHeight: 16 },
    unverified: { fontFamily: MONO, fontSize: 10.5, color: t.inkFaint, marginTop: 6 },
  });
