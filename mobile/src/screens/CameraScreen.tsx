/**
 * CameraScreen.tsx — Visión animal (Open WebUI style)
 *
 * - Dark themed camera overlay
 * - Species selector pills
 * - Clean results card with themed colors
 */

import React, { useState, useRef, useCallback } from 'react';
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
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';

import { analyzeImage, VisionAnalysis } from '../api/seedyClient';
import { useTheme } from '../theme/ThemeContext';
import { Spacing, FontSize, Radius } from '../theme/themes';

type Species = 'poultry' | 'pig' | 'cattle' | null;

interface AnalysisResult {
  image: string;
  analysis: VisionAnalysis;
  timestamp: number;
}

export function CameraScreen() {
  const { theme } = useTheme();
  const [permission, requestPermission] = useCameraPermissions();
  const [selectedSpecies, setSelectedSpecies] = useState<Species>(null);
  const [capturedImage, setCapturedImage] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [showCamera, setShowCamera] = useState(true);
  const cameraRef = useRef<CameraView>(null);

  const SPECIES_OPTIONS: Array<{
    key: Species;
    label: string;
    icon: string;
    isMCI: boolean;
    color: string;
  }> = [
    { key: null, label: 'Auto', icon: 'scan-outline', isMCI: false, color: theme.primary },
    { key: 'poultry', label: 'Aves', icon: 'egg-outline', isMCI: true, color: theme.speciesPoultry },
    { key: 'pig', label: 'Porcino', icon: 'pig-variant', isMCI: true, color: theme.speciesPig },
    { key: 'cattle', label: 'Vacuno', icon: 'cow', isMCI: true, color: theme.speciesCattle },
  ];

  const handleCapture = useCallback(async () => {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: 0.85,
        base64: true,
        exif: true,
      });
      if (photo?.base64) {
        setCapturedImage(photo.base64);
        setShowCamera(false);
        doAnalyze(photo.base64);
      }
    } catch {
      Alert.alert('Error', 'No se pudo capturar la foto');
    }
  }, [selectedSpecies]);

  const handleGallery = useCallback(async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permiso denegado', 'Necesitamos acceso a la galería');
      return;
    }
    const pickerResult = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
      base64: true,
    });
    if (!pickerResult.canceled && pickerResult.assets[0]?.base64) {
      const base64 = pickerResult.assets[0].base64;
      setCapturedImage(base64);
      setShowCamera(false);
      doAnalyze(base64);
    }
  }, [selectedSpecies]);

  const doAnalyze = useCallback(async (imageBase64: string) => {
    setAnalyzing(true);
    setResult(null);
    try {
      const analysis = await analyzeImage(imageBase64, selectedSpecies || undefined);
      setResult({ image: imageBase64, analysis, timestamp: Date.now() });
    } catch (err: any) {
      Alert.alert('Error', err.message || 'No se pudo analizar la imagen');
    } finally {
      setAnalyzing(false);
    }
  }, [selectedSpecies]);

  const resetToCamera = useCallback(() => {
    setCapturedImage(null);
    setResult(null);
    setShowCamera(true);
  }, []);

  // ── Permiso ──────────────────────────────────────────────────────
  if (!permission) return <View style={[styles.container, { backgroundColor: theme.bg0 }]} />;

  if (!permission.granted) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: theme.bg1 }]}>
        <View style={styles.permissionContainer}>
          <Ionicons name="camera-outline" size={64} color={theme.textMuted} />
          <Text style={[styles.permissionText, { color: theme.textSecondary }]}>
            Seedy necesita acceso a la cámara para identificar animales
          </Text>
          <TouchableOpacity
            style={[styles.permissionButton, { backgroundColor: theme.primary }]}
            onPress={requestPermission}
          >
            <Text style={styles.permissionButtonText}>Permitir cámara</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  // ── Resultados ──────────────────────────────────────────────────
  if (!showCamera && capturedImage) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: theme.bg1 }]}>
        <ScrollView contentContainerStyle={styles.resultScroll}>
          <Image
            source={{ uri: `data:image/jpeg;base64,${capturedImage}` }}
            style={[styles.resultImage, { borderColor: theme.border }]}
            resizeMode="cover"
          />

          {analyzing && (
            <View style={styles.analyzingContainer}>
              <ActivityIndicator size="large" color={theme.primary} />
              <Text style={[styles.analyzingText, { color: theme.textSecondary }]}>
                Analizando con Seedy Vision...
              </Text>
            </View>
          )}

          {result && (
            <View style={[styles.resultCard, { backgroundColor: theme.bg2, borderColor: theme.border }]}>
              <View style={styles.resultHeader}>
                <View style={[styles.speciesBadge, { backgroundColor: theme.primarySurface }]}>
                  <Text style={[styles.speciesBadgeText, { color: theme.primary }]}>
                    {result.analysis.species.toUpperCase()}
                  </Text>
                </View>
                <Text style={[styles.breedText, { color: theme.text }]}>
                  {result.analysis.breed}
                </Text>
                <Text style={[styles.confidenceText, { color: theme.textSecondary }]}>
                  {(result.analysis.confidence * 100).toFixed(0)}% confianza
                </Text>
              </View>

              <View style={styles.detailsGrid}>
                <DetailItem
                  icon="fitness-outline"
                  label="Condición corporal"
                  value={result.analysis.body_condition}
                  theme={theme}
                />
                {result.analysis.estimated_weight_kg && (
                  <DetailItem
                    icon="scale-outline"
                    label="Peso estimado"
                    value={`${result.analysis.estimated_weight_kg} kg`}
                    theme={theme}
                  />
                )}
              </View>

              {result.analysis.health_notes.length > 0 && (
                <View style={[styles.healthSection, { backgroundColor: theme.warning + '15' }]}>
                  <Text style={[styles.sectionTitle, { color: theme.text }]}>
                    <Ionicons name="medkit" size={16} color={theme.warning} />
                    {' '}Observaciones sanitarias
                  </Text>
                  {result.analysis.health_notes.map((note, i) => (
                    <Text key={i} style={[styles.healthNote, { color: theme.text }]}>
                      • {note}
                    </Text>
                  ))}
                </View>
              )}

              <View style={[styles.descriptionSection, { borderTopColor: theme.divider }]}>
                <Text style={[styles.sectionTitle, { color: theme.text }]}>
                  Análisis completo
                </Text>
                <Text style={[styles.descriptionText, { color: theme.textSecondary }]}>
                  {result.analysis.description}
                </Text>
              </View>
            </View>
          )}

          <TouchableOpacity
            style={[styles.newPhotoButton, { backgroundColor: theme.primary }]}
            onPress={resetToCamera}
          >
            <Ionicons name="camera" size={20} color="#FFF" />
            <Text style={styles.newPhotoText}> Nueva foto</Text>
          </TouchableOpacity>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // ── Camera view ──────────────────────────────────────────────────
  return (
    <View style={styles.container}>
      <CameraView ref={cameraRef} style={styles.camera} facing="back">
        {/* Species */}
        <SafeAreaView edges={['top']}>
          <View style={styles.speciesSelector}>
            {SPECIES_OPTIONS.map((opt) => {
              const active = selectedSpecies === opt.key;
              return (
                <TouchableOpacity
                  key={opt.label}
                  style={[
                    styles.speciesButton,
                    {
                      backgroundColor: active
                        ? opt.color
                        : 'rgba(0,0,0,0.6)',
                      borderColor: active ? opt.color : 'rgba(255,255,255,0.2)',
                    },
                  ]}
                  onPress={() => setSelectedSpecies(opt.key)}
                >
                  {opt.isMCI ? (
                    <MaterialCommunityIcons
                      name={opt.icon as any}
                      size={18}
                      color={active ? '#FFF' : opt.color}
                    />
                  ) : (
                    <Ionicons
                      name={opt.icon as any}
                      size={18}
                      color={active ? '#FFF' : opt.color}
                    />
                  )}
                  <Text
                    style={[
                      styles.speciesLabel,
                      { color: active ? '#FFF' : 'rgba(255,255,255,0.8)' },
                    ]}
                  >
                    {opt.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>
        </SafeAreaView>

        {/* Viewfinder */}
        <View style={styles.viewfinder}>
          <View style={[styles.cornerTL, { borderColor: theme.primary }]} />
          <View style={[styles.cornerTR, { borderColor: theme.primary }]} />
          <View style={[styles.cornerBL, { borderColor: theme.primary }]} />
          <View style={[styles.cornerBR, { borderColor: theme.primary }]} />
        </View>

        {/* Bottom bar */}
        <View style={styles.cameraBottomBar}>
          <TouchableOpacity style={styles.galleryButton} onPress={handleGallery}>
            <Ionicons name="images" size={28} color="#FFF" />
          </TouchableOpacity>
          <TouchableOpacity style={styles.captureButton} onPress={handleCapture}>
            <View style={styles.captureInner} />
          </TouchableOpacity>
          <View style={styles.galleryButton} />
        </View>
      </CameraView>
    </View>
  );
}

function DetailItem({ icon, label, value, theme }: any) {
  return (
    <View style={styles.detailItem}>
      <Ionicons name={icon} size={20} color={theme.primary} />
      <View style={styles.detailTextContainer}>
        <Text style={[styles.detailLabel, { color: theme.textSecondary }]}>{label}</Text>
        <Text style={[styles.detailValue, { color: theme.text }]}>{value}</Text>
      </View>
    </View>
  );
}

const CS = 30;
const CW = 3;
const cornerBase = { position: 'absolute' as const, width: CS, height: CS };

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  camera: { flex: 1, justifyContent: 'space-between' },

  speciesSelector: {
    flexDirection: 'row',
    justifyContent: 'center',
    paddingTop: Spacing.sm,
    paddingHorizontal: Spacing.md,
    gap: Spacing.sm,
  },
  speciesButton: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.sm,
    borderRadius: Radius.full,
    borderWidth: 1,
    gap: Spacing.xs,
  },
  speciesLabel: {
    fontSize: FontSize.caption,
    fontWeight: '600',
  },

  viewfinder: { width: 280, height: 280, alignSelf: 'center' },
  cornerTL: { ...cornerBase, top: 0, left: 0, borderTopWidth: CW, borderLeftWidth: CW },
  cornerTR: { ...cornerBase, top: 0, right: 0, borderTopWidth: CW, borderRightWidth: CW },
  cornerBL: { ...cornerBase, bottom: 0, left: 0, borderBottomWidth: CW, borderLeftWidth: CW },
  cornerBR: { ...cornerBase, bottom: 0, right: 0, borderBottomWidth: CW, borderRightWidth: CW },

  cameraBottomBar: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    alignItems: 'center',
    paddingBottom: 40,
    paddingHorizontal: Spacing.xl,
  },
  galleryButton: { width: 44, height: 44, borderRadius: 22, justifyContent: 'center', alignItems: 'center' },
  captureButton: {
    width: 72, height: 72, borderRadius: 36,
    backgroundColor: 'rgba(255,255,255,0.3)',
    justifyContent: 'center', alignItems: 'center',
    borderWidth: 3, borderColor: '#FFF',
  },
  captureInner: { width: 58, height: 58, borderRadius: 29, backgroundColor: '#FFF' },

  permissionContainer: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: Spacing.xl },
  permissionText: { fontSize: FontSize.bodyLarge, textAlign: 'center', marginVertical: Spacing.lg },
  permissionButton: { paddingHorizontal: Spacing.xl, paddingVertical: Spacing.md, borderRadius: Radius.md },
  permissionButtonText: { color: '#FFF', fontSize: FontSize.bodyLarge, fontWeight: '600' },

  resultScroll: { padding: Spacing.md, paddingBottom: 40 },
  resultImage: { width: '100%', height: 300, borderRadius: Radius.lg, marginBottom: Spacing.md, borderWidth: 1 },
  analyzingContainer: { alignItems: 'center', paddingVertical: Spacing.xl },
  analyzingText: { marginTop: Spacing.md, fontSize: FontSize.body },

  resultCard: { borderRadius: Radius.lg, padding: Spacing.lg, marginBottom: Spacing.md, borderWidth: 1 },
  resultHeader: { alignItems: 'center', marginBottom: Spacing.lg },
  speciesBadge: { paddingHorizontal: Spacing.md, paddingVertical: Spacing.xs, borderRadius: Radius.sm, marginBottom: Spacing.sm },
  speciesBadgeText: { fontSize: FontSize.caption, fontWeight: '700', letterSpacing: 1 },
  breedText: { fontSize: FontSize.titleLarge, fontWeight: '700' },
  confidenceText: { fontSize: FontSize.caption, marginTop: Spacing.xs },
  detailsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: Spacing.md, marginBottom: Spacing.lg },
  detailItem: { flexDirection: 'row', alignItems: 'center', flex: 1, minWidth: '45%', gap: Spacing.sm },
  detailTextContainer: { flex: 1 },
  detailLabel: { fontSize: FontSize.caption },
  detailValue: { fontSize: FontSize.body, fontWeight: '600' },
  healthSection: { marginBottom: Spacing.lg, padding: Spacing.md, borderRadius: Radius.md },
  sectionTitle: { fontSize: FontSize.bodyLarge, fontWeight: '600', marginBottom: Spacing.sm },
  healthNote: { fontSize: FontSize.body, marginLeft: Spacing.sm, marginBottom: Spacing.xs },
  descriptionSection: { borderTopWidth: 1, paddingTop: Spacing.md },
  descriptionText: { fontSize: FontSize.body, lineHeight: 22 },
  newPhotoButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    paddingVertical: Spacing.md, borderRadius: Radius.md, marginBottom: Spacing.xl,
  },
  newPhotoText: { color: '#FFF', fontSize: FontSize.bodyLarge, fontWeight: '600' },
});
