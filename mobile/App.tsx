import {
  Manrope_500Medium,
  Manrope_600SemiBold,
  Manrope_700Bold,
  Manrope_800ExtraBold,
} from '@expo-google-fonts/manrope';
import {
  JetBrainsMono_400Regular,
  JetBrainsMono_500Medium,
} from '@expo-google-fonts/jetbrains-mono';
import { useFonts } from 'expo-font';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useEffect, useState } from 'react';
import {
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
  useColorScheme,
} from 'react-native';
import { SafeAreaProvider, SafeAreaView } from 'react-native-safe-area-context';

import { AddCard } from './src/screens/AddCard';
import { Chat } from './src/screens/Chat';
import { ConnectIssuer } from './src/screens/ConnectIssuer';
import { SignIn } from './src/screens/SignIn';
import { Home } from './src/screens/Home';
import { fetchAuthStatus, signOut, type AuthStatus } from './src/auth';
import { dark, light, type Theme } from './src/theme';

type Sheet = null | 'ask' | 'account' | 'addCard' | 'issuer';

export default function App() {
  const scheme = useColorScheme();
  const theme: Theme = scheme === 'light' ? light : dark;
  // Every face is named explicitly rather than leaning on fontWeight:
  // React Native will not synthesise a bold for a custom static font, so
  // a style asking for '700' on Manrope silently renders as Medium.
  const [fontsReady] = useFonts({
    Manrope_500Medium,
    Manrope_600SemiBold,
    Manrope_700Bold,
    Manrope_800ExtraBold,
    JetBrainsMono_400Regular,
    JetBrainsMono_500Medium,
  });
  const [sheet, setSheet] = useState<Sheet>(null);
  //: Bumped whenever the wallet changes, so Home refetches instead of showing
  //: a stale card rail behind the sheet that just changed it.
  const [walletVersion, setWalletVersion] = useState(0);
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const s = styles(theme);

  const refreshAuth = useCallback(() => {
    fetchAuthStatus()
      .then(setAuth)
      // A server that cannot be reached must not strand the user on a blank
      // screen. Treat it as signed out: the sign-in screen reports the error
      // itself and is the one place a retry makes sense.
      .catch(() => setAuth({
        signed_in: false,
        profile: null,
        paypal_login_available: false,
        paypal_login_hint: null,
      }));
  }, []);

  useEffect(refreshAuth, [refreshAuth]);

  return (
    <SafeAreaProvider>
      <StatusBar style={scheme === 'light' ? 'dark' : 'light'} />

      {/* Holding the ground colour until the faces land avoids a flash of
          system type reflowing into Manrope on the first screen. */}
      {auth === null || !fontsReady ? (
        <View style={s.boot} />
      ) : !auth.signed_in ? (
        <SignIn onSignedIn={refreshAuth} />
      ) : (
      <Home
        onOpenChat={() => setSheet('ask')}
        onOpenAccount={() => setSheet('account')}
        onAddCard={() => setSheet('addCard')}
        reloadKey={walletVersion}
      />
      )}

      <Modal
        visible={sheet === 'addCard'}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setSheet(null)}
      >
        <AddCard
          onDone={(added) => {
            if (added) setWalletVersion((v) => v + 1);
            setSheet(null);
          }}
        />
      </Modal>

      <Modal
        visible={sheet === 'ask' || sheet === 'account' || sheet === 'issuer'}
        animationType="slide"
        presentationStyle="pageSheet"
        onRequestClose={() => setSheet(null)}
      >
        <View style={s.sheet}>
          <View style={s.sheetBar}>
            <Text style={s.sheetTitle}>
              {sheet === 'ask'
                ? 'Ask Pointwise'
                : sheet === 'issuer'
                  ? 'Connect a card issuer'
                  : 'Account'}
            </Text>
            <Pressable
              accessibilityRole="button"
              accessibilityLabel="Close"
              onPress={() => setSheet(null)}
              style={({ pressed }) => [s.close, pressed && { opacity: 0.6 }]}
            >
              <Text style={s.closeText}>Done</Text>
            </Pressable>
          </View>
          {sheet === 'ask' ? (
            <Chat />
          ) : sheet === 'issuer' ? (
            <ConnectIssuer onChanged={() => setWalletVersion((v) => v + 1)} />
          ) : (
            <AccountSheet
              theme={theme}
              auth={auth}
              onSignOut={async () => {
                await signOut();
                setSheet(null);
                refreshAuth();
              }}
              onConnectIssuer={() => setSheet('issuer')}
            />
          )}
        </View>
      </Modal>
    </SafeAreaProvider>
  );
}

/** Account menu. Most rows are still placeholders; sign-out is real. */
function AccountSheet({
  theme,
  auth,
  onSignOut,
  onConnectIssuer,
}: {
  theme: Theme;
  auth: AuthStatus | null;
  onSignOut: () => void;
  onConnectIssuer: () => void;
}) {
  const s = styles(theme);
  return (
    <SafeAreaView style={s.account} edges={['left', 'right']}>
      {auth?.profile && (
        <View style={s.who}>
          <Text style={s.whoName}>{auth.profile.name}</Text>
          <Text style={s.whoMeta}>
            {auth.profile.verified
              ? `Signed in with PayPal${auth.profile.email ? ` · ${auth.profile.email}` : ''}`
              : 'Name only — not verified by PayPal'}
          </Text>
        </View>
      )}
      <Text style={s.accountNote}>
        More settings are on the way.
      </Text>
      <View style={s.accountList}>
        <Pressable
          accessibilityRole="button"
          onPress={onConnectIssuer}
          style={({ pressed }) => [s.accountRow, pressed && { opacity: 0.6 }]}
        >
          <Text style={s.accountRowText}>Connect a card issuer</Text>
          <Text style={s.accountRowGo}>›</Text>
        </Pressable>
        {['Notifications', 'Privacy'].map((row) => (
          <View key={row} style={s.accountRow}>
            <Text style={s.accountRowText}>{row}</Text>
            <Text style={s.accountRowHint}>soon</Text>
          </View>
        ))}
      </View>
      <Pressable
        accessibilityRole="button"
        onPress={onSignOut}
        style={({ pressed }) => [s.signOut, pressed && { opacity: 0.6 }]}
      >
        <Text style={s.signOutText}>Sign out</Text>
      </Pressable>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    sheet: { flex: 1, backgroundColor: t.ground },
    sheetBar: {
      flexDirection: 'row',
      alignItems: 'center',
      justifyContent: 'space-between',
      paddingHorizontal: 16,
      paddingTop: 16,
      paddingBottom: 10,
      borderBottomWidth: 1,
      borderBottomColor: t.rule,
    },
    sheetTitle: { fontSize: 17, fontWeight: '700', color: t.ink },
    close: { paddingHorizontal: 6, paddingVertical: 4 },
    closeText: { color: t.accent, fontSize: 15, fontWeight: '600' },

    account: { flex: 1, padding: 16 },
    accountNote: { color: t.inkSoft, fontSize: 13.5, lineHeight: 19, marginBottom: 18 },
    accountList: { gap: 8 },
    accountRow: {
      flexDirection: 'row',
      justifyContent: 'space-between',
      alignItems: 'center',
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 9,
      padding: 14,
    },
    accountRowText: { color: t.ink, fontSize: 14.5 },
    accountRowHint: { color: t.inkFaint, fontSize: 12 },
    accountRowGo: { color: t.accent, fontSize: 18, fontWeight: '600' },

    boot: { flex: 1, backgroundColor: t.ground },
    who: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 11,
      padding: 14,
      marginBottom: 14,
      gap: 3,
    },
    whoName: { color: t.ink, fontSize: 17, fontWeight: '700' },
    whoMeta: { color: t.inkFaint, fontSize: 12.5 },
    signOut: { marginTop: 18, alignItems: 'center', paddingVertical: 12 },
    signOutText: { color: t.stop, fontSize: 15, fontWeight: '600' },
  });
