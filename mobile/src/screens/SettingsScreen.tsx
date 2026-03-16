/**
 * SettingsScreen.tsx — Configuración de la app Seedy (themed)
 *
 * Features:
 * - Selector de tema (3 presets con preview de colores)
 * - Configurar URL del backend (SecureStore)
 * - Health check del servidor
 * - Info del modelo (v6) y colecciones RAG
 * - Configuración térmica (emisividad, especie por defecto)
 * - Datos de la cuenta / About
 * - Open WebUI style via useTheme()
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  TextInput,
  TouchableOpacity,
  ActivityIndicator,
  Linking,
  Alert,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as SecureStore from 'expo-secure-store';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';

import { checkHealth, HealthStatus, STORAGE_KEYS } from '../api/seedyClient';
import { useTheme } from '../theme/ThemeContext';
import { Spacing, FontSize, THEME_LIST, type ThemePreset } from '../theme/themes';

const APP_VERSION = '1.0.0';
const BUILD_CODE = 'fase12-v1';

export function SettingsScreen() {
  const { theme, preset, setPreset } = useTheme();
  const [backendUrl, setBackendUrl] = useState('');
  const [editUrl, setEditUrl] = useState('');
  const [isEditing, setIsEditing] = useState(false);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [checking, setChecking] = useState(false);

  // ── Cargar URL guardada ────────────────────────────────────────────
  useEffect(() => {
    (async () => {
      const url = await SecureStore.getItemAsync(STORAGE_KEYS.BACKEND_URL);
      const resolved = url || 'https://seedy-api.neofarm.io';
      setBackendUrl(resolved);
      setEditUrl(resolved);
    })();
  }, []);

  // ── Guardar URL ────────────────────────────────────────────────────
  const saveUrl = useCallback(async () => {
    let url = editUrl.trim();
    if (url.endsWith('/')) url = url.slice(0, -1);
    if (!url.startsWith('http')) url = `http://${url}`;

    await SecureStore.setItemAsync(STORAGE_KEYS.BACKEND_URL, url);
    setBackendUrl(url);
    setIsEditing(false);
    Alert.alert('Guardado', `URL actualizada a:\n${url}`);
  }, [editUrl]);

  // ── Health check ───────────────────────────────────────────────────
  const runHealthCheck = useCallback(async () => {
    setChecking(true);
    setHealth(null);
    try {
      const result = await checkHealth();
      setHealth(result);
    } catch (err: any) {
      setHealth({
        status: 'error',
        model: 'N/A',
        rag_collections: 0,
        uptime: 0,
        error: err.message || 'Sin conexión',
      });
    } finally {
      setChecking(false);
    }
  }, []);

  // ── Section renderer ──────────────────────────────────────────────
  const Section = ({
    icon,
    title,
    children,
  }: {
    icon: string;
    title: string;
    children: React.ReactNode;
  }) => (
    <View style={[styles.section, { backgroundColor: theme.bg2, borderColor: theme.border }]}>
      <View style={styles.sectionHeader}>
        <Ionicons name={icon as any} size={20} color={theme.primary} />
        <Text style={[styles.sectionTitle, { color: theme.text }]}>
          {title}
        </Text>
      </View>
      {children}
    </View>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.bg1 }]}>
      <ScrollView contentContainerStyle={styles.scrollContent}>
        {/* ── Logo / Header ─────────────────────────────────────── */}
        <View style={[styles.headerSection, { backgroundColor: theme.bg0 }]}>
          <Image
            source={require('../../assets/images/logo.png')}
            style={styles.logoImage}
          />
          <Text style={[styles.appName, { color: theme.text }]}>Seedy</Text>
          <Text style={[styles.appSubtitle, { color: theme.textSecondary }]}>
            NeoFarm AI Assistant
          </Text>
          <Text style={[styles.versionText, { color: theme.textMuted }]}>
            v{APP_VERSION} ({BUILD_CODE})
          </Text>
        </View>

        {/* ── Apariencia — Theme Picker ─────────────────────────── */}
        <Section icon="color-palette" title="Apariencia">
          <Text style={[styles.themeHint, { color: theme.textSecondary }]}>
            Elige uno de los 3 temas preconfigurados
          </Text>
          <View style={styles.themeGrid}>
            {THEME_LIST.map((t) => {
              const isActive = preset === t.id;
              return (
                <TouchableOpacity
                  key={t.id}
                  style={[
                    styles.themeCard,
                    { backgroundColor: t.bg2, borderColor: isActive ? t.primary : t.border, borderWidth: isActive ? 2 : 1 },
                  ]}
                  onPress={() => setPreset(t.id)}
                  activeOpacity={0.7}
                >
                  {/* Color swatches preview */}
                  <View style={styles.themeSwatch}>
                    <View style={[styles.swatchDot, { backgroundColor: t.bg0 }]} />
                    <View style={[styles.swatchDot, { backgroundColor: t.bg1 }]} />
                    <View style={[styles.swatchDot, { backgroundColor: t.primary }]} />
                    <View style={[styles.swatchDot, { backgroundColor: t.accent }]} />
                  </View>
                  <Text
                    style={[
                      styles.themeName,
                      { color: t.text },
                    ]}
                  >
                    {t.name}
                  </Text>
                  {isActive && (
                    <Ionicons
                      name="checkmark-circle"
                      size={18}
                      color={t.primary}
                      style={styles.themeCheck}
                    />
                  )}
                </TouchableOpacity>
              );
            })}
          </View>
        </Section>

        {/* ── Servidor ──────────────────────────────────────────── */}
        <Section icon="server" title="Servidor Backend">
          {isEditing ? (
            <View style={styles.urlEditContainer}>
              <TextInput
                style={[
                  styles.urlInput,
                  {
                    backgroundColor: theme.inputBg,
                    color: theme.inputText,
                    borderColor: theme.primary,
                  },
                ]}
                value={editUrl}
                onChangeText={setEditUrl}
                placeholder="https://seedy-api.neofarm.io"
                placeholderTextColor={theme.inputPlaceholder}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="url"
              />
              <View style={styles.urlActions}>
                <TouchableOpacity
                  style={[styles.urlSaveBtn, { backgroundColor: theme.primary }]}
                  onPress={saveUrl}
                >
                  <Text style={styles.urlSaveBtnText}>Guardar</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.urlCancelBtn, { backgroundColor: theme.bg3 }]}
                  onPress={() => {
                    setEditUrl(backendUrl);
                    setIsEditing(false);
                  }}
                >
                  <Text style={[styles.urlCancelBtnText, { color: theme.textSecondary }]}>
                    Cancelar
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <TouchableOpacity
              style={[styles.urlDisplay, { backgroundColor: theme.bg3 }]}
              onPress={() => setIsEditing(true)}
            >
              <Text style={[styles.urlText, { color: theme.text }]}>
                {backendUrl}
              </Text>
              <Ionicons name="pencil" size={16} color={theme.textMuted} />
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={[styles.healthBtn, { borderColor: theme.primary }]}
            onPress={runHealthCheck}
            disabled={checking}
          >
            {checking ? (
              <ActivityIndicator size="small" color={theme.primary} />
            ) : (
              <>
                <Ionicons name="pulse" size={18} color={theme.primary} />
                <Text style={[styles.healthBtnText, { color: theme.primary }]}>
                  Comprobar conexión
                </Text>
              </>
            )}
          </TouchableOpacity>

          {health && (
            <View
              style={[
                styles.healthResult,
                {
                  backgroundColor:
                    health.status === 'ok'
                      ? theme.success + '15'
                      : theme.error + '15',
                },
              ]}
            >
              <View style={styles.healthRow}>
                <Text style={[styles.healthLabel, { color: theme.textSecondary }]}>
                  Estado:
                </Text>
                <Text
                  style={[
                    styles.healthValue,
                    {
                      color:
                        health.status === 'ok'
                          ? theme.success
                          : theme.error,
                    },
                  ]}
                >
                  {health.status === 'ok' ? '✅ Conectado' : '❌ Error'}
                </Text>
              </View>
              {health.model && (
                <View style={styles.healthRow}>
                  <Text style={[styles.healthLabel, { color: theme.textSecondary }]}>
                    Modelo:
                  </Text>
                  <Text style={[styles.healthValue, { color: theme.text }]}>
                    {health.model}
                  </Text>
                </View>
              )}
              {health.rag_collections > 0 && (
                <View style={styles.healthRow}>
                  <Text style={[styles.healthLabel, { color: theme.textSecondary }]}>
                    RAG:
                  </Text>
                  <Text style={[styles.healthValue, { color: theme.text }]}>
                    {health.rag_collections} colecciones
                  </Text>
                </View>
              )}
              {health.error && (
                <View style={styles.healthRow}>
                  <Text style={[styles.healthLabel, { color: theme.textSecondary }]}>
                    Error:
                  </Text>
                  <Text style={[styles.healthValue, { color: theme.error }]}>
                    {health.error}
                  </Text>
                </View>
              )}
            </View>
          )}
        </Section>

        {/* ── Funciones ─────────────────────────────────────────── */}
        <Section icon="apps" title="Funciones">
          <View style={styles.featureList}>
            <FeatureItem
              icon="chatbubbles"
              name="Chat con Seedy"
              desc="Consultas agrícola-ganaderas via IA + RAG"
              enabled
              theme={theme}
            />
            <FeatureItem
              icon="camera"
              name="Vision Camera"
              desc="Identificación de raza/especie/estado"
              enabled
              theme={theme}
            />
            <FeatureItem
              icon="thermometer"
              name="Cámara Térmica"
              desc="Monitorización USB-C con alertas"
              enabled
              theme={theme}
            />
            <FeatureItem
              icon="git-branch"
              name="Genética"
              desc="Simulación F1-F5, BLUP, cruces"
              enabled
              theme={theme}
            />
          </View>
        </Section>

        {/* ── Modelo ────────────────────────────────────────────── */}
        <Section icon="hardware-chip" title="Modelo IA">
          <View style={styles.infoGrid}>
            <InfoRow label="Base" value="Qwen2.5-7B-Instruct" theme={theme} />
            <InfoRow label="Fine-tune" value="seedy:v6-local (Q8_0)" theme={theme} />
            <InfoRow label="Ejemplos SFT" value="302" theme={theme} />
            <InfoRow
              label="Dominios"
              value="IoT, Nutrición, Genética, Normativa, GeoTwin…"
              theme={theme}
            />
            <InfoRow label="Inferencia" value="Ollama local" theme={theme} />
            <InfoRow label="VRAM" value="~8.1 GB (RTX 5080)" theme={theme} />
          </View>
        </Section>

        {/* ── Cámara térmica ────────────────────────────────────── */}
        <Section icon="flame" title="Cámara Térmica">
          <View style={styles.infoGrid}>
            <InfoRow label="Protocolo" value="UVC (USB Video Class)" theme={theme} />
            <InfoRow label="Objetivo" value="9mm (campo estrecho)" theme={theme} />
            <InfoRow label="Resolución" value="256×192 + TISR 384×288" theme={theme} />
            <InfoRow label="Emisividad" value="0.95 (animales)" theme={theme} />
            <InfoRow
              label="Cámaras"
              value="InfiRay P2 Pro, T2S+, FLIR One"
              theme={theme}
            />
          </View>
        </Section>

        {/* ── Plataformas ───────────────────────────────────────── */}
        <Section icon="globe" title="Plataformas NeoFarm">
          {[
            { emoji: '🐄', name: 'VacasData Hub', url: 'https://hub.vacasdata.com', domain: 'hub.vacasdata.com' },
            { emoji: '🐷', name: 'PorciData Hub', url: 'https://hub.porcidata.com', domain: 'hub.porcidata.com' },
            { emoji: '🐔', name: 'Ovosfera Capones', url: 'https://capones.ovosfera.com', domain: 'capones.ovosfera.com' },
          ].map((platform) => (
            <TouchableOpacity
              key={platform.url}
              style={[styles.platformItem, { borderBottomColor: theme.divider }]}
              onPress={() => Linking.openURL(platform.url)}
            >
              <Text style={styles.platformIcon}>{platform.emoji}</Text>
              <View style={styles.platformInfo}>
                <Text style={[styles.platformName, { color: theme.text }]}>
                  {platform.name}
                </Text>
                <Text style={[styles.platformUrl, { color: theme.primary }]}>
                  {platform.domain}
                </Text>
              </View>
              <Ionicons name="open-outline" size={16} color={theme.textMuted} />
            </TouchableOpacity>
          ))}
        </Section>

        {/* ── Acerca de ─────────────────────────────────────────── */}
        <View style={styles.aboutSection}>
          <Text style={[styles.aboutText, { color: theme.textMuted }]}>
            Seedy © 2025 NeoFarm · David Durrif
          </Text>
          <Text style={[styles.aboutText, { color: theme.textMuted }]}>
            IA agropecuaria multi-especie con RAG, visión y genética
          </Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

// ── Componentes auxiliares ──────────────────────────────────────────

function FeatureItem({
  icon,
  name,
  desc,
  enabled,
  theme,
}: {
  icon: string;
  name: string;
  desc: string;
  enabled: boolean;
  theme: any;
}) {
  return (
    <View style={styles.featureItem}>
      <View
        style={[
          styles.featureIconBg,
          { backgroundColor: enabled ? theme.primarySurface : theme.bg3 },
        ]}
      >
        <Ionicons
          name={icon as any}
          size={20}
          color={enabled ? theme.primary : theme.textMuted}
        />
      </View>
      <View style={styles.featureInfo}>
        <Text style={[styles.featureName, { color: theme.text }]}>{name}</Text>
        <Text style={[styles.featureDesc, { color: theme.textSecondary }]}>
          {desc}
        </Text>
      </View>
      <Ionicons
        name={enabled ? 'checkmark-circle' : 'close-circle-outline'}
        size={20}
        color={enabled ? theme.success : theme.textMuted}
      />
    </View>
  );
}

function InfoRow({
  label,
  value,
  theme,
}: {
  label: string;
  value: string;
  theme: any;
}) {
  return (
    <View style={[styles.infoRow, { borderBottomColor: theme.divider }]}>
      <Text style={[styles.infoLabel, { color: theme.textSecondary }]}>
        {label}
      </Text>
      <Text style={[styles.infoValue, { color: theme.text }]}>{value}</Text>
    </View>
  );
}

// ── Estilos ────────────────────────────────────────────────────────

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 40,
  },

  // Header
  headerSection: {
    alignItems: 'center',
    padding: Spacing.xl,
    paddingTop: Spacing.lg,
  },
  logoImage: {
    width: 64,
    height: 64,
    borderRadius: 16,
  },
  appName: {
    fontSize: 28,
    fontWeight: '800',
    marginTop: Spacing.sm,
  },
  appSubtitle: {
    fontSize: FontSize.body,
    marginTop: 4,
  },
  versionText: {
    fontSize: FontSize.caption,
    marginTop: 4,
  },

  // Sections
  section: {
    marginHorizontal: Spacing.md,
    marginTop: Spacing.md,
    borderRadius: 16,
    padding: Spacing.lg,
    borderWidth: 1,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  sectionTitle: {
    fontSize: FontSize.bodyLarge,
    fontWeight: '600',
  },

  // Theme picker
  themeHint: {
    fontSize: FontSize.caption,
    marginBottom: Spacing.md,
  },
  themeGrid: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  themeCard: {
    flex: 1,
    borderRadius: 12,
    padding: Spacing.md,
    alignItems: 'center',
    position: 'relative',
  },
  themeSwatch: {
    flexDirection: 'row',
    gap: 4,
    marginBottom: Spacing.sm,
  },
  swatchDot: {
    width: 16,
    height: 16,
    borderRadius: 8,
  },
  themeName: {
    fontSize: FontSize.caption,
    fontWeight: '600',
  },
  themeCheck: {
    position: 'absolute',
    top: 6,
    right: 6,
  },

  // URL
  urlDisplay: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: Spacing.md,
    borderRadius: 12,
  },
  urlText: {
    fontSize: FontSize.body,
    fontFamily: 'monospace',
    flex: 1,
  },
  urlEditContainer: {
    gap: Spacing.sm,
  },
  urlInput: {
    padding: Spacing.md,
    borderRadius: 12,
    fontSize: FontSize.body,
    fontFamily: 'monospace',
    borderWidth: 2,
  },
  urlActions: {
    flexDirection: 'row',
    gap: Spacing.sm,
  },
  urlSaveBtn: {
    flex: 1,
    paddingVertical: Spacing.sm,
    borderRadius: 8,
    alignItems: 'center',
  },
  urlSaveBtnText: {
    color: '#FFF',
    fontWeight: '600',
    fontSize: FontSize.body,
  },
  urlCancelBtn: {
    flex: 1,
    paddingVertical: Spacing.sm,
    borderRadius: 8,
    alignItems: 'center',
  },
  urlCancelBtnText: {
    fontWeight: '600',
    fontSize: FontSize.body,
  },

  // Health
  healthBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: Spacing.sm,
    marginTop: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: 8,
    borderWidth: 1,
  },
  healthBtnText: {
    fontWeight: '600',
    fontSize: FontSize.body,
  },
  healthResult: {
    marginTop: Spacing.md,
    padding: Spacing.md,
    borderRadius: 12,
  },
  healthRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
  },
  healthLabel: {
    fontSize: FontSize.body,
  },
  healthValue: {
    fontSize: FontSize.body,
    fontWeight: '600',
  },

  // Features
  featureList: {
    gap: Spacing.md,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
  },
  featureIconBg: {
    width: 40,
    height: 40,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  featureInfo: {
    flex: 1,
  },
  featureName: {
    fontSize: FontSize.body,
    fontWeight: '600',
  },
  featureDesc: {
    fontSize: FontSize.caption,
  },

  // Info grid
  infoGrid: {
    gap: Spacing.xs,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 6,
    borderBottomWidth: 1,
  },
  infoLabel: {
    fontSize: FontSize.body,
  },
  infoValue: {
    fontSize: FontSize.body,
    fontWeight: '500',
    maxWidth: '60%',
    textAlign: 'right',
  },

  // Platforms
  platformItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.md,
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
  },
  platformIcon: {
    fontSize: 28,
  },
  platformInfo: {
    flex: 1,
  },
  platformName: {
    fontSize: FontSize.body,
    fontWeight: '600',
  },
  platformUrl: {
    fontSize: FontSize.caption,
  },

  // About
  aboutSection: {
    alignItems: 'center',
    padding: Spacing.xl,
    paddingBottom: Spacing.xl,
  },
  aboutText: {
    fontSize: FontSize.caption,
    textAlign: 'center',
    marginBottom: 4,
  },
});
