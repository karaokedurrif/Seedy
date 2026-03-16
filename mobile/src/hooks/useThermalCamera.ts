/**
 * useThermalCamera.ts — Hook para cámaras térmicas USB-C
 *
 * Soporta cámaras UVC térmicas profesionales conectadas por USB-C:
 *   - InfiRay P2 Pro / T2S+ (9mm, 256×192 TISR)
 *   - FLIR One Pro / Edge Pro
 *   - Seek Thermal CompactPRO
 *   - Cualquier cámara UVC compatible
 *
 * Protocolo:
 *   1. Detectar dispositivo USB-C via Android USB Host API
 *   2. Abrir stream UVC (video/x-raw o MJPEG)
 *   3. Capturar frames radiométricos (si disponible)
 *   4. Convertir a imagen visible + mapa de temperaturas
 *
 * Nota: La integración real requiere un módulo nativo Android.
 * Este hook define la interfaz y fallback a cámara normal.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { NativeModules, NativeEventEmitter, Platform, Alert } from 'react-native';

// ── Types ───────────────────────────────────────────────────────────────
export interface ThermalFrame {
  /** Imagen visible (JPEG base64) con paleta térmica aplicada */
  imageBase64: string;
  /** Ancho del frame en píxeles */
  width: number;
  /** Alto del frame en píxeles */
  height: number;
  /** Temperatura mínima en °C del frame */
  minTemp: number;
  /** Temperatura máxima en °C del frame */
  maxTemp: number;
  /** Temperatura media en °C */
  avgTemp: number;
  /** Punto más caliente */
  hotspot: { x: number; y: number; temp: number };
  /** Punto más frío */
  coldspot: { x: number; y: number; temp: number };
  /** Timestamp del frame */
  timestamp: number;
  /** Datos radiométricos raw (opcional, matrix de temps en °C) */
  radiometricData?: number[][];
}

export interface ThermalDevice {
  name: string;
  vendorId: number;
  productId: number;
  resolution: string;
  connected: boolean;
}

export type ThermalPalette =
  | 'iron'        // Escala de hierro (default industrial)
  | 'rainbow'     // Arco iris (máximo contraste)
  | 'whitehot'    // Blanco = caliente
  | 'blackhot'    // Negro = caliente
  | 'lava'        // Lava (veterinario)
  | 'arctic';     // Ártico (frío)

export interface ThermalConfig {
  palette: ThermalPalette;
  minRange: number;    // °C mínimo del rango (auto si null)
  maxRange: number;    // °C máximo del rango
  emissivity: number;  // 0.0-1.0 (animales ≈ 0.95-0.98)
  showCrosshair: boolean;
  showMinMax: boolean;
}

interface UseThermalCameraReturn {
  /** Si hay una cámara térmica USB-C conectada */
  isConnected: boolean;
  /** Info del dispositivo detectado */
  device: ThermalDevice | null;
  /** Si el stream está activo */
  isStreaming: boolean;
  /** Último frame capturado */
  lastFrame: ThermalFrame | null;
  /** Configuración actual */
  config: ThermalConfig;
  /** Error actual */
  error: string | null;
  /** Iniciar stream de la cámara */
  startStream: () => Promise<void>;
  /** Detener stream */
  stopStream: () => void;
  /** Capturar un frame estático */
  captureFrame: () => Promise<ThermalFrame | null>;
  /** Cambiar paleta de colores */
  setPalette: (palette: ThermalPalette) => void;
  /** Ajustar rango de temperatura */
  setRange: (min: number, max: number) => void;
  /** Cambiar emisividad (animales ≈ 0.95) */
  setEmissivity: (value: number) => void;
}

// ── Default config para animales de granja ──────────────────────────────
const DEFAULT_CONFIG: ThermalConfig = {
  palette: 'iron',
  minRange: 15,      // 15°C mínimo (ambiental)
  maxRange: 42,      // 42°C máximo (fiebre animal)
  emissivity: 0.95,  // Piel/pluma de animal
  showCrosshair: true,
  showMinMax: true,
};

// ── Rangos normales de temperatura corporal por especie ──────────────────
export const ANIMAL_TEMP_RANGES = {
  poultry: { normal: { min: 40.6, max: 41.7 }, fever: 42.0, hypo: 39.5 },
  pig:     { normal: { min: 38.0, max: 39.5 }, fever: 40.0, hypo: 37.0 },
  cattle:  { normal: { min: 38.0, max: 39.5 }, fever: 39.5, hypo: 36.5 },
} as const;

// ── Hook ────────────────────────────────────────────────────────────────
export function useThermalCamera(): UseThermalCameraReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [device, setDevice] = useState<ThermalDevice | null>(null);
  const [isStreaming, setIsStreaming] = useState(false);
  const [lastFrame, setLastFrame] = useState<ThermalFrame | null>(null);
  const [config, setConfig] = useState<ThermalConfig>(DEFAULT_CONFIG);
  const [error, setError] = useState<string | null>(null);
  const streamRef = useRef<any>(null);

  // ── Detectar cámara USB-C ───────────────────────────────────────────
  useEffect(() => {
    if (Platform.OS !== 'android') {
      setError('Cámara térmica USB-C solo disponible en Android');
      return;
    }

    const ThermalModule = NativeModules.ThermalCamera;
    if (!ThermalModule) {
      // Módulo nativo no compilado — modo simulación
      setError(null);
      setIsConnected(false);
      return;
    }

    // Listener de conexión USB
    const emitter = new NativeEventEmitter(ThermalModule);

    const connectSub = emitter.addListener('onThermalDeviceConnected', (dev) => {
      setDevice({
        name: dev.name || 'Thermal Camera',
        vendorId: dev.vendorId,
        productId: dev.productId,
        resolution: dev.resolution || '256x192',
        connected: true,
      });
      setIsConnected(true);
      setError(null);
    });

    const disconnectSub = emitter.addListener('onThermalDeviceDisconnected', () => {
      setDevice(null);
      setIsConnected(false);
      setIsStreaming(false);
    });

    const frameSub = emitter.addListener('onThermalFrame', (frame) => {
      setLastFrame({
        imageBase64: frame.imageBase64,
        width: frame.width,
        height: frame.height,
        minTemp: frame.minTemp,
        maxTemp: frame.maxTemp,
        avgTemp: frame.avgTemp,
        hotspot: frame.hotspot,
        coldspot: frame.coldspot,
        timestamp: Date.now(),
        radiometricData: frame.radiometricData,
      });
    });

    // Buscar dispositivo ya conectado
    ThermalModule.scanForDevices?.();

    return () => {
      connectSub.remove();
      disconnectSub.remove();
      frameSub.remove();
    };
  }, []);

  // ── Start stream ──────────────────────────────────────────────────
  const startStream = useCallback(async () => {
    const ThermalModule = NativeModules.ThermalCamera;
    if (!ThermalModule) {
      setError('Módulo nativo de cámara térmica no disponible. Conecta una cámara USB-C.');
      return;
    }

    try {
      await ThermalModule.startStream({
        palette: config.palette,
        emissivity: config.emissivity,
        minRange: config.minRange,
        maxRange: config.maxRange,
      });
      setIsStreaming(true);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Error al iniciar stream térmico');
    }
  }, [config]);

  // ── Stop stream ───────────────────────────────────────────────────
  const stopStream = useCallback(() => {
    const ThermalModule = NativeModules.ThermalCamera;
    ThermalModule?.stopStream?.();
    setIsStreaming(false);
  }, []);

  // ── Capture single frame ──────────────────────────────────────────
  const captureFrame = useCallback(async (): Promise<ThermalFrame | null> => {
    const ThermalModule = NativeModules.ThermalCamera;
    if (!ThermalModule) {
      // Fallback: devolver último frame si hay
      return lastFrame;
    }

    try {
      const frame = await ThermalModule.captureFrame({
        palette: config.palette,
        emissivity: config.emissivity,
      });
      const thermalFrame: ThermalFrame = {
        imageBase64: frame.imageBase64,
        width: frame.width,
        height: frame.height,
        minTemp: frame.minTemp,
        maxTemp: frame.maxTemp,
        avgTemp: frame.avgTemp,
        hotspot: frame.hotspot,
        coldspot: frame.coldspot,
        timestamp: Date.now(),
        radiometricData: frame.radiometricData,
      };
      setLastFrame(thermalFrame);
      return thermalFrame;
    } catch (err: any) {
      setError(err.message);
      return null;
    }
  }, [config, lastFrame]);

  // ── Config setters ────────────────────────────────────────────────
  const setPalette = useCallback((palette: ThermalPalette) => {
    setConfig((prev) => ({ ...prev, palette }));
    NativeModules.ThermalCamera?.setPalette?.(palette);
  }, []);

  const setRange = useCallback((min: number, max: number) => {
    setConfig((prev) => ({ ...prev, minRange: min, maxRange: max }));
    NativeModules.ThermalCamera?.setRange?.(min, max);
  }, []);

  const setEmissivity = useCallback((value: number) => {
    const clamped = Math.max(0.1, Math.min(1.0, value));
    setConfig((prev) => ({ ...prev, emissivity: clamped }));
    NativeModules.ThermalCamera?.setEmissivity?.(clamped);
  }, []);

  return {
    isConnected,
    device,
    isStreaming,
    lastFrame,
    config,
    error,
    startStream,
    stopStream,
    captureFrame,
    setPalette,
    setRange,
    setEmissivity,
  };
}
