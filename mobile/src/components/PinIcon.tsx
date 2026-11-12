/**
 * A map pin.
 *
 * Replaces the `◎` the location banner used to carry, which is a circled
 * ring -- a target or a record button, not a place. The banner is about
 * where you are standing, and the pin is the one shape that says so without
 * a caption.
 *
 * Drawn rather than set in type: a glyph is at the mercy of whatever font
 * happens to resolve it, and this one has to sit on a coloured band at a
 * fixed optical size.
 */

import React from 'react';
import Svg, { Circle, Path } from 'react-native-svg';

export function PinIcon({ size = 18, color }: { size?: number; color: string }) {
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {/* Teardrop: the body is a circle, the tip is where it meets the
          ground, so the whole mark points at a spot rather than filling a
          box. */}
      <Path
        d="M12 2.5c-4 0-7 3-7 6.8 0 5 6.1 11.4 6.4 11.7a.9.9 0 0 0 1.3 0C13 20.7 19 14.3 19 9.3c0-3.8-3-6.8-7-6.8z"
        fill="none"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
      />
      <Circle cx={12} cy={9.2} r={2.4} fill={color} />
    </Svg>
  );
}
