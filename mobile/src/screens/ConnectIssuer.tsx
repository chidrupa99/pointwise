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
import * as WebBrowser from 'expo-web-browser';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  fetchPlaidStatus,
  linkSandboxIssuer,
  mapAccount,
  completeLink,
  startLink,
  syncIssuers,
  unlinkIssuer,
  type PlaidStatus,
} from '../plaid';
import { fetchCatalog, formatDate, type CatalogCard } from '../wallet';
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

  // Every bank, not the first one. A card lives at the bank that issued it,
  // so a wallet of four cards is usually several connections -- an Amex Gold
  // is at American Express and a Venture X at Capital One, and they can never
  // arrive on the same login.
  const links = status?.links ?? [];

  /**
   * Plaid's hosted Link page, opened in a web view.
   *
   * The browser hands back nothing on the way out -- a public token in a
   * redirect URL would be a credential in a URL -- so once the sheet closes
   * the server is asked what the session produced. Someone who backed out
   * without choosing a bank gets told that, not an error.
   */
  const connect = useCallback(async () => {
    setBusy('link');
    setError(null);
    setNote(null);
    try {
      const { link_token, hosted_link_url } = await startLink();
      if (!hosted_link_url) throw new Error('Plaid returned no Link URL.');
      await WebBrowser.openAuthSessionAsync(hosted_link_url);
      const done = await completeLink(link_token);
      if (done.linked) {
        setNote(
          'Connected. Tell us which card each account is and Pointwise will price your history.',
        );
        await refresh();
        onChanged();
      } else {
        setNote('Nothing was connected.');
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }, [refresh, onChanged]);

  return (
    <SafeAreaView style={s.safe} edges={['left', 'right', 'bottom']}>
      <ScrollView contentContainerStyle={s.scroll}>
        <Text style={s.lead}>
          However you paid &mdash; tapped, typed, or through PayPal &mdash;
          it lands on the card. Pointwise reads the card&rsquo;s own statement,
          so nothing you buy goes unscored.
        </Text>

        {!status && !error && (
          <ActivityIndicator style={s.spinner} color={theme.inkFaint} />
        )}

        {status && !status.configured && (
          <View style={s.notice}>
            <Text style={s.noticeTitle}>Connecting is unavailable</Text>
            <Text style={s.noticeBody}>
              Add your cards by hand for now — Pointwise can still rank them,
              it just will not see what you spend.
            </Text>
          </View>
        )}

        {status?.configured && (
          <>
            <Pressable
              accessibilityRole="button"
              disabled={busy !== null}
              onPress={() => void connect()}
              style={({ pressed }) => [
                s.cta,
                busy !== null && s.ctaOff,
                pressed && { opacity: 0.8 },
              ]}
            >
              <Text style={s.ctaText}>
                {busy === 'link'
                  ? 'Connecting…'
                  : links.length === 0
                    ? 'Connect your bank'
                    : 'Connect another bank'}
              </Text>
            </Pressable>
            {links.length === 0 && (
              <Text style={s.fine}>
                You sign in to your bank on their own screen. Pointwise never
                sees your banking password, and never asks for a card number.
              </Text>
            )}

            {/* The sign-in is a web view and five taps. That is the honest
                flow and it stays the button, but a presentation runs on
                someone else's wifi, so the direct path stays reachable. */}
            {status.sandbox_shortcut_available && (
              <Pressable
                accessibilityRole="button"
                disabled={busy !== null}
                onPress={() =>
                  run(
                    'link',
                    linkSandboxIssuer,
                    'Connected. Tell us which card each account is and Pointwise will price your history.',
                  )
                }
                hitSlop={6}
                style={({ pressed }) => [s.skip, pressed && { opacity: 0.6 }]}
              >
                <Text style={s.skipText}>Skip the sign-in (sandbox)</Text>
              </Pressable>
            )}
          </>
        )}

        {links.map((link) => (
          <View key={link.item_id} style={s.block}>
            <Text style={s.blockTitle}>{link.institution_name}</Text>
            <Text style={s.blockMeta}>
              Connected {formatDate(link.linked_at.slice(0, 10))} &middot;{' '}
              {link.transaction_count === 0
                ? 'no transactions yet'
                : `${link.transaction_count} transaction${
                    link.transaction_count === 1 ? '' : 's'
                  }`}
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

            {/* Per bank, because that is what a Plaid connection is: one
                bank login. There is no per-card revoke to offer -- removing a
                single card means telling us the account is not one of yours
                above, or dropping the card from your wallet. */}
            <Pressable
              accessibilityRole="button"
              disabled={busy !== null}
              onPress={() =>
                run(
                  'unlink',
                  () => unlinkIssuer(link.item_id),
                  `${link.institution_name} disconnected.`,
                )
              }
              style={({ pressed }) => [s.danger, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.dangerText}>Disconnect this bank</Text>
            </Pressable>
          </View>
        ))}

        {/* Connecting already pulled the statement. What is left here is a
            retry for the case where Plaid had nothing ready yet, which is why
            it is a quiet link and not the third step of a wizard. */}
        {status?.connected && (
          <>
            <View style={s.stats}>
              <View style={s.statRow}>
                <Text style={s.stat}>
                  {status.transactions_cached === 0
                    ? 'No transactions yet'
                    : `${status.transactions_cached} in total`}
                </Text>
                <Pressable
                  accessibilityRole="button"
                  disabled={busy !== null}
                  onPress={() => run('sync', syncIssuers)}
                  hitSlop={8}
                >
                  <Text style={[s.refresh, busy !== null && s.refreshOff]}>
                    {busy === 'sync' ? 'Checking…' : 'Check for new'}
                  </Text>
                </Pressable>
              </View>
              {status.unmapped_accounts > 0 && (
                <Text style={s.statWarn}>
                  {status.unmapped_accounts} account
                  {status.unmapped_accounts === 1 ? '' : 's'} still unmatched —
                  their purchases cannot be scored
                </Text>
              )}
            </View>
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
    statRow: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
    },
    refresh: { fontFamily: UI, fontSize: 12.5, color: t.accent },
    refreshOff: { color: t.inkFaint },
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


    cta: {
      backgroundColor: t.accent,
      borderRadius: radius.md,
      paddingVertical: space.md,
      alignItems: 'center',
    },
    ctaOff: { opacity: 0.45 },
    ctaText: { color: t.accentInk, fontFamily: UI, fontSize: 15.5, fontWeight: '600' },
    skip: { alignItems: 'center', paddingVertical: space.sm },
    skipText: { fontFamily: UI, fontSize: 12.5, color: t.inkFaint },
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
    blockMeta: { fontFamily: UI, fontSize: 12, color: t.inkFaint },

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
