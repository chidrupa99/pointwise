/**
 * The advisor sheet.
 *
 * The trace under each answer is the point of this screen as much as the
 * answer is. A chatbot that says "use the Gold, $8.64 back" is indistinguishable
 * from one that made the number up; showing that the engine ranked fourteen
 * cards is what makes the figure worth acting on.
 */

import React, { useCallback, useEffect, useRef, useState } from 'react';
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

import {
  chat,
  fetchAgentStatus,
  type AgentStatus,
  type ChatTurn,
  type TraceEntry,
} from '../api';
import { quietPosition } from '../nearby';
import { dark, light, type Theme } from '../theme';

interface Bubble extends ChatTurn {
  trace?: TraceEntry[];
  failed?: boolean;
  /** Quick replies offered with this bubble, shown only while it is the last. */
  suggestions?: string[];
}

/** Openers that each exercise a different tool, so the demo has a path. */
const OPENERS = [
  'Which card for $120 at Trader Joe’s?',
  'I’ve spent $5,800 on groceries. Still the same card?',
  'What am I leaving on the table?',
  'Why does Costco not count as grocery?',
] as const;

export function Chat() {
  const theme: Theme = useColorScheme() === 'light' ? light : dark;
  const s = styles(theme);

  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<AgentStatus | null>(null);
  const scroller = useRef<React.ComponentRef<typeof ScrollView>>(null);
  const composer = useRef<React.ComponentRef<typeof TextInput>>(null);

  useEffect(() => {
    fetchAgentStatus().then(setStatus).catch(() => setStatus(null));
  }, []);

  const last = bubbles[bubbles.length - 1];

  const send = useCallback(
    async (text: string) => {
      const question = text.trim();
      if (!question || busy) return;

      // The history sent up is text-only, so the failed turn below is dropped
      // from it rather than being replayed as if the advisor had answered.
      const asked: Bubble[] = [...bubbles, { role: 'user', content: question }];
      setBubbles(asked);
      setDraft('');
      setBusy(true);

      try {
        const position = await quietPosition();
        const reply = await chat(
          asked
            .filter((b) => !b.failed)
            .map(({ role, content }) => ({ role, content })),
          position,
        );
        setBubbles([
          ...asked,
          {
            role: 'assistant',
            content: reply.text,
            trace: reply.trace,
            suggestions: reply.suggestions,
          },
        ]);
      } catch (error) {
        setBubbles([
          ...asked,
          {
            role: 'assistant',
            content:
              error instanceof Error ? error.message : 'The advisor is unreachable.',
            failed: true,
          },
        ]);
      } finally {
        setBusy(false);
      }
    },
    [bubbles, busy],
  );

  return (
    <SafeAreaView style={s.wrap} edges={['left', 'right', 'bottom']}>
      <KeyboardAvoidingView
        style={s.wrap}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          ref={scroller}
          style={s.feed}
          contentContainerStyle={s.feedInner}
          onContentSizeChange={() => scroller.current?.scrollToEnd({ animated: true })}
          keyboardDismissMode="interactive"
        >
          {status && !status.configured && (
            <View style={s.notice}>
              <Text style={s.noticeTitle}>Advisor not connected</Text>
              <Text style={s.noticeBody}>{status.hint}</Text>
            </View>
          )}

          {bubbles.length === 0 && (
            <View style={s.empty}>
              <Text style={s.emptyLead}>
                Ask about a purchase you&rsquo;re about to make, or about what
                your cards have been doing on the checkouts Pointwise routed.
              </Text>
              <Text style={s.emptyNote}>
                Every figure comes from the rules engine. The advisor reads it out;
                it never works it out.
              </Text>
              {OPENERS.map((opener) => (
                <Pressable
                  key={opener}
                  accessibilityRole="button"
                  onPress={() => send(opener)}
                  style={({ pressed }) => [s.opener, pressed && { opacity: 0.6 }]}
                >
                  <Text style={s.openerText}>{opener}</Text>
                </Pressable>
              ))}
            </View>
          )}

          {bubbles.map((bubble, index) => (
            <Message key={index} bubble={bubble} theme={theme} />
          ))}

          {/* Quick replies, only under the newest bubble. Leaving them on
              older ones would invite answering a question two turns stale. */}
          {!busy && last?.suggestions && last.suggestions.length > 0 && (
            <View style={s.pills}>
              {last.suggestions.map((option) => (
                <Pressable
                  key={option}
                  accessibilityRole="button"
                  onPress={() => send(option)}
                  style={({ pressed }) => [s.pill, pressed && s.pillOn]}
                >
                  <Text style={s.pillText}>{option}</Text>
                </Pressable>
              ))}
              <Pressable
                accessibilityRole="button"
                accessibilityLabel="Type a different answer"
                onPress={() => composer.current?.focus()}
                style={({ pressed }) => [
                  s.pill,
                  s.pillOther,
                  pressed && s.pillOn,
                ]}
              >
                <Text style={[s.pillText, s.pillOtherText]}>Other…</Text>
              </Pressable>
            </View>
          )}

          {busy && (
            <View style={s.thinking}>
              <ActivityIndicator color={theme.inkFaint} size="small" />
              <Text style={s.thinkingText}>Consulting the engine</Text>
            </View>
          )}
        </ScrollView>

        <View style={s.composer}>
          <TextInput
            ref={composer}
            style={s.input}
            value={draft}
            onChangeText={setDraft}
            placeholder="Which card should I use?"
            placeholderTextColor={theme.inkFaint}
            multiline
            returnKeyType="send"
            onSubmitEditing={() => send(draft)}
            accessibilityLabel="Your question"
            editable={!busy}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send"
            onPress={() => send(draft)}
            disabled={busy || !draft.trim()}
            style={({ pressed }) => [
              s.send,
              (busy || !draft.trim()) && { opacity: 0.35 },
              pressed && { opacity: 0.6 },
            ]}
          >
            <Text style={s.sendText}>Ask</Text>
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

function Message({ bubble, theme }: { bubble: Bubble; theme: Theme }) {
  const s = styles(theme);
  const mine = bubble.role === 'user';
  return (
    <View style={mine ? s.mineWrap : s.theirsWrap}>
      <View style={[mine ? s.mine : s.theirs, bubble.failed && s.broken]}>
        <Text style={[mine ? s.mineText : s.theirsText, bubble.failed && s.brokenText]}>
          {bubble.content}
        </Text>
      </View>
      {bubble.trace && bubble.trace.length > 0 && (
        <View style={s.trace}>
          {bubble.trace.map((entry, index) => (
            <Text key={index} style={[s.traceRow, !entry.ok && s.traceBad]}>
              {entry.ok ? '✓' : '×'} {entry.summary}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}

const styles = (t: Theme) =>
  StyleSheet.create({
    wrap: { flex: 1, backgroundColor: t.ground },
    feed: { flex: 1 },
    feedInner: { padding: 16, gap: 12 },

    notice: {
      backgroundColor: t.warnSoft,
      borderWidth: 1,
      borderColor: t.warn,
      borderRadius: 9,
      padding: 12,
      gap: 4,
    },
    noticeTitle: { color: t.warn, fontSize: 13, fontWeight: '700' },
    noticeBody: { color: t.inkSoft, fontSize: 12.5, lineHeight: 17 },

    empty: { gap: 10, paddingTop: 4 },
    emptyLead: { color: t.ink, fontSize: 15.5, lineHeight: 22 },
    emptyNote: {
      color: t.inkFaint,
      fontSize: 12.5,
      lineHeight: 18,
      marginBottom: 6,
    },
    opener: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 9,
      paddingVertical: 11,
      paddingHorizontal: 13,
    },
    openerText: { color: t.accent, fontSize: 14, lineHeight: 19 },

    mineWrap: { alignItems: 'flex-end' },
    theirsWrap: { alignItems: 'flex-start', gap: 6 },
    mine: {
      backgroundColor: t.accent,
      borderRadius: 14,
      borderBottomRightRadius: 4,
      paddingVertical: 9,
      paddingHorizontal: 13,
      maxWidth: '86%',
    },
    mineText: { color: t.accentInk, fontSize: 14.5, lineHeight: 20 },
    theirs: {
      backgroundColor: t.surface,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 14,
      borderBottomLeftRadius: 4,
      paddingVertical: 10,
      paddingHorizontal: 13,
      maxWidth: '92%',
    },
    theirsText: { color: t.ink, fontSize: 14.5, lineHeight: 21 },
    broken: { backgroundColor: t.stopSoft, borderColor: t.stop },
    brokenText: { color: t.stop, fontSize: 13 },

    trace: { gap: 3, paddingLeft: 3 },
    traceRow: { color: t.inkFaint, fontSize: 11.5, lineHeight: 16 },
    traceBad: { color: t.warn },

    thinking: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingLeft: 3 },
    thinkingText: { color: t.inkFaint, fontSize: 12.5 },

    pills: {
      flexDirection: 'row',
      flexWrap: 'wrap',
      gap: 8,
      marginTop: 10,
      marginBottom: 4,
    },
    pill: {
      paddingVertical: 9,
      paddingHorizontal: 14,
      borderRadius: 999,
      borderWidth: 1,
      borderColor: t.accent,
      backgroundColor: t.accentSoft,
    },
    pillOn: { opacity: 0.6 },
    pillText: { color: t.accent, fontSize: 14, fontWeight: '600' },
    pillOther: { borderColor: t.rule, backgroundColor: t.surface },
    pillOtherText: { color: t.inkSoft, fontWeight: '500' },

    composer: {
      flexDirection: 'row',
      alignItems: 'flex-end',
      gap: 8,
      paddingHorizontal: 16,
      paddingTop: 10,
      paddingBottom: 10,
      borderTopWidth: 1,
      borderTopColor: t.rule,
      backgroundColor: t.surface,
    },
    input: {
      flex: 1,
      maxHeight: 110,
      minHeight: 40,
      backgroundColor: t.sunk,
      borderWidth: 1,
      borderColor: t.rule,
      borderRadius: 9,
      paddingHorizontal: 12,
      paddingTop: 10,
      paddingBottom: 10,
      color: t.ink,
      fontSize: 14.5,
    },
    send: {
      backgroundColor: t.accent,
      borderRadius: 9,
      paddingHorizontal: 16,
      height: 40,
      justifyContent: 'center',
    },
    sendText: { color: t.accentInk, fontSize: 14.5, fontWeight: '700' },
  });
