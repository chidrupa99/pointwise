/** The pre-tap screen: say where you are, see which card to use. */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { CardRow } from '../components/CardRow';
import { fetchAudit, recommend, type RecommendResponse } from '../api';
import { MONO, dark, light, money, type Theme } from '../theme';

/** Merchants whose category routinely surprises people. */
const EXAMPLES: ReadonlyArray<readonly [string, string, string]> = [
  ["Trader Joe's", '120', 'a real supermarket'],
  ['Walmart', '120', 'codes as a discount store'],
  ['Costco', '240', 'wholesale club'],
  ['Starbucks', '8', 'fast food'],
  ['Amazon', '95', 'direct marketing'],
  ['United Airlines', '1200', 'airfare'],
];

const PORTALS = ['Apple Pay', 'Chase Travel', 'Capital One Travel', 'Amex Travel'] as const;

/** The $5,800 preset crosses Blue Cash Preferred's $6,000 grocery cap. */
const SPEND_PRESETS = ['0', '3000', '5800'] as const;

const ROTATING = ['flex-rotating-q4-grocery', 'discover-rotating-q4'];

export function WhichCard() {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [merchant, setMerchant] = useState("Trader Joe's");
  const [amount, setAmount] = useState('120');
  const [portal, setPortal] = useState<string | null>(null);
  const [foreign, setForeign] = useState(false);
  const [spend, setSpend] = useState<string>('0');
  const [activated, setActivated] = useState(true);

  const [result, setResult] = useState<RecommendResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [audit, setAudit] = useState<string>('');

  const run = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(
        await recommend({
          merchant,
          amount: amount || '1',
          portal,
          is_foreign: foreign,
          category_spend_to_date: spend,
          activated_rule_ids: activated ? ROTATING : [],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not reach the engine');
      setResult(null);
    } finally {
      setBusy(false);
    }
  }, [merchant, amount, portal, foreign, spend, activated]);

  useEffect(() => {
    void run();
  }, [portal, foreign, spend, activated]);

  useEffect(() => {
    fetchAudit()
      .then((a) => setAudit(a.summary))
      .catch(() => setAudit(''));
  }, []);

  const best = result?.ranked[0];
  const runnerUp = result?.ranked[1];

  return (
    <SafeAreaView style={s.safe} edges={['top', 'left', 'right']}>
      <KeyboardAvoidingView
        style={s.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={s.scroll}
          keyboardShouldPersistTaps="handled"
          keyboardDismissMode="on-drag"
        >
          <View style={s.header}>
            <Text style={s.h1}>Pointwise</Text>
            <Text style={s.tagline}>which card, and why</Text>
          </View>

          <View style={s.panel}>
            <Text style={s.label}>Merchant</Text>
            <View style={s.row}>
              <TextInput
                style={[s.input, s.flex]}
                value={merchant}
                onChangeText={setMerchant}
                onSubmitEditing={run}
                returnKeyType="search"
                placeholder="e.g. Trader Joe's"
                placeholderTextColor={theme.inkFaint}
                accessibilityLabel="Merchant name"
              />
              <TextInput
                style={[s.input, s.amount]}
                value={amount}
                onChangeText={setAmount}
                onSubmitEditing={run}
                keyboardType="decimal-pad"
                returnKeyType="done"
                accessibilityLabel="Amount in dollars"
              />
            </View>

            <Text style={[s.label, s.spaced]}>Try a tricky one</Text>
            <View style={s.chips}>
              {EXAMPLES.map(([name, amt, note]) => (
                <Pressable
                  key={name}
                  accessibilityRole="button"
                  accessibilityLabel={`${name} — ${note}`}
                  onPress={() => {
                    setMerchant(name);
                    setAmount(amt);
                  }}
                  style={({ pressed }) => [
                    s.chip,
                    merchant === name && s.chipOn,
                    pressed && { opacity: 0.6 },
                  ]}
                >
                  <Text style={[s.chipText, merchant === name && s.chipTextOn]}>{name}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={[s.label, s.spaced]}>Paid through</Text>
            <View style={s.chips}>
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Paid directly, no portal"
                onPress={() => setPortal(null)}
                style={({ pressed }) => [s.chip, portal === null && s.chipOn, pressed && { opacity: 0.6 }]}
              >
                <Text style={[s.chipText, portal === null && s.chipTextOn]}>Directly</Text>
              </Pressable>
              {PORTALS.map((p) => (
                <Pressable
                  key={p}
                  accessibilityRole="button"
                  accessibilityLabel={`Paid through ${p}`}
                  onPress={() => setPortal(p)}
                  style={({ pressed }) => [s.chip, portal === p && s.chipOn, pressed && { opacity: 0.6 }]}
                >
                  <Text style={[s.chipText, portal === p && s.chipTextOn]}>{p}</Text>
                </Pressable>
              ))}
            </View>

            <Text style={[s.label, s.spaced]}>Already spent in this category</Text>
            <View style={s.chips}>
              {SPEND_PRESETS.map((v) => (
                <Pressable
                  key={v}
                  accessibilityRole="button"
                  accessibilityLabel={`Already spent ${money(v)} in this category`}
                  onPress={() => setSpend(v)}
                  style={({ pressed }) => [s.chip, spend === v && s.chipOn, pressed && { opacity: 0.6 }]}
                >
                  <Text style={[s.chipText, spend === v && s.chipTextOn]}>
                    ${Number(v).toLocaleString('en-US')}
                  </Text>
                </Pressable>
              ))}
            </View>

            <View style={[s.chips, s.spaced]}>
              <Pressable
                accessibilityRole="switch"
                accessibilityState={{ checked: foreign }}
                accessibilityLabel="Foreign transaction"
                onPress={() => setForeign((v) => !v)}
                style={({ pressed }) => [s.chip, foreign && s.chipOn, pressed && { opacity: 0.6 }]}
              >
                <Text style={[s.chipText, foreign && s.chipTextOn]}>Foreign transaction</Text>
              </Pressable>
              <Pressable
                accessibilityRole="switch"
                accessibilityState={{ checked: activated }}
                accessibilityLabel="Rotating categories activated"
                onPress={() => setActivated((v) => !v)}
                style={({ pressed }) => [s.chip, activated && s.chipOn, pressed && { opacity: 0.6 }]}
              >
                <Text style={[s.chipText, activated && s.chipTextOn]}>Rotating activated</Text>
              </Pressable>
            </View>

            <Pressable
              accessibilityRole="button"
              onPress={run}
              disabled={busy}
              style={({ pressed }) => [s.go, (pressed || busy) && { opacity: 0.7 }]}
            >
              {busy ? (
                <ActivityIndicator color={theme.accentInk} />
              ) : (
                <Text style={s.goText}>Which card?</Text>
              )}
            </Pressable>
          </View>

          {error && (
            <View style={s.errorBox}>
              <Text style={s.errorText}>
                {error}. Start the engine with{'\n'}
                <Text style={s.code}>uvicorn pointwise.api:app --port 8077</Text>
              </Text>
            </View>
          )}

          {result && (
            <>
              <View style={s.resolve}>
                <Text style={s.resolveText}>resolved to </Text>
                <View style={[s.pill, !result.resolved && s.pillWarn]}>
                  <Text style={[s.pillText, !result.resolved && s.pillTextWarn]}>
                    {result.category}
                  </Text>
                </View>
                <Text style={s.resolveText}> via {result.provenance}</Text>
              </View>
              {!result.resolved && (
                <Text style={s.resolveNote}>
                  Unknown merchant, so this is a floor rather than a prediction.
                </Text>
              )}

              {best && (
                <View style={s.winner}>
                  <Text style={s.winnerEyebrow}>USE THIS ONE</Text>
                  <Text style={s.winnerName}>{best.card_name}</Text>
                  <Text style={s.winnerIssuer}>{best.issuer}</Text>
                  <Text style={s.winnerAmount}>{money(best.net_value_dollars)}</Text>
                  <Text style={s.winnerGap}>
                    {best.effective_rate_percent}% effective
                    {runnerUp && Number(result.advantage_dollars) > 0 && (
                      <>
                        {' · '}
                        <Text style={s.winnerGapStrong}>
                          {money(result.advantage_dollars)} better
                        </Text>
                        {` than ${runnerUp.card_name}`}
                      </>
                    )}
                  </Text>
                </View>
              )}

              <View style={s.list}>
                {result.ranked.map((ev, i) => (
                  <CardRow
                    key={ev.card_id}
                    evaluation={ev}
                    rank={i + 1}
                    theme={theme}
                    startExpanded={i === 0}
                  />
                ))}
              </View>

              {result.excluded.length > 0 && (
                <View style={s.list}>
                  <Text style={[s.label, s.spaced]}>Excluded</Text>
                  {result.excluded.map((ev) => (
                    <View key={ev.card_id} style={s.excluded}>
                      <Text style={s.excludedText}>
                        {ev.card_name}: {ev.disqualified_reason}
                      </Text>
                    </View>
                  ))}
                </View>
              )}
            </>
          )}

          <View style={s.notice}>
            <Text style={s.noticeText}>
              <Text style={s.noticeStrong}>Unverified data. </Text>
              Every rule ships verified_by_human: false. These rates must be checked
              against each issuer's current cardmember agreement before any of these
              figures reaches a real user.
            </Text>
          </View>
          {audit !== '' && <Text style={s.audit}>{audit}</Text>}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1, backgroundColor: t.ground },
    flex: { flex: 1 },
    scroll: { padding: 16, paddingBottom: 56 },

    header: { marginBottom: 18 },
    h1: { fontSize: 26, fontWeight: '700', color: t.ink, letterSpacing: -0.5 },
    tagline: { fontFamily: MONO, fontSize: 11, color: t.inkFaint, marginTop: 2 },

    panel: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 12,
      padding: 16,
      marginBottom: 16,
    },
    label: {
      fontSize: 10.5,
      fontWeight: '600',
      letterSpacing: 1.1,
      textTransform: 'uppercase',
      color: t.inkFaint,
      marginBottom: 7,
    },
    spaced: { marginTop: 14 },
    row: { flexDirection: 'row', gap: 10 },
    input: {
      backgroundColor: t.ground,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 8,
      paddingHorizontal: 12,
      paddingVertical: 11,
      fontSize: 15,
      color: t.ink,
    },
    amount: { width: 96, fontFamily: MONO },

    chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6 },
    chip: {
      backgroundColor: t.sunk,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 999,
      paddingHorizontal: 11,
      paddingVertical: 6,
    },
    chipOn: { backgroundColor: t.accentSoft, borderColor: t.accent },
    chipText: { fontSize: 12.5, color: t.inkSoft },
    chipTextOn: { color: t.accent, fontWeight: '600' },

    go: {
      backgroundColor: t.accent,
      borderRadius: 8,
      paddingVertical: 13,
      alignItems: 'center',
      marginTop: 16,
    },
    goText: { color: t.accentInk, fontSize: 15, fontWeight: '600' },

    errorBox: {
      backgroundColor: t.stopSoft,
      borderWidth: 1,
      borderColor: t.stop,
      borderRadius: 9,
      padding: 13,
      marginBottom: 14,
    },
    errorText: { color: t.ink, fontSize: 13, lineHeight: 19 },
    code: { fontFamily: MONO, fontSize: 11.5, color: t.stop },

    resolve: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', marginBottom: 12 },
    resolveText: { fontSize: 12.5, color: t.inkSoft },
    resolveNote: { fontSize: 12.5, color: t.warn, marginBottom: 12, marginTop: -6 },
    pill: { backgroundColor: t.accentSoft, borderRadius: 5, paddingHorizontal: 8, paddingVertical: 3 },
    pillWarn: { backgroundColor: t.warnSoft },
    pillText: { fontFamily: MONO, fontSize: 11.5, color: t.accent },
    pillTextWarn: { color: t.warn },

    winner: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderLeftWidth: 3,
      borderLeftColor: t.ok,
      borderRadius: 12,
      padding: 18,
      marginBottom: 12,
    },
    winnerEyebrow: {
      fontSize: 10,
      fontWeight: '700',
      letterSpacing: 1.3,
      color: t.ok,
      marginBottom: 7,
    },
    winnerName: { fontSize: 22, fontWeight: '700', color: t.ink, letterSpacing: -0.4 },
    winnerIssuer: { fontSize: 12.5, color: t.inkFaint, marginTop: 1 },
    winnerAmount: {
      fontFamily: MONO,
      fontSize: 38,
      color: t.ink,
      marginTop: 10,
      letterSpacing: -1,
    },
    winnerGap: { fontSize: 13, color: t.inkSoft, marginTop: 3, lineHeight: 18 },
    winnerGapStrong: { color: t.ok, fontWeight: '700' },

    list: { gap: 8, marginTop: 4 },
    excluded: {
      backgroundColor: t.stopSoft,
      borderRadius: 8,
      padding: 11,
    },
    excludedText: { color: t.stop, fontSize: 12.5 },

    notice: {
      marginTop: 24,
      backgroundColor: t.stopSoft,
      borderWidth: 1,
      borderColor: t.stop,
      borderRadius: 9,
      padding: 14,
    },
    noticeText: { fontSize: 12.5, lineHeight: 18, color: t.ink },
    noticeStrong: { color: t.stop, fontWeight: '700' },
    audit: {
      fontFamily: MONO,
      fontSize: 10.5,
      color: t.inkFaint,
      textAlign: 'center',
      marginTop: 12,
    },
  });
