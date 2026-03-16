/**
 * seedyClient.ts — API client para backend FastAPI de Seedy
 *
 * Endpoints:
 *   POST /chat          → SSE streaming (chat con Seedy)
 *   POST /vision/analyze → Análisis de imagen (raza, especie, estado)
 *   POST /vision/thermal → Análisis de imagen térmica
 *   GET  /health        → Healthcheck
 *   GET  /genetics/breeds → Lista de razas
 *   POST /genetics/predict-f1 → Predicción F1
 */

import * as SecureStore from 'expo-secure-store';

// ── Config ──────────────────────────────────────────────────────────────
export const STORAGE_KEYS = {
  BACKEND_URL: 'seedy_backend_url',
} as const;

// Default: API pública via Cloudflare Tunnel
// LAN fallback: http://192.168.1.100:8000
const DEFAULT_URL = 'https://seedy-api.neofarm.io';

export async function getBackendUrl(): Promise<string> {
  const stored = await SecureStore.getItemAsync(STORAGE_KEYS.BACKEND_URL);
  return stored || DEFAULT_URL;
}

export async function setBackendUrl(url: string): Promise<void> {
  await SecureStore.setItemAsync(STORAGE_KEYS.BACKEND_URL, url);
}

// ── Types ───────────────────────────────────────────────────────────────
export interface ChatMessage {
  role: 'system' | 'user' | 'assistant';
  content: string;
  image?: string; // base64 para VLM
  timestamp?: number;
}

export interface VisionAnalysis {
  species: string;          // poultry | pig | cattle | unknown
  breed: string;            // nombre de la raza detectada
  confidence: number;       // 0.0 - 1.0
  body_condition: string;   // buena | regular | mala
  estimated_weight_kg: number | null;
  health_notes: string[];   // observaciones de salud visual
  description: string;      // descripción completa
}

export interface ThermalAnalysis {
  min_temp_c: number;
  max_temp_c: number;
  avg_temp_c: number;
  hotspots: Array<{ x: number; y: number; temp_c: number }>;
  animal_temps: Array<{
    id: number;
    body_temp_c: number;
    status: 'normal' | 'fiebre' | 'hipotermia';
  }>;
  alerts: string[];
  description: string;
}

export interface HealthStatus {
  status: string;
  model: string;
  rag_collections: number;
  uptime: number;
  qdrant?: boolean;
  collections?: string[];
  error?: string;
}

// ── SSE Chat Stream ─────────────────────────────────────────────────────
export async function* streamChat(
  messages: ChatMessage[],
  onToken?: (token: string) => void,
): AsyncGenerator<string> {
  const baseUrl = await getBackendUrl();

  const response = await fetch(`${baseUrl}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      messages: messages.map((m) => ({
        role: m.role,
        content: m.content,
        ...(m.image ? { images: [m.image] } : {}),
      })),
      stream: true,
    }),
  });

  if (!response.ok) {
    throw new Error(`Chat error: ${response.status} ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') return;

        try {
          const parsed = JSON.parse(data);
          const token = parsed.choices?.[0]?.delta?.content
            || parsed.response
            || parsed.token
            || '';
          if (token) {
            onToken?.(token);
            yield token;
          }
        } catch {
          // SSE line sin JSON válido — puede ser token raw
          if (data.trim()) {
            onToken?.(data);
            yield data;
          }
        }
      }
    }
  }
}

// ── Vision Analysis ─────────────────────────────────────────────────────
export async function analyzeImage(
  imageBase64: string,
  species?: string,
): Promise<VisionAnalysis> {
  const baseUrl = await getBackendUrl();

  const response = await fetch(`${baseUrl}/vision/analyze`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image: imageBase64,
      species_hint: species || null,
    }),
  });

  if (!response.ok) {
    throw new Error(`Vision error: ${response.status}`);
  }

  return response.json();
}

// ── Thermal Analysis ────────────────────────────────────────────────────
export async function analyzeThermal(
  imageBase64: string,
  rawThermalData?: number[], // radiometric data if available
): Promise<ThermalAnalysis> {
  const baseUrl = await getBackendUrl();

  const response = await fetch(`${baseUrl}/vision/thermal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      image: imageBase64,
      thermal_data: rawThermalData || null,
    }),
  });

  if (!response.ok) {
    throw new Error(`Thermal error: ${response.status}`);
  }

  return response.json();
}

// ── Health & Info ───────────────────────────────────────────────────────
export async function checkHealth(): Promise<HealthStatus> {
  const baseUrl = await getBackendUrl();
  const response = await fetch(`${baseUrl}/health`, { timeout: 5000 } as any);
  if (!response.ok) throw new Error(`Health: ${response.status}`);
  return response.json();
}

// ── Genetics ────────────────────────────────────────────────────────────
export async function getBreeds(species?: string): Promise<any[]> {
  const baseUrl = await getBackendUrl();
  const params = species ? `?species=${species}` : '';
  const response = await fetch(`${baseUrl}/genetics/breeds${params}`);
  if (!response.ok) throw new Error(`Breeds: ${response.status}`);
  return response.json();
}

export async function predictF1(
  sireBreed: string,
  damBreed: string,
): Promise<any> {
  const baseUrl = await getBackendUrl();
  const response = await fetch(`${baseUrl}/genetics/predict-f1`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sire_breed: sireBreed, dam_breed: damBreed }),
  });
  if (!response.ok) throw new Error(`PredictF1: ${response.status}`);
  return response.json();
}
