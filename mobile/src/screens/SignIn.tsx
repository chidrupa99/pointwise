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
import { LinearGradient } from 'expo-linear-gradient';
import * as WebBrowser from 'expo-web-browser';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  fetchAuthStatus,
  localSignIn,
  startPayPalLogin,
  type AuthStatus,
} from '../auth';
import { Brand } from '../components/Brand';
import { UI, dark, light, radius, space, type, type Theme } from '../theme';

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
    <View style={{ flex: 1, backgroundColor: theme.ground }}>
      <LinearGradient
        colors={[theme.groundLift, theme.ground]}
        style={StyleSheet.absoluteFill}
      />
      <SafeAreaView style={s.safe}>
      <ScrollView contentContainerStyle={s.scroll}>
        <View style={s.brand}>
          <Brand size={64} theme={theme} />
          <Text style={s.title}>Pointwise</Text>
          <Text style={s.tagline}>
            Which of your cards earns most, worked out before you pay.
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
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    safe: { flex: 1 },
    scroll: {
      paddingHorizontal: space.xl,
      paddingTop: space.xxxl,
      paddingBottom: space.xl,
      gap: space.lg,
      flexGrow: 1,
    },
    brand: { alignItems: 'center', gap: space.md, marginBottom: space.xl },
    title: { ...type.title, fontSize: 34, lineHeight: 40, color: t.ink },
    tagline: {
      ...type.body,
      color: t.inkSoft,
      textAlign: 'center',
      maxWidth: 290,
    },
    spinner: { marginTop: space.xl },

    paypal: {
      backgroundColor: '#003087',
      borderRadius: radius.md,
      paddingVertical: space.lg,
      alignItems: 'center',
    },
    paypalText: { fontFamily: UI, color: '#fff', fontSize: 16, fontWeight: '700' },

    fallback: { gap: space.md },
    label: { ...type.label, color: t.inkSoft, fontWeight: '600' },
    input: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: radius.md,
      paddingHorizontal: space.lg,
      paddingVertical: space.lg,
      fontFamily: UI,
      fontSize: 16,
      color: t.ink,
    },
    go: {
      backgroundColor: t.accent,
      borderRadius: radius.md,
      paddingVertical: space.lg,
      alignItems: 'center',
    },
    goOff: { opacity: 0.4 },
    goText: {
      fontFamily: UI,
      color: t.accentInk,
      fontSize: 16,
      fontWeight: '600',
    },
    honest: { ...type.small, lineHeight: 17, color: t.inkFaint },

    alt: { alignItems: 'center', paddingVertical: space.md },
    altText: { ...type.body, color: t.accent, fontWeight: '600' },

    error: { ...type.label, color: t.stop },
    foot: {
      ...type.small,
      lineHeight: 16,
      color: t.inkFaint,
      textAlign: 'center',
      marginTop: 'auto',
      paddingTop: space.xl,
    },
  });
