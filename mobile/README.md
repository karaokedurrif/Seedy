# 📱 Seedy Mobile — NeoFarm AI Assistant

App Android para chat con Seedy, visión ganadera y cámara térmica USB-C.

## 🏗️ Stack

| Componente | Tecnología |
|---|---|
| Framework | React Native + Expo SDK 52 |
| Lenguaje | TypeScript |
| UI | React Native Paper (Material Design 3) |
| Navegación | React Navigation (Bottom Tabs) |
| Cámara | expo-camera + expo-image-picker |
| Térmica | Módulo nativo UVC (USB-C) |
| Backend | FastAPI + Ollama (seedy:v6-local) |

## 📂 Estructura

```
mobile/
├── App.tsx                          # Entry point
├── app.json                         # Expo config + android permissions
├── eas.json                         # EAS Build (APK/AAB)
├── package.json
├── babel.config.js
├── tsconfig.json
└── src/
    ├── api/
    │   └── seedyClient.ts           # API: chat SSE, vision, thermal, genetics
    ├── components/
    │   └── MessageBubble.tsx         # Burbujas de chat
    ├── hooks/
    │   ├── useSeedyChat.ts           # Hook SSE streaming + contexto
    │   └── useThermalCamera.ts       # Hook cámara térmica UVC
    ├── navigation/
    │   └── AppNavigator.tsx          # Bottom tab navigator
    ├── screens/
    │   ├── ChatScreen.tsx            # Chat con Seedy (IA + RAG)
    │   ├── CameraScreen.tsx          # Cámara regular → raza/especie
    │   ├── ThermalScreen.tsx         # Cámara térmica USB-C
    │   └── SettingsScreen.tsx        # Config servidor, info modelo
    └── theme/
        └── colors.ts                # Paleta NeoFarm
```

## 🚀 Setup

```bash
cd mobile

# Instalar dependencias
npm install

# Development con Expo Go
npx expo start

# Build APK (requiere cuenta EAS)
npx eas-cli login
npx eas build --platform android --profile preview
```

## 📱 Pantallas

### 💬 Chat con Seedy
- SSE streaming en tiempo real
- Enviar fotos al chat (cámara o galería)
- 10 mensajes de contexto
- Identificación de razas/especies por imagen

### 📷 Cámara de Visión
- Selector de especie (Auto/Aves/Porcino/Vacuno)
- Visor con overlay
- Análisis de raza, condición corporal, peso estimado
- Notas de salud visual
- Integración con `/vision/analyze`

### 🌡️ Cámara Térmica
- Soporte USB-C (UVC): InfiRay P2 Pro, T2S+, FLIR One
- Objetivo 9mm con resolución TISR
- 4 paletas: Hierro, Arcoíris, Blanco, Lava
- Indicadores min/max/avg temperatura
- Detección fiebre/hipotermia por especie:
  - 🐔 Aves: 40.6–41.7°C (fiebre ≥42°C)
  - 🐷 Porcino: 38.0–39.5°C (fiebre ≥40°C)
  - 🐄 Vacuno: 38.0–39.5°C (fiebre ≥39.5°C)
- Análisis térmico con alertas automáticas

### ⚙️ Ajustes
- URL del backend (SecureStore)
- Health check del servidor
- Info del modelo (seedy:v6-local, 302 SFT)
- Links a plataformas NeoFarm

## 🔌 Backend endpoints requeridos

| Endpoint | Método | Descripción |
|---|---|---|
| `/chat` | POST | Chat SSE streaming |
| `/vision/analyze` | POST | Análisis de imagen (raza/especie) |
| `/vision/thermal` | POST | Análisis de imagen térmica |
| `/health` | GET | Healthcheck |
| `/genetics/breeds` | GET | Lista de razas |
| `/genetics/predict-f1` | POST | Predicción F1 |

## 📦 Build APK

```bash
# Preview APK (para testing)
npx eas build --platform android --profile preview

# Production AAB (para Google Play)
npx eas build --platform android --profile production
```

## 🔧 Cámaras Térmicas Compatibles

| Modelo | Resolución | Interfaz | Radiométrica |
|---|---|---|---|
| InfiRay P2 Pro (9mm) | 256×192 + TISR | USB-C UVC | ✅ |
| InfiRay T2S+ / T3S | 256×192 | USB-C UVC | ✅ |
| FLIR One Pro / Edge | 160×120 + MSX | USB-C | ✅ |
| Seek Thermal CompactPRO | 320×240 | USB-C | Parcial |

---

*Fase 12 — Seedy Mobile · NeoFarm 2025*
