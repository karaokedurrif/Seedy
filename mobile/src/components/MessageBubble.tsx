/**
 * MessageBubble.tsx — Estilo Open WebUI
 *
 * - Sin burbujas de colores. Fondo transparente para assistant,
 *   subtle bg para user.
 * - Avatar con icono Seedy para assistant, emoji user
 * - Markdown-like text, cursor animado
 * - Timestamp discreto
 */

import React from 'react';
import { View, Text, StyleSheet, Image } from 'react-native';
import { useTheme } from '../theme/ThemeContext';
import { Spacing, FontSize, Radius } from '../theme/themes';
import type { ChatMessage } from '../api/seedyClient';

interface Props {
  message: ChatMessage;
  isStreaming?: boolean;
}

export function MessageBubble({ message, isStreaming }: Props) {
  const { theme } = useTheme();
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';

  if (isSystem) return null;

  return (
    <View
      style={[
        styles.row,
        {
          backgroundColor: isUser ? theme.chatUser : theme.chatAssistant,
          borderBottomWidth: 1,
          borderBottomColor: theme.divider,
        },
      ]}
    >
      {/* Avatar */}
      <View
        style={[
          styles.avatar,
          {
            backgroundColor: isUser
              ? theme.primary + '30'
              : theme.bg2,
          },
        ]}
      >
        {isUser ? (
          <Text style={styles.avatarEmoji}>🧑‍🌾</Text>
        ) : (
          <Image
            source={require('../../assets/images/favicon.png')}
            style={styles.avatarImage}
          />
        )}
      </View>

      {/* Content */}
      <View style={styles.content}>
        <Text
          style={[
            styles.roleName,
            { color: isUser ? theme.text : theme.primary },
          ]}
        >
          {isUser ? 'Tú' : 'Seedy'}
        </Text>

        {/* Attached image */}
        {message.image && (
          <Image
            source={{ uri: `data:image/jpeg;base64,${message.image}` }}
            style={[styles.attachedImage, { borderColor: theme.border }]}
            resizeMode="cover"
          />
        )}

        {/* Message text */}
        <Text
          style={[
            styles.messageText,
            {
              color: isUser ? theme.chatUserText : theme.chatAssistantText,
            },
          ]}
          selectable
        >
          {message.content}
          {isStreaming && !isUser && (
            <Text style={[styles.cursor, { color: theme.primary }]}>▌</Text>
          )}
        </Text>

        {/* Timestamp */}
        {message.timestamp && (
          <Text style={[styles.timestamp, { color: theme.textMuted }]}>
            {new Date(message.timestamp).toLocaleTimeString('es-ES', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </Text>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.md,
    gap: Spacing.md,
  },
  avatar: {
    width: 36,
    height: 36,
    borderRadius: Radius.md,
    justifyContent: 'center',
    alignItems: 'center',
    marginTop: 2,
  },
  avatarEmoji: {
    fontSize: 18,
  },
  avatarImage: {
    width: 22,
    height: 22,
    borderRadius: 4,
  },
  content: {
    flex: 1,
  },
  roleName: {
    fontSize: FontSize.caption,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 4,
  },
  messageText: {
    fontSize: FontSize.body + 1,
    lineHeight: 22,
  },
  cursor: {
    fontWeight: '700',
    fontSize: FontSize.body + 2,
  },
  timestamp: {
    fontSize: FontSize.caption - 1,
    marginTop: 6,
  },
  attachedImage: {
    width: '100%',
    height: 180,
    borderRadius: Radius.md,
    marginBottom: Spacing.sm,
    borderWidth: 1,
  },
});
