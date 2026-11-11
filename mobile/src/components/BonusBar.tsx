/**
 * Welcome-offer progress, on the card tile.
 *
 * This is the one number in the app with a cliff edge under it. Every other
 * figure is a comparison between two rates that differ by a few dollars; miss
 * a 75,000-point offer by one day or one dollar and the whole thing pays
 * nothing. So the three states read differently on purpose -- in progress,
 * earned, and missed must never be mistakable for one another at a glance,
 * which is what a single bar with a percentage would make them.
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import type { Theme } from '../theme';
import type { SignupBonus } from '../wallet';

/** Below this, the deadline stops being background information. */
const URGENT_DAYS = 30;

function dollars(raw: string): string {
  const n = Number(raw);
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

export function BonusBar({
  bonus,
  theme,
}: {
  bonus: SignupBonus;
  theme: Theme;
}) {
  const s = styles(theme);

  if (bonus.earned) {
    return (
      <View style={s.wrap}>
        <View style={[s.track, s.trackDone]}>
          <View style={[s.fill, s.fillDone, { width: '100%' }]} />
        </View>
        <Text style={s.earned}>
          Welcome offer earned ·{' '}
          {Math.round(Number(bonus.points)).toLocaleString('en-US')} pts
        </Text>
      </View>
    );
  }

  if (bonus.expired) {
    // No bar at all. A part-filled bar on a closed window invites the reader
    // to think there is still something to finish.
    return (
      <View style={s.wrap}>
        <Text style={s.expired}>
          Offer window closed · {dollars(bonus.remaining)} short
        </Text>
      </View>
    );
  }

  const urgent = bonus.days_left <= URGENT_DAYS;
  return (
    <View style={s.wrap}>
      <View style={s.head}>
        <Text style={s.label}>Welcome offer</Text>
        <Text style={[s.days, urgent && s.daysUrgent]}>
          {bonus.days_left}d left
        </Text>
      </View>
      <View style={s.track}>
        <View
          style={[
            s.fill,
            urgent && s.fillUrgent,
            { width: `${Math.max(2, Math.min(100, bonus.percent))}%` },
          ]}
        />
      </View>
      <Text style={s.note}>
        {dollars(bonus.remaining)} more to go · {dollars(bonus.worth_dollars)}{' '}
        at stake
      </Text>
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    wrap: {
      marginTop: 12,
      paddingTop: 10,
      borderTopWidth: StyleSheet.hairlineWidth,
      // On a coloured card tile the rule has to be a tint of white, not the
      // theme's grey, or it disappears on the darker issuers.
      borderTopColor: 'rgba(255,255,255,0.25)',
    },
    head: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      marginBottom: 6,
    },
    label: {
      color: 'rgba(255,255,255,0.78)',
      fontSize: 11,
      letterSpacing: 0.6,
      textTransform: 'uppercase',
      fontWeight: '600',
    },
    days: { color: 'rgba(255,255,255,0.78)', fontSize: 11, fontWeight: '600' },
    daysUrgent: { color: t.warnSoft },
    track: {
      height: 6,
      borderRadius: 3,
      backgroundColor: 'rgba(255,255,255,0.2)',
      overflow: 'hidden',
    },
    trackDone: { backgroundColor: 'rgba(255,255,255,0.28)' },
    fill: { height: 6, borderRadius: 3, backgroundColor: '#ffffff' },
    fillUrgent: { backgroundColor: t.warnSoft },
    fillDone: { backgroundColor: t.okSoft },
    note: {
      color: 'rgba(255,255,255,0.72)',
      fontSize: 11,
      marginTop: 6,
      fontVariant: ['tabular-nums'],
    },
    earned: {
      color: t.okSoft,
      fontSize: 11,
      marginTop: 6,
      fontWeight: '600',
    },
    expired: {
      color: 'rgba(255,255,255,0.6)',
      fontSize: 11,
      fontVariant: ['tabular-nums'],
    },
  });
