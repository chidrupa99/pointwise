/**
 * Welcome-offer progress, on the card tile.
 *
 * This is the one number in the app with a cliff edge under it. Every other
 * figure is a comparison between two rates that differ by a few dollars; miss
 * a 75,000-point offer by one day or one dollar and the whole thing pays
 * nothing. So the three states read differently on purpose -- in progress,
 * earned, and missed must never be mistakable for one another at a glance,
 * which is what a single bar with a percentage would make them.
 *
 * Colours come from the card's finish, not the theme. These sit on champagne
 * and titanium as well as gunmetal, and an earlier version that assumed white
 * tints was invisible on the light ones.
 */

import React from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { UI, type CardFinish, space } from '../theme';
import type { SignupBonus } from '../wallet';

/** Below this, the deadline stops being background information. */
const URGENT_DAYS = 30;

function dollars(raw: string): string {
  const n = Number(raw);
  return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
}

export function BonusBar({
  bonus,
  finish,
}: {
  bonus: SignupBonus;
  finish: CardFinish;
}) {
  const s = styles(finish);

  if (bonus.earned) {
    return (
      <View style={s.wrap}>
        <View style={s.track}>
          <View style={[s.fill, { width: '100%', backgroundColor: finish.on }]} />
        </View>
        <Text style={[s.note, { color: finish.on, fontWeight: '600' }]}>
          Offer earned · {Math.round(Number(bonus.points)).toLocaleString('en-US')}
        </Text>
      </View>
    );
  }

  if (bonus.expired) {
    // No bar at all. A part-filled bar under a closed window invites the
    // reader to think there is still something left to finish.
    return (
      <View style={s.wrap}>
        <Text style={s.note}>
          Offer closed · {dollars(bonus.remaining)} short
        </Text>
      </View>
    );
  }

  const urgent = bonus.days_left <= URGENT_DAYS;
  return (
    <View style={s.wrap}>
      <View style={s.row}>
        <Text style={s.label}>Welcome offer</Text>
        <Text style={[s.label, urgent && { color: finish.onWarn }]}>
          {bonus.days_left}d left
        </Text>
      </View>
      <View style={s.track}>
        <View
          style={[
            s.fill,
            {
              width: `${Math.max(2, Math.min(100, bonus.percent))}%`,
              backgroundColor: urgent ? finish.onWarn : finish.on,
            },
          ]}
        />
      </View>
      {/* Two short facts on one line. As a single sentence this ran to three
          lines on a 228pt tile and broke "at stake" across two of them. */}
      <View style={s.row}>
        <Text style={s.note}>{dollars(bonus.remaining)} to go</Text>
        <Text style={s.note}>{dollars(bonus.worth_dollars)} at stake</Text>
      </View>
    </View>
  );
}

const styles = (f: CardFinish) =>
  StyleSheet.create({
    wrap: { marginTop: space.md, gap: space.sm },
    row: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'baseline',
    },
    label: {
      fontFamily: UI,
      color: f.onSoft,
      fontSize: 10.5,
      letterSpacing: 0.9,
      textTransform: 'uppercase',
      fontWeight: '600',
    },
    track: {
      height: 5,
      borderRadius: 3,
      backgroundColor: f.hairline,
      overflow: 'hidden',
    },
    fill: { height: 5, borderRadius: 3 },
    note: {
      fontFamily: UI,
      color: f.onSoft,
      fontSize: 11.5,
      fontVariant: ['tabular-nums'],
    },
  });
