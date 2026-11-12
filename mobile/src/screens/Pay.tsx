/**
 * Pay through PayPal, on the card the engine picked.
 *
 * Every other screen is retrospective: here is what you spent, here is what
 * it should have gone on. This one is the only place the advice is acted on
 * while it can still change the outcome -- the purchase goes through PayPal
 * onto the winning card, and the row it creates is already scored when the
 * user gets back to Activity.
 *
 * The recommendation is shown before the payment, not after. A button that
 * said only "Pay" would be asking the user to trust the card choice sight
 * unseen, which is the opposite of what this app is for.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { recommend, type RecommendResponse } from '../api';
import { checkout, type Receipt } from '../pay';
import {
  MONO,
  UI,
  UI_BOLD,
  UI_SEMI,
  dark,
  money,
  light,
  radius,
  space,
  type,
  type Theme,
} from '../theme';

interface Props {
  onDone: (paid: boolean) => void;
}

export function Pay({ onDone }: Props) {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [merchant, setMerchant] = useState('');
  const [amount, setAmount] = useState('');
  const [rec, setRec] = useState<RecommendResponse | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const ready = merchant.trim().length > 0 && Number(amount) > 0;

  // Ask the engine as they type, so the card is on screen before they commit
  // rather than being revealed by the receipt.
  useEffect(() => {
    if (!ready || receipt) return;
    let cancelled = false;
    const timer = setTimeout(() => {
      recommend({ merchant: merchant.trim(), amount })
        .then((r) => !cancelled && setRec(r))
        .catch(() => !cancelled && setRec(null));
    }, 350);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [merchant, amount, ready, receipt]);

  const best = rec?.ranked?.[0] ?? null;

  const pay = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setReceipt(await checkout(merchant.trim(), amount));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [merchant, amount]);

  if (receipt) {
    const paid = receipt.status === 'COMPLETED';
    return (
      <SafeAreaView style={s.safe} edges={['left', 'right', 'bottom']}>
        <ScrollView contentContainerStyle={s.scroll}>
          <Text style={s.done}>
            {paid ? 'Paid' : receipt.status}
          </Text>
          <Text style={s.doneLine}>
            {money(amount)} at {merchant.trim()} on{' '}
            <Text style={s.doneStrong}>{receipt.charged_card.card_name}</Text>
          </Text>

          <View style={s.block}>
            <Row label="Earned" value={`${money(receipt.charged_card.net_value_dollars)}`} theme={theme} />
            <Row
              label="Better than"
              value={
                receipt.runner_up
                  ? `${receipt.runner_up} by ${money(receipt.advantage_dollars)}`
                  : 'no other eligible card'
              }
              theme={theme}
            />
            <Row label="PayPal order" value={receipt.order_id ?? '—'} theme={theme} mono />
            <Row label="Capture" value={receipt.capture_id ?? '—'} theme={theme} mono />
            {/* Said out loud because the alternative is implying the vaulted
                card was charged when a stand-in was. */}
            <Row
              label="Funded from"
              value={
                receipt.funding.funded_from_vault
                  ? `vaulted card ••${receipt.funding.last4 ?? '????'}`
                  : `stand-in card ••${receipt.funding.last4 ?? '????'}`
              }
              theme={theme}
            />
          </View>

          <Pressable
            accessibilityRole="button"
            onPress={() => onDone(true)}
            style={({ pressed }) => [s.cta, pressed && { opacity: 0.85 }]}
          >
            <Text style={s.ctaText}>See it in Activity</Text>
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.safe} edges={['left', 'right', 'bottom']}>
      <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">
        <Text style={s.lead}>
          Pointwise ranks your cards for this purchase, then pays with the one
          that earns most &mdash; through PayPal, on that card.
        </Text>

        <Text style={s.label}>Where</Text>
        <TextInput
          style={s.input}
          value={merchant}
          onChangeText={setMerchant}
          placeholder="Trader Joe&rsquo;s"
          placeholderTextColor={theme.inkFaint}
          autoCapitalize="words"
          accessibilityLabel="Merchant"
        />

        <Text style={s.label}>How much</Text>
        <TextInput
          style={[s.input, s.amount]}
          value={amount}
          onChangeText={setAmount}
          placeholder="0.00"
          placeholderTextColor={theme.inkFaint}
          keyboardType="decimal-pad"
          accessibilityLabel="Amount in dollars"
        />

        {ready && best && (
          <View style={s.pick}>
            <Text style={s.pickLabel}>Pointwise would use</Text>
            <Text style={s.pickCard}>{best.card_name}</Text>
            <Text style={s.pickWhy}>{rec?.explain}</Text>
          </View>
        )}

        {error && <Text style={s.error}>{error}</Text>}

        <Pressable
          accessibilityRole="button"
          disabled={!ready || busy}
          onPress={() => void pay()}
          style={({ pressed }) => [
            s.cta,
            (!ready || busy) && s.ctaOff,
            pressed && { opacity: 0.85 },
          ]}
        >
          {busy ? (
            <ActivityIndicator color={theme.accentInk} />
          ) : (
            <Text style={s.ctaText}>
              {best ? `Pay ${money(amount)} with ${best.card_name}` : 'Pay with PayPal'}
            </Text>
          )}
        </Pressable>

        <Text style={s.fine}>
          PayPal charges the card Pointwise picked. Put it on a different card
          and the gap is recorded as a miss rather than quietly forgiven.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({
  label,
  value,
  theme,
  mono,
}: {
  label: string;
  value: string;
  theme: Theme;
  mono?: boolean;
}) {
  const s = styles(theme);
  return (
    <View style={s.row}>
      <Text style={s.rowLabel}>{label}</Text>
      <Text style={[s.rowValue, mono && s.rowMono]} numberOfLines={1}>
        {value}
      </Text>
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1 },
    scroll: { padding: space.lg, gap: space.md, paddingBottom: space.xxxl },
    lead: { ...type.body, color: t.inkSoft },
    label: { ...type.label, color: t.inkFaint, marginTop: space.sm },
    input: {
      backgroundColor: t.sunk,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: radius.md,
      paddingHorizontal: space.md,
      paddingVertical: space.md,
      color: t.ink,
      fontFamily: UI,
      fontSize: 16,
    },
    amount: { fontFamily: MONO, fontSize: 20 },

    pick: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.accent,
      borderRadius: radius.md,
      padding: space.md,
      gap: 2,
    },
    pickLabel: { ...type.small, color: t.inkFaint },
    pickCard: { fontFamily: UI_BOLD, fontSize: 18, color: t.ink },
    pickWhy: { ...type.small, color: t.inkSoft, marginTop: 2 },

    cta: {
      backgroundColor: t.accent,
      borderRadius: radius.md,
      paddingVertical: space.lg,
      alignItems: 'center',
      marginTop: space.sm,
      minHeight: 52,
      justifyContent: 'center',
    },
    ctaOff: { backgroundColor: t.surfaceLift },
    ctaText: { fontFamily: UI_SEMI, color: t.accentInk, fontSize: 16 },
    fine: { ...type.small, lineHeight: 17, color: t.inkFaint },
    error: { ...type.small, color: t.stop },

    done: { ...type.hero, fontSize: 34, color: t.ink },
    doneLine: { ...type.body, color: t.inkSoft },
    doneStrong: { fontFamily: UI_BOLD, color: t.ink },
    block: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      borderRadius: radius.md,
      padding: space.md,
      gap: space.sm,
      marginTop: space.sm,
    },
    row: { flexDirection: 'row', justifyContent: 'space-between', gap: space.md },
    rowLabel: { ...type.small, color: t.inkFaint },
    rowValue: { ...type.small, color: t.ink, flexShrink: 1, textAlign: 'right' },
    rowMono: { fontFamily: MONO, fontSize: 11 },
  });
