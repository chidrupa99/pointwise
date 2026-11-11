/**
 * Connecting a card issuer, so the audit covers spending Pointwise did not route.
 *
 * The flow is three steps and the middle one is the only one that needs a
 * human: link, then say which card each account is, then pull transactions.
 * Plaid names an account "Platinum Card ••3210"; the corpus calls it
 * `amex-platinum`. Nothing guarantees those line up, so the match is always
 * shown for confirmation rather than applied silently -- a wrong mapping would
 * price every purchase on that card against the wrong rates.
 */

import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  fetchPlaidStatus,
  linkSandboxIssuer,
  mapAccount,
  syncIssuers,
  unlinkIssuer,
  type PlaidStatus,
} from '../plaid';
import { fetchCatalog, type CatalogCard } from '../wallet';
import { MONO, UI, dark, light, radius, space, type Theme } from '../theme';

interface Props {
  /** Called whenever the transaction set changed, so Home refetches. */
  onChanged: () => void;
}

export function ConnectIssuer({ onChanged }: Props) {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [status, setStatus] = useState<PlaidStatus | null>(null);
  const [catalog, setCatalog] = useState<CatalogCard[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [picking, setPicking] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [st, cat] = await Promise.all([fetchPlaidStatus(), fetchCatalog()]);
      setStatus(st);
      setCatalog(cat.cards);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const run = useCallback(
    async (label: string, fn: () => Promise<unknown>, after?: string) => {
      setBusy(label);
      setError(null);
      setNote(null);
      try {
        await fn();
        if (after) setNote(after);
        await refresh();
        onChanged();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(null);
      }
    },
    [refresh, onChanged],
  );

  const link = status?.links[0] ?? null;

  return (
    <SafeAreaView style={s.safe} edges={['left', 'right', 'bottom']}>
      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={s.lead}>
          Pointwise can only audit purchases it routed itself. Linking a card
          issuer lets it read the card&rsquo;s own statement, so spending made
          any way at all gets scored.
        </Text>

        {!status && !error && (
          <ActivityIndicator style={s.spinner} color={theme.inkFaint} />
        )}

        {status && !status.configured && (
          <View style={s.notice}>
            <Text style={s.noticeTitle}>Plaid is not configured</Text>
            <Text style={s.noticeBody}>{status.hint}</Text>
          </View>
        )}

        {status?.configured && (
          <View style={s.envRow}>
            <Text style={s.envLabel}>environment</Text>
            <Text style={s.envValue}>{status.environment}</Text>
          </View>
        )}

        {/* Step 1 — link */}
        {status?.configured && !status.connected && (
          <>
            <Pressable
              accessibilityRole="button"
              disabled={busy !== null || !status.sandbox_shortcut_available}
              onPress={() =>
                run('link', linkSandboxIssuer, 'Linked. Now pull transactions.')
              }
              style={({ pressed }) => [
                s.cta,
                (busy !== null || !status.sandbox_shortcut_available) && s.ctaOff,
                pressed && { opacity: 0.8 },
              ]}
            >
              <Text style={s.ctaText}>
                {busy === 'link' ? 'Linking…' : 'Connect the sandbox bank'}
              </Text>
            </Pressable>
            <Text style={s.fine}>
              Plaid&rsquo;s test institution. No real bank, no login, no money
              — it arrives with credit card accounts and a month of
              transactions already attached.
            </Text>
          </>
        )}

        {/* Step 2 — say which card each account is */}
        {link && (
          <View style={s.block}>
            <Text style={s.blockTitle}>{link.institution_name}</Text>
            <Text style={s.blockMeta}>
              Linked {link.linked_at.replace('T', ' ')} · credential held
              server-side ({link.access_token_length} chars)
            </Text>

            {link.accounts.length === 0 && (
              <Text style={s.fine}>
                No credit card accounts on this item. Only cards can be scored.
              </Text>
            )}

            {link.accounts.map((account) => {
              const card = catalog.find((c) => c.card_id === account.card_id);
              const open = picking === account.account_id;
              return (
                <View key={account.account_id} style={s.account}>
                  <Text style={s.accountLabel}>{account.label}</Text>
                  <Pressable
                    accessibilityRole="button"
                    onPress={() => setPicking(open ? null : account.account_id)}
                    style={({ pressed }) => [
                      s.mapRow,
                      pressed && { opacity: 0.6 },
                    ]}
                  >
                    <Text
                      style={[s.mapValue, !card && s.mapUnset]}
                      numberOfLines={1}
                    >
                      {card ? card.name : 'Not matched — tap to choose'}
                    </Text>
                    <Text style={s.chev}>{open ? '▴' : '▾'}</Text>
                  </Pressable>

                  {open && (
                    <View style={s.options}>
                      {catalog.map((c) => (
                        <Pressable
                          key={c.card_id}
                          accessibilityRole="button"
                          onPress={() => {
                            setPicking(null);
                            void run('map', () =>
                              mapAccount(link.item_id, account.account_id, c.card_id),
                            );
                          }}
                          style={({ pressed }) => [
                            s.option,
                            c.card_id === account.card_id && s.optionOn,
                            pressed && { opacity: 0.6 },
                          ]}
                        >
                          <Text style={s.optionText}>{c.name}</Text>
                        </Pressable>
                      ))}
                      <Pressable
                        accessibilityRole="button"
                        onPress={() => {
                          setPicking(null);
                          void run('map', () =>
                            mapAccount(link.item_id, account.account_id, null),
                          );
                        }}
                        style={({ pressed }) => [s.option, pressed && { opacity: 0.6 }]}
                      >
                        <Text style={[s.optionText, s.optionClear]}>
                          Not one of my cards
                        </Text>
                      </Pressable>
                    </View>
                  )}
                </View>
              );
            })}
          </View>
        )}

        {/* Step 3 — pull */}
        {status?.connected && (
          <>
            <Pressable
              accessibilityRole="button"
              disabled={busy !== null}
              onPress={() => run('sync', syncIssuers, 'Transactions pulled.')}
              style={({ pressed }) => [
                s.cta,
                busy !== null && s.ctaOff,
                pressed && { opacity: 0.8 },
              ]}
            >
              <Text style={s.ctaText}>
                {busy === 'sync' ? 'Pulling…' : 'Pull transactions'}
              </Text>
            </Pressable>

            <View style={s.stats}>
              <Text style={s.stat}>
                {status.transactions_cached} transactions held
              </Text>
              {status.unmapped_accounts > 0 && (
                <Text style={s.statWarn}>
                  {status.unmapped_accounts} account
                  {status.unmapped_accounts === 1 ? '' : 's'} still unmatched —
                  their purchases cannot be scored
                </Text>
              )}
            </View>

            <Pressable
              accessibilityRole="button"
              disabled={busy !== null}
              onPress={() =>
                run('unlink', () => unlinkIssuer(link!.item_id), 'Issuer forgotten.')
              }
              style={({ pressed }) => [s.danger, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.dangerText}>Disconnect and forget this issuer</Text>
            </Pressable>
          </>
        )}

        {note && <Text style={s.note}>{note}</Text>}
        {error && <Text style={s.error}>{error}</Text>}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1 },
    scroll: { padding: space.lg, paddingBottom: space.xxxl, gap: space.md },
    lead: { fontFamily: UI, fontSize: 14.5, lineHeight: 21, color: t.inkSoft },
    spinner: { marginTop: space.xl },

    notice: {
      backgroundColor: t.warnSoft,
      borderRadius: radius.md,
      borderLeftWidth: 3,
      borderLeftColor: t.warn,
      padding: space.md,
      gap: space.xs,
    },
    noticeTitle: { fontFamily: UI, fontSize: 14, fontWeight: '700', color: t.warn },
    noticeBody: { fontFamily: UI, fontSize: 13, lineHeight: 19, color: t.inkSoft },

    envRow: { flexDirection: 'row', justifyContent: 'space-between' },
    envLabel: { fontFamily: MONO, fontSize: 11, color: t.inkFaint },
    envValue: { fontFamily: MONO, fontSize: 11, color: t.ink },

    cta: {
      backgroundColor: t.accent,
      borderRadius: radius.md,
      paddingVertical: space.md,
      alignItems: 'center',
    },
    ctaOff: { opacity: 0.45 },
    ctaText: { color: t.accentInk, fontFamily: UI, fontSize: 15.5, fontWeight: '600' },
    fine: { fontFamily: UI, fontSize: 12, lineHeight: 18, color: t.inkFaint },

    block: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.ruleSoft,
      borderRadius: radius.md,
      padding: space.md,
      gap: space.sm,
    },
    blockTitle: { fontFamily: UI, fontSize: 16, fontWeight: '700', color: t.ink },
    blockMeta: { fontFamily: MONO, fontSize: 11, color: t.inkFaint },

    account: { gap: space.xs, borderTopWidth: 1, borderTopColor: t.ruleSoft, paddingTop: space.sm },
    accountLabel: { fontFamily: UI, fontSize: 14, color: t.ink, fontWeight: '600' },
    mapRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      backgroundColor: t.sunk,
      borderRadius: radius.sm,
      paddingHorizontal: space.md,
      paddingVertical: space.sm,
    },
    mapValue: { fontFamily: UI, fontSize: 14, color: t.ink, flex: 1 },
    mapUnset: { color: t.warn, fontWeight: '600' },
    chev: { color: t.inkFaint, fontFamily: UI, fontSize: 13, marginLeft: space.sm },

    options: { gap: space.xs },
    option: { paddingVertical: space.sm, paddingHorizontal: space.md, borderRadius: radius.sm },
    optionOn: { backgroundColor: t.accentSoft },
    optionText: { fontFamily: UI, fontSize: 14, color: t.ink },
    optionClear: { color: t.inkFaint },

    stats: { gap: space.xs },
    stat: { fontFamily: MONO, fontSize: 12, color: t.inkSoft },
    statWarn: { fontFamily: UI, fontSize: 12.5, lineHeight: 18, color: t.warn },

    danger: { alignItems: 'center', paddingVertical: space.md },
    dangerText: { color: t.stop, fontFamily: UI, fontSize: 14 },

    note: { fontFamily: UI, fontSize: 13, color: t.ok, fontWeight: '600' },
    error: { fontFamily: UI, fontSize: 13, color: t.stop },
  });
