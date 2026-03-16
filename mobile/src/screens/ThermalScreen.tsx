/**
 * ThermalScreen.tsx — Pantalla de cámara térmica USB-C (themed)
 *
 * Features:
 * - Detección automática de cámara térmica USB-C
 * - Stream en tiempo real con paleta configurable
 * - Captura de frame + análisis por Seedy
 * - Indicadores min/max/avg temperatura
 * - Detección de fiebre/hipotermia por especie
 * - Fallback: instrucciones si no hay cámara conectada
 * - Open WebUI themed via useTheme()
 */

import React, { useState, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ScrollView,
  Image,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';

import {
  useThermalCamera,
  ThermalPalette,
} from '../hooks/useThermalCamera';
import { analyzeThermal, ThermalAnalysis } from '../api/seedyClient';
import { useTheme } from '../theme/ThemeContext';
import { Spacing, FontSize, ANIMAL_TEMP_RANGES } from '../theme/themes';

const PALETTES: Array<{ key: ThermalPalette; label: string; colors: string[] }> = [
  { key: 'iron', label: 'Hierro', colors: ['#000033', '#FF6600', '#FFFF00'] },
  { key: 'rainbow', label: 'Arcoíris', colors: ['#0000FF', '#00FF00', '#FF0000'] },
  { key: 'whitehot', label: 'Blanco', colors: ['#000000', '#888888', '#FFFFFF'] },
  { key: 'lava', label: 'Lava', colors: ['#1A0000', '#FF3300', '#FFCC00'] },
];

type ActiveSpecies = 'poultry' | 'pig' | 'cattle';

export function ThermalScreen() {
  const { theme } = useTheme();
  const thermal = useThermalCamera();
  const [activeSpecies, setActiveSpecies] = useState<ActiveSpecies>('poultry');
  const [analyzing, setAnalyzing] = useState(false);
  const [analysis, setAnalysis] = useState<ThermalAnalysis | null>(null);

  // ── Capturar y analizar ────────────────────────────────────────────
  const handleCapture = useCallback(async () => {
    const frame = await thermal.captureFrame();
    if (!frame) {
      Alert.alert('Error', 'No se pudo capturar el frame térmico');
      return;
    }

    setAnalyzing(true);
    setAnalysis(null);

    try {
      const result = await analyzeThermal(
        frame.imageBase64,
        frame.radiometricData?.flat(),
      );
      setAnalysis(result);
    } catch (err: any) {
      Alert.alert('Error', err.message || 'Error al analizar imagen térmica');
    } finally {
      setAnalyzing(false);
    }
  }, [thermal]);

  // ── Evaluar temperatura vs rangos normales ─────────────────────────
  const evaluateTemp = (temp: number): { status: string; color: string } => {
    const range = ANIMAL_TEMP_RANGES[activeSpecies];
    if (temp >= range.fever) return { status: '🔴 FIEBRE', color: theme.error };
    if (temp <= range.hypo) return { status: '🔵 HIPOTERMIA', color: theme.info };
    if (temp >= range.normal.min && temp <= range.normal.max) {
      return { status: '🟢 Normal', color: theme.success };
    }
    return { status: '🟡 Revisar', color: theme.warning };
  };

  // ── Sin cámara conectada ───────────────────────────────────────────
  if (!thermal.isConnected) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: theme.bg1 }]}>
        <ScrollView contentContainerStyle={styles.noDeviceContainer}>
          <MaterialCommunityIcons
            name="thermometer-alert"
            size={80}
            color={theme.textMuted}
          />
          <Text style={[styles.noDeviceTitle, { color: theme.text }]}>
            Cámara Térmica USB-C
          </Text>
          <Text style={[styles.noDeviceText, { color: theme.textSecondary }]}>
            Conecta tu cámara térmica por USB-C para empezar a medir
            temperaturas corporales de los animales.
          </Text>

          {/* Cámaras compatibles */}
          <View style={[styles.compatCard, { backgroundColor: theme.bg2, borderColor: theme.border }]}>
            <Text style={[styles.compatTitle, { color: theme.text }]}>
              Cámaras compatibles
            </Text>

            {[
              { name: 'InfiRay P2 Pro (9mm)', spec: '256×192 · TISR 384×288 · ±0.5°C · USB-C', ok: true },
              { name: 'InfiRay T2S+ / T3S', spec: '256×192 · 25Hz · Radiométrica · USB-C', ok: true },
              { name: 'FLIR One Pro / Edge', spec: '160×120 · MSX · ±3°C · USB-C', ok: true },
              { name: 'Seek Thermal CompactPRO', spec: '320×240 · 15Hz · USB-C', ok: false },
            ].map((cam) => (
              <View key={cam.name} style={styles.compatItem}>
                <MaterialCommunityIcons
                  name={cam.ok ? 'check-circle' : 'check-circle-outline'}
                  size={18}
                  color={cam.ok ? theme.success : theme.textMuted}
                />
                <View style={styles.compatTextWrap}>
                  <Text style={[styles.compatName, { color: theme.text }]}>
                    {cam.name}
                  </Text>
                  <Text style={[styles.compatSpec, { color: theme.textSecondary }]}>
                    {cam.spec}
                  </Text>
                </View>
              </View>
            ))}
          </View>

          {/* Rangos de temperatura */}
          <View style={[styles.rangesCard, { backgroundColor: theme.bg2, borderColor: theme.border }]}>
            <Text style={[styles.compatTitle, { color: theme.text }]}>
              Temperaturas normales
            </Text>
            {(Object.entries(ANIMAL_TEMP_RANGES) as [ActiveSpecies, any][]).map(
              ([species, range]) => (
                <View key={species} style={[styles.rangeRow, { borderBottomColor: theme.divider }]}>
                  <Text style={[styles.rangeName, { color: theme.text }]}>
                    {species === 'poultry' ? '🐔 Aves' :
                     species === 'pig' ? '🐷 Porcino' : '🐄 Vacuno'}
                  </Text>
                  <Text style={[styles.rangeValue, { color: theme.primary }]}>
                    {range.normal.min}–{range.normal.max}°C
                  </Text>
                  <Text style={[styles.rangeFever, { color: theme.error }]}>
                    Fiebre: ≥{range.fever}°C
                  </Text>
                </View>
              ),
            )}
          </View>

          {thermal.error && (
            <Text style={[styles.errorText, { color: theme.error }]}>
              {thermal.error}
            </Text>
          )}
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── Con cámara conectada ───────────────────────────────────────────
  return (
    <SafeAreaView style={[styles.container, { backgroundColor: theme.bg1 }]}>
      <ScrollView>
        {/* Device info */}
        <View style={[styles.deviceBar, { backgroundColor: theme.bg2, borderBottomColor: theme.border }]}>
          <MaterialCommunityIcons name="usb" size={18} color={theme.success} />
          <Text style={[styles.deviceName, { color: theme.text }]}>
            {thermal.device?.name} ({thermal.device?.resolution})
          </Text>
          <View style={[styles.connectedBadge, { backgroundColor: theme.success + '20' }]}>
            <Text style={[styles.connectedText, { color: theme.success }]}>
              Conectada
            </Text>
          </View>
        </View>

        {/* Selector de especie */}
        <View style={styles.speciesRow}>
          {(['poultry', 'pig', 'cattle'] as ActiveSpecies[]).map((sp) => (
            <TouchableOpacity
              key={sp}
              style={[
                styles.speciesChip,
                { backgroundColor: theme.bg3, borderColor: theme.border, borderWidth: 1 },
                activeSpecies === sp && { backgroundColor: theme.primary, borderColor: theme.primary },
              ]}
              onPress={() => setActiveSpecies(sp)}
            >
              <Text
                style={[
                  styles.speciesChipText,
                  { color: theme.text },
                  activeSpecies === sp && { color: theme.textInverse },
                ]}
              >
                {sp === 'poultry' ? '🐔 Aves' :
                 sp === 'pig' ? '🐷 Porcino' : '🐄 Vacuno'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Thermal preview */}
        <View style={styles.thermalPreview}>
          {thermal.lastFrame ? (
            <>
              <Image
                source={{
                  uri: `data:image/jpeg;base64,${thermal.lastFrame.imageBase64}`,
                }}
                style={styles.thermalImage}
                resizeMode="contain"
              />
              {/* Overlay min/max */}
              <View style={styles.tempOverlay}>
                <View style={styles.tempBadge}>
                  <Text style={[styles.tempValue, { color: theme.thermalCold }]}>
                    ↓ {thermal.lastFrame.minTemp.toFixed(1)}°C
                  </Text>
                </View>
                <View style={styles.tempBadge}>
                  <Text style={styles.tempValue}>
                    ⊘ {thermal.lastFrame.avgTemp.toFixed(1)}°C
                  </Text>
                </View>
                <View style={styles.tempBadge}>
                  <Text style={[styles.tempValue, { color: theme.thermalHot }]}>
                    ↑ {thermal.lastFrame.maxTemp.toFixed(1)}°C
                  </Text>
                </View>
              </View>

              {/* Estado según especie */}
              {(() => {
                const eval_ = evaluateTemp(thermal.lastFrame.hotspot.temp);
                return (
                  <View
                    style={[
                      styles.statusBanner,
                      { backgroundColor: eval_.color + '20' },
                    ]}
                  >
                    <Text style={[styles.statusText, { color: eval_.color }]}>
                      {eval_.status} — Punto más caliente:{' '}
                      {thermal.lastFrame.hotspot.temp.toFixed(1)}°C
                    </Text>
                  </View>
                );
              })()}
            </>
          ) : (
            <View style={styles.noFrameContainer}>
              <MaterialCommunityIcons
                name="camera-iris"
                size={48}
                color={theme.textMuted}
              />
              <Text style={[styles.noFrameText, { color: theme.textMuted }]}>
                Pulsa "Iniciar" para ver el stream térmico
              </Text>
            </View>
          )}
        </View>

        {/* Palette selector */}
        <View style={styles.paletteRow}>
          {PALETTES.map((p) => (
            <TouchableOpacity
              key={p.key}
              style={[
                styles.paletteChip,
                { backgroundColor: theme.bg3 },
                thermal.config.palette === p.key && {
                  backgroundColor: theme.primarySurface,
                  borderWidth: 2,
                  borderColor: theme.primary,
                },
              ]}
              onPress={() => thermal.setPalette(p.key)}
            >
              <View style={styles.palettePreview}>
                {p.colors.map((c, i) => (
                  <View
                    key={i}
                    style={[styles.paletteSwatch, { backgroundColor: c }]}
                  />
                ))}
              </View>
              <Text style={[styles.paletteLabel, { color: theme.text }]}>
                {p.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Control buttons */}
        <View style={styles.controlRow}>
          <TouchableOpacity
            style={[
              styles.controlButton,
              { backgroundColor: thermal.isStreaming ? theme.error : theme.primary },
            ]}
            onPress={thermal.isStreaming ? thermal.stopStream : thermal.startStream}
          >
            <Ionicons
              name={thermal.isStreaming ? 'stop' : 'play'}
              size={24}
              color="#FFF"
            />
            <Text style={styles.controlButtonText}>
              {thermal.isStreaming ? 'Detener' : 'Iniciar'}
            </Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={[styles.controlButton, { backgroundColor: theme.accent }]}
            onPress={handleCapture}
            disabled={analyzing}
          >
            {analyzing ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <>
                <Ionicons name="scan" size={24} color="#FFF" />
                <Text style={styles.controlButtonText}>Analizar</Text>
              </>
            )}
          </TouchableOpacity>
        </View>

        {/* Resultado del análisis */}
        {analysis && (
          <View style={[styles.analysisCard, { backgroundColor: theme.bg2, borderColor: theme.border }]}>
            <Text style={[styles.analysisTitle, { color: theme.text }]}>
              <MaterialCommunityIcons
                name="thermometer-check"
                size={18}
                color={theme.primary}
              />{' '}
              Análisis Térmico
            </Text>

            <View style={styles.tempGrid}>
              <View style={styles.tempGridItem}>
                <Text style={[styles.tempGridLabel, { color: theme.textSecondary }]}>
                  Mín
                </Text>
                <Text style={[styles.tempGridValue, { color: theme.text }]}>
                  {analysis.min_temp_c.toFixed(1)}°C
                </Text>
              </View>
              <View style={styles.tempGridItem}>
                <Text style={[styles.tempGridLabel, { color: theme.textSecondary }]}>
                  Media
                </Text>
                <Text style={[styles.tempGridValue, { color: theme.text }]}>
                  {analysis.avg_temp_c.toFixed(1)}°C
                </Text>
              </View>
              <View style={styles.tempGridItem}>
                <Text style={[styles.tempGridLabel, { color: theme.textSecondary }]}>
                  Máx
                </Text>
                <Text style={[styles.tempGridValue, { color: theme.text }]}>
                  {analysis.max_temp_c.toFixed(1)}°C
                </Text>
              </View>
            </View>

            {analysis.animal_temps.length > 0 && (
              <View style={styles.animalTemps}>
                <Text style={[styles.subTitle, { color: theme.text }]}>
                  Animales detectados
                </Text>
                {analysis.animal_temps.map((a) => {
                  const eval_ = evaluateTemp(a.body_temp_c);
                  return (
                    <View key={a.id} style={[styles.animalTempRow, { borderBottomColor: theme.divider }]}>
                      <Text style={[styles.animalId, { color: theme.text }]}>
                        Animal #{a.id}
                      </Text>
                      <Text
                        style={[
                          styles.animalTempValue,
                          { color: eval_.color },
                        ]}
                      >
                        {a.body_temp_c.toFixed(1)}°C {eval_.status}
                      </Text>
                    </View>
                  );
                })}
              </View>
            )}

            {analysis.alerts.length > 0 && (
              <View style={[styles.alertsSection, { backgroundColor: theme.warning + '15' }]}>
                {analysis.alerts.map((alert, i) => (
                  <View key={i} style={styles.alertRow}>
                    <Ionicons name="warning" size={16} color={theme.warning} />
                    <Text style={[styles.alertText, { color: theme.text }]}>
                      {alert}
                    </Text>
                  </View>
                ))}
              </View>
            )}

            <Text style={[styles.analysisDescription, { color: theme.textSecondary }]}>
              {analysis.description}
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },

  // Device bar
  deviceBar: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: Spacing.md,
    borderBottomWidth: 1,
    gap: Spacing.sm,
  },
  deviceName: {
    flex: 1,
    fontSize: FontSize.body,
    fontWeight: '500',
  },
  connectedBadge: {
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: 8,
  },
  connectedText: {
    fontSize: FontSize.caption,
    fontWeight: '600',
  },

  // Species row
  speciesRow: {
    flexDirection: 'row',
    padding: Spacing.md,
    gap: Spacing.sm,
    justifyContent: 'center',
  },
  speciesChip: {
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: 16,
  },
  speciesChipText: {
    fontSize: FontSize.body,
    fontWeight: '500',
  },

  // Thermal preview
  thermalPreview: {
    marginHorizontal: Spacing.md,
    backgroundColor: '#000',
    borderRadius: 16,
    overflow: 'hidden',
    minHeight: 260,
  },
  thermalImage: {
    width: '100%',
    height: 260,
  },
  tempOverlay: {
    position: 'absolute',
    bottom: 8,
    left: 8,
    right: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  tempBadge: {
    backgroundColor: 'rgba(0,0,0,0.7)',
    paddingHorizontal: Spacing.sm,
    paddingVertical: 2,
    borderRadius: 8,
  },
  tempValue: {
    color: '#FFF',
    fontSize: FontSize.caption,
    fontWeight: '700',
    fontFamily: 'monospace',
  },
  statusBanner: {
    padding: Spacing.sm,
    alignItems: 'center',
  },
  statusText: {
    fontSize: FontSize.body,
    fontWeight: '600',
  },
  noFrameContainer: {
    height: 260,
    justifyContent: 'center',
    alignItems: 'center',
  },
  noFrameText: {
    marginTop: Spacing.sm,
    fontSize: FontSize.body,
  },

  // Palette
  paletteRow: {
    flexDirection: 'row',
    padding: Spacing.md,
    gap: Spacing.sm,
    justifyContent: 'center',
  },
  paletteChip: {
    alignItems: 'center',
    padding: Spacing.sm,
    borderRadius: 12,
    minWidth: 70,
  },
  palettePreview: {
    flexDirection: 'row',
    height: 16,
    borderRadius: 4,
    overflow: 'hidden',
    marginBottom: 4,
  },
  paletteSwatch: {
    width: 18,
    height: 16,
  },
  paletteLabel: {
    fontSize: FontSize.caption,
  },

  // Controls
  controlRow: {
    flexDirection: 'row',
    padding: Spacing.md,
    gap: Spacing.md,
  },
  controlButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: Spacing.md,
    borderRadius: 12,
    gap: Spacing.sm,
  },
  controlButtonText: {
    color: '#FFF',
    fontSize: FontSize.bodyLarge,
    fontWeight: '600',
  },

  // Analysis
  analysisCard: {
    margin: Spacing.md,
    padding: Spacing.lg,
    borderRadius: 16,
    borderWidth: 1,
  },
  analysisTitle: {
    fontSize: FontSize.title,
    fontWeight: '700',
    marginBottom: Spacing.md,
  },
  tempGrid: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    marginBottom: Spacing.lg,
  },
  tempGridItem: {
    alignItems: 'center',
  },
  tempGridLabel: {
    fontSize: FontSize.caption,
  },
  tempGridValue: {
    fontSize: FontSize.titleLarge,
    fontWeight: '700',
    fontFamily: 'monospace',
  },
  subTitle: {
    fontSize: FontSize.bodyLarge,
    fontWeight: '600',
    marginBottom: Spacing.sm,
  },
  animalTemps: {
    marginBottom: Spacing.lg,
  },
  animalTempRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: Spacing.xs,
    borderBottomWidth: 1,
  },
  animalId: {
    fontSize: FontSize.body,
  },
  animalTempValue: {
    fontSize: FontSize.body,
    fontWeight: '600',
    fontFamily: 'monospace',
  },
  alertsSection: {
    borderRadius: 12,
    padding: Spacing.md,
    marginBottom: Spacing.md,
  },
  alertRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.sm,
    marginBottom: Spacing.xs,
  },
  alertText: {
    fontSize: FontSize.body,
    flex: 1,
  },
  analysisDescription: {
    fontSize: FontSize.body,
    lineHeight: 22,
  },

  // No device
  noDeviceContainer: {
    alignItems: 'center',
    padding: Spacing.xl,
    paddingTop: 60,
  },
  noDeviceTitle: {
    fontSize: FontSize.titleLarge,
    fontWeight: '700',
    marginTop: Spacing.lg,
  },
  noDeviceText: {
    fontSize: FontSize.body,
    textAlign: 'center',
    marginVertical: Spacing.md,
    lineHeight: 22,
  },
  compatCard: {
    width: '100%',
    borderRadius: 16,
    padding: Spacing.lg,
    marginTop: Spacing.lg,
    borderWidth: 1,
  },
  compatTitle: {
    fontSize: FontSize.bodyLarge,
    fontWeight: '600',
    marginBottom: Spacing.md,
  },
  compatItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: Spacing.sm,
    marginBottom: Spacing.md,
  },
  compatTextWrap: {
    flex: 1,
  },
  compatName: {
    fontSize: FontSize.body,
    fontWeight: '600',
  },
  compatSpec: {
    fontSize: FontSize.caption,
    marginTop: 2,
  },

  // Ranges card
  rangesCard: {
    width: '100%',
    borderRadius: 16,
    padding: Spacing.lg,
    marginTop: Spacing.md,
    borderWidth: 1,
  },
  rangeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: Spacing.sm,
    borderBottomWidth: 1,
  },
  rangeName: {
    fontSize: FontSize.body,
    flex: 1,
  },
  rangeValue: {
    fontSize: FontSize.body,
    fontWeight: '600',
    flex: 1,
    textAlign: 'center',
    fontFamily: 'monospace',
  },
  rangeFever: {
    fontSize: FontSize.caption,
    flex: 1,
    textAlign: 'right',
  },
  errorText: {
    marginTop: Spacing.md,
    fontSize: FontSize.body,
  },
});
