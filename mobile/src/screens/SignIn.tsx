/**
 * The front door.
 *
 * "Log In with PayPal" is the real path and the right one for this app -- the
 * whole product runs on PayPal's rails. It needs a return URL registered in
 * PayPal's dashboard, which cannot be set from code, so when it is unavailable
 * this screen says so plainly and offers to continue without it.
 *
 * The fallback is honest about what it is. It takes a name so the app has
 * someone to address; it verifies nothing and protects nothing, and the screen
 * says that rather than dressing a text field up as authentication.
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
import * as WebBrowser from 'expo-web-browser';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  fetchAuthStatus,
  localSignIn,
  startPayPalLogin,
  type AuthStatus,
} from '../auth';
import { dark, light, type Theme } from '../theme';

interface Props {
  onSignedIn: () => void;
}

export function SignIn({ onSignedIn }: Props) {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showFallback, setShowFallback] = useState(false);

  useEffect(() => {
    fetchAuthStatus()
      .then((st) => {
        setStatus(st);
        // Without PayPal login there is nothing to hide behind a second tap.
        if (!st.paypal_login_available) setShowFallback(true);
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)));
  }, []);

  const withPayPal = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const { url } = await startPayPalLogin();
      // The callback is handled by our own server, so we only need the browser
      // to come back -- there is nothing to parse out of the result here.
      await WebBrowser.openAuthSessionAsync(url);
      const after = await fetchAuthStatus();
      if (after.signed_in) {
        onSignedIn();
        return;
      }
      setError('Sign-in was not completed.');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [onSignedIn]);

  const withName = useCallback(async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setBusy(true);
    setError(null);
    try {
      await localSignIn(trimmed);
      onSignedIn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }, [name, onSignedIn]);

  return (
    <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.brand}>
          <View style={s.mark}>
            <Text style={s.markText}>P</Text>
          </View>
          <Text style={s.title}>Pointwise</Text>
          <Text style={s.tagline}>
            Tells you which of your cards earns most, before you pay.
            Every figure from a rules engine, never a guess.
          </Text>
        </View>

        {!status && !error && (
          <ActivityIndicator style={s.spinner} color={theme.inkFaint} />
        )}

        {status?.paypal_login_available && (
          <Pressable
            accessibilityRole="button"
            disabled={busy}
            onPress={() => void withPayPal()}
            style={({ pressed }) => [s.paypal, pressed && { opacity: 0.85 }]}
          >
            <Text style={s.paypalText}>Continue with PayPal</Text>
          </Pressable>
        )}

        {/* No banner when PayPal sign-in is unconfigured. The hint behind it
            names an env var and a dashboard setting -- it is addressed to
            whoever is building this, not to the person holding the phone, and
            nothing is broken from their side: the name fallback below opens
            automatically and signs them in. `paypal_login_hint` is still on
            /api/auth/status, which is where a developer should read it. */}

        {showFallback && (
          <View style={s.fallback}>
            <Text style={s.label}>What should the app call you?</Text>
            <TextInput
              style={s.input}
              value={name}
              onChangeText={setName}
              placeholder="Your name"
              placeholderTextColor={theme.inkFaint}
              autoCapitalize="words"
              returnKeyType="go"
              onSubmitEditing={() => void withName()}
              accessibilityLabel="Your name"
            />
            <Pressable
              accessibilityRole="button"
              disabled={busy || !name.trim()}
              onPress={() => void withName()}
              style={({ pressed }) => [
                s.go,
                (!name.trim() || busy) && s.goOff,
                pressed && { opacity: 0.8 },
              ]}
            >
              <Text style={s.goText}>Continue</Text>
            </Pressable>
            <Text style={s.honest}>
              This is a name, not an account. Nothing is verified and nothing is
              protected by it — it is here so the app has someone to address.
            </Text>
          </View>
        )}

        {status?.paypal_login_available && !showFallback && (
          <Pressable
            accessibilityRole="button"
            onPress={() => setShowFallback(true)}
            style={({ pressed }) => [s.alt, pressed && { opacity: 0.6 }]}
          >
            <Text style={s.altText}>Continue without PayPal</Text>
          </Pressable>
        )}

        {busy && <ActivityIndicator color={theme.inkFaint} />}
        {error && <Text style={s.error}>{error}</Text>}

        <Text style={s.foot}>
          Sandbox only. No real money moves, no card details are stored on
          this device, and nothing is connected to your bank.
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1, backgroundColor: t.ground },
    scroll: { padding: 24, paddingTop: 56, gap: 16, flexGrow: 1 },
    brand: { alignItems: 'center', gap: 10, marginBottom: 16 },
    mark: {
      width: 56,
      height: 56,
      borderRadius: 14,
      backgroundColor: t.accent,
      alignItems: 'center',
      justifyContent: 'center',
    },
    markText: { color: t.accentInk, fontSize: 28, fontWeight: '700' },
    title: { fontSize: 28, fontWeight: '700', color: t.ink },
    tagline: {
      fontSize: 15,
      lineHeight: 22,
      color: t.inkSoft,
      textAlign: 'center',
      maxWidth: 300,
    },
    spinner: { marginTop: 24 },

    paypal: {
      backgroundColor: '#003087',
      borderRadius: 12,
      paddingVertical: 16,
      alignItems: 'center',
    },
    paypalText: { color: '#fff', fontSize: 16, fontWeight: '700' },

    fallback: { gap: 10 },
    label: { fontSize: 14, color: t.inkSoft, fontWeight: '600' },
    input: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 11,
      paddingHorizontal: 14,
      paddingVertical: 14,
      fontSize: 16,
      color: t.ink,
    },
    go: {
      backgroundColor: t.accent,
      borderRadius: 12,
      paddingVertical: 15,
      alignItems: 'center',
    },
    goOff: { opacity: 0.4 },
    goText: { color: t.accentInk, fontSize: 16, fontWeight: '600' },
    honest: { fontSize: 12, lineHeight: 18, color: t.inkFaint },

    alt: { alignItems: 'center', paddingVertical: 12 },
    altText: { color: t.accent, fontSize: 15 },

    error: { fontSize: 13, color: t.stop },
    foot: {
      fontSize: 12,
      lineHeight: 18,
      color: t.inkFaint,
      textAlign: 'center',
      marginTop: 'auto',
    },
  });
