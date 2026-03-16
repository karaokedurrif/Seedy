/**
 * ChatScreen.tsx — Chat con Seedy IA (Open WebUI style)
 *
 * - Dark background, clean input bar at bottom
 * - Welcome screen with Seedy logo when empty
 * - Streaming SSE with cursor animation
 * - Camera/gallery attachment
 * - Full-width messages (no bubbles, like Open WebUI)
 */

import React, { useState, useRef, useCallback } from 'react';
import {
  View,
  FlatList,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  KeyboardAvoidingView,
  Platform,
  ActivityIndicator,
  Alert,
  Text,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons } from '@expo/vector-icons';

import { useSeedyChat } from '../hooks/useSeedyChat';
import { MessageBubble } from '../components/MessageBubble';
import { useTheme } from '../theme/ThemeContext';
import { Spacing, FontSize, Radius } from '../theme/themes';

export function ChatScreen() {
  const { theme } = useTheme();
  const {
    messages,
    isStreaming,
    error,
    sendMessage,
    sendImageForAnalysis,
    clearHistory,
  } = useSeedyChat();

  const [inputText, setInputText] = useState('');
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const flatListRef = useRef<FlatList>(null);

  const handleSend = useCallback(async () => {
    const text = inputText.trim();
    if (!text && !pendingImage) return;

    const image = pendingImage;
    setInputText('');
    setPendingImage(null);

    if (image) {
      await sendImageForAnalysis(
        image,
        text || 'Analiza esta imagen: especie, raza, condición corporal, peso estimado y salud visible.',
      );
    } else {
      await sendMessage(text);
    }
  }, [inputText, pendingImage, sendMessage, sendImageForAnalysis]);

  const handleCamera = useCallback(async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permiso denegado', 'Necesitamos acceso a la cámara');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
      base64: true,
      allowsEditing: false,
      exif: true,
    });
    if (!result.canceled && result.assets[0]?.base64) {
      setPendingImage(result.assets[0].base64);
    }
  }, []);

  const handleGallery = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permiso denegado', 'Necesitamos acceso a la galería');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
      base64: true,
      allowsEditing: false,
    });
    if (!result.canceled && result.assets[0]?.base64) {
      setPendingImage(result.assets[0].base64);
    }
  }, []);

  const scrollToEnd = useCallback(() => {
    setTimeout(() => {
      flatListRef.current?.scrollToEnd({ animated: true });
    }, 100);
  }, []);

  // ── Welcome (empty state) ──────────────────────────────────────────
  const WelcomeView = () => (
    <View style={styles.welcomeContainer}>
      <Image
        source={require('../../assets/images/logo.png')}
        style={styles.welcomeLogo}
      />
      <Text style={[styles.welcomeTitle, { color: theme.text }]}>
        Seedy
      </Text>
      <Text style={[styles.welcomeSubtitle, { color: theme.textSecondary }]}>
        Asistente IA para ganadería de precisión
      </Text>

      <View style={styles.suggestionsContainer}>
        {[
          '¿Qué razas de capones recomiendas para Segovia?',
          '¿Cómo montar un sistema IoT con PorciData?',
          '¿Cuáles son los rangos de temperatura normales?',
        ].map((suggestion, i) => (
          <TouchableOpacity
            key={i}
            style={[
              styles.suggestionChip,
              { backgroundColor: theme.bg2, borderColor: theme.border },
            ]}
            onPress={() => {
              setInputText(suggestion);
            }}
          >
            <Text
              style={[styles.suggestionText, { color: theme.textSecondary }]}
            >
              {suggestion}
            </Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: theme.bg1 }]}
      edges={['top']}
    >
      {/* Header */}
      <View style={[styles.header, { backgroundColor: theme.bg0, borderBottomColor: theme.border }]}>
        <Image
          source={require('../../assets/images/favicon.png')}
          style={styles.headerIcon}
        />
        <Text style={[styles.headerTitle, { color: theme.text }]}>Seedy</Text>
        <Text style={[styles.headerModel, { color: theme.textMuted }]}>v6-local</Text>
        <View style={{ flex: 1 }} />
        {messages.length > 0 && (
          <TouchableOpacity onPress={clearHistory} style={styles.headerBtn}>
            <Ionicons name="create-outline" size={20} color={theme.textSecondary} />
          </TouchableOpacity>
        )}
      </View>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        keyboardVerticalOffset={0}
      >
        {/* Messages */}
        <FlatList
          ref={flatListRef}
          data={messages}
          keyExtractor={(_, i) => String(i)}
          renderItem={({ item, index }) => (
            <MessageBubble
              message={item}
              isStreaming={isStreaming && index === messages.length - 1}
            />
          )}
          contentContainerStyle={[
            styles.messageList,
            messages.length === 0 && styles.messageListEmpty,
          ]}
          onContentSizeChange={scrollToEnd}
          showsVerticalScrollIndicator={false}
          ListEmptyComponent={<WelcomeView />}
        />

        {/* Pending image preview */}
        {pendingImage && (
          <View
            style={[
              styles.imagePreview,
              {
                backgroundColor: theme.bg2,
                borderTopColor: theme.border,
              },
            ]}
          >
            <Image
              source={{ uri: `data:image/jpeg;base64,${pendingImage}` }}
              style={[styles.previewThumb, { borderColor: theme.border }]}
            />
            <TouchableOpacity
              onPress={() => setPendingImage(null)}
              style={styles.removeImage}
            >
              <Ionicons name="close-circle" size={22} color={theme.error} />
            </TouchableOpacity>
          </View>
        )}

        {/* Input bar — Open WebUI style */}
        <View
          style={[
            styles.inputBar,
            {
              backgroundColor: theme.bg0,
              borderTopColor: theme.border,
            },
          ]}
        >
          <View
            style={[
              styles.inputRow,
              {
                backgroundColor: theme.inputBg,
                borderColor: theme.inputBorder,
              },
            ]}
          >
            {/* Attach buttons */}
            <TouchableOpacity
              onPress={handleCamera}
              style={styles.attachBtn}
              disabled={isStreaming}
            >
              <Ionicons
                name="camera-outline"
                size={22}
                color={isStreaming ? theme.textMuted : theme.textSecondary}
              />
            </TouchableOpacity>
            <TouchableOpacity
              onPress={handleGallery}
              style={styles.attachBtn}
              disabled={isStreaming}
            >
              <Ionicons
                name="image-outline"
                size={20}
                color={isStreaming ? theme.textMuted : theme.textSecondary}
              />
            </TouchableOpacity>

            {/* Text input */}
            <TextInput
              style={[
                styles.textInput,
                { color: theme.inputText },
              ]}
              placeholder="Pregunta a Seedy..."
              placeholderTextColor={theme.inputPlaceholder}
              value={inputText}
              onChangeText={setInputText}
              multiline
              maxLength={2000}
              editable={!isStreaming}
              returnKeyType="send"
              onSubmitEditing={handleSend}
            />

            {/* Send */}
            <TouchableOpacity
              onPress={handleSend}
              style={[
                styles.sendButton,
                {
                  backgroundColor:
                    inputText.trim() || pendingImage
                      ? theme.primary
                      : theme.textMuted + '40',
                },
              ]}
              disabled={isStreaming || (!inputText.trim() && !pendingImage)}
            >
              {isStreaming ? (
                <ActivityIndicator size="small" color="#FFF" />
              ) : (
                <Ionicons name="arrow-up" size={20} color="#FFF" />
              )}
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  flex: {
    flex: 1,
  },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm + 2,
    borderBottomWidth: 1,
    gap: Spacing.sm,
  },
  headerIcon: {
    width: 28,
    height: 28,
    borderRadius: 6,
  },
  headerTitle: {
    fontSize: FontSize.bodyLarge,
    fontWeight: '700',
  },
  headerModel: {
    fontSize: FontSize.caption,
    marginLeft: 2,
  },
  headerBtn: {
    padding: Spacing.sm,
  },

  // Messages
  messageList: {
    paddingBottom: Spacing.sm,
    flexGrow: 1,
  },
  messageListEmpty: {
    justifyContent: 'center',
  },

  // Welcome
  welcomeContainer: {
    alignItems: 'center',
    paddingHorizontal: Spacing.xl,
    paddingTop: 40,
  },
  welcomeLogo: {
    width: 80,
    height: 80,
    borderRadius: 20,
    marginBottom: Spacing.md,
  },
  welcomeTitle: {
    fontSize: FontSize.headline,
    fontWeight: '800',
  },
  welcomeSubtitle: {
    fontSize: FontSize.body,
    marginTop: Spacing.xs,
    textAlign: 'center',
  },
  suggestionsContainer: {
    marginTop: Spacing.xl,
    width: '100%',
    gap: Spacing.sm,
  },
  suggestionChip: {
    borderRadius: Radius.md,
    borderWidth: 1,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.md,
  },
  suggestionText: {
    fontSize: FontSize.body,
  },

  // Image preview
  imagePreview: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderTopWidth: 1,
  },
  previewThumb: {
    width: 56,
    height: 56,
    borderRadius: Radius.sm,
    borderWidth: 1,
  },
  removeImage: {
    marginLeft: Spacing.sm,
  },

  // Input bar — Open WebUI rounded
  inputBar: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderTopWidth: 1,
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    borderWidth: 1,
    borderRadius: Radius.xl,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 4,
    gap: 2,
  },
  attachBtn: {
    padding: Spacing.sm,
    justifyContent: 'center',
    alignItems: 'center',
  },
  textInput: {
    flex: 1,
    minHeight: 36,
    maxHeight: 120,
    fontSize: 15,
    paddingVertical: Spacing.sm,
    paddingHorizontal: Spacing.xs,
  },
  sendButton: {
    width: 34,
    height: 34,
    borderRadius: 17,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 1,
  },
});
