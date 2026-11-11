/**
 * The Pointwise mark.
 *
 * An apex rising over a baseline. The baseline is what a card earns by
 * default; the apex is the card that beats it, and the gap between them is
 * the whole product. It replaces a rounded square with a "P" in it, which
 * said nothing and is what every placeholder looks like.
 *
 * Drawn rather than set in type so it stays crisp at 24px in a nav bar and at
 * 72px on the sign-in screen, and so the apex can carry the accent while the
 * baseline stays quiet.
 */

import React from 'react';
import { View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';

import { radius, type Theme } from '../theme';

export function Brand({
  size = 30,
  theme,
  plate = true,
}: {
  size?: number;
  theme: Theme;
  /** False draws the mark alone, for places that already have a container. */
  plate?: boolean;
}) {
  const stroke = Math.max(2, size * 0.085);
  const mark = (
    <Svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      {plate && (
        <Rect width={32} height={32} rx={9} fill={theme.accent} />
      )}
      {/* The baseline: what the card in your pocket already earns. */}
      <Path
        d="M8 23.5 H24"
        stroke={plate ? theme.accentInk : theme.inkFaint}
        strokeOpacity={0.45}
        strokeWidth={stroke}
        strokeLinecap="round"
      />
      {/* The apex: the card that beats it. */}
      <Path
        d="M8 17.5 L16 8.5 L24 17.5"
        stroke={plate ? theme.accentInk : theme.accent}
        strokeWidth={stroke}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </Svg>
  );

  if (!plate) return mark;
  return (
    <View style={{ borderRadius: radius.md, overflow: 'hidden' }}>{mark}</View>
  );
}
