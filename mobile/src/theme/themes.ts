/**
 * Theme system — 3 presets tipo Open WebUI
 *
 * 1. "Seedy Dark"  — Estilo Open WebUI (dark gris/negro + accent verde)
 * 2. "NeoFarm"     — Verde campo oscuro + tierra
 * 3. "Arctic"      — Claro hielo + azul acero
 *
 * Cada tema define colores, fondos, bordes, chat bubbles, etc.
 * ThemeProvider + useTheme() para acceso global.
 */

export type ThemePreset = 'dark' | 'neofarm' | 'arctic';

export interface AppTheme {
  id: ThemePreset;
  name: string;
  isDark: boolean;

  // Core
  primary: string;
  primaryDark: string;
  primaryLight: string;
  primarySurface: string;
  secondary: string;
  accent: string;
  accentLight: string;

  // Backgrounds — Open WebUI style layers
  bg0: string;       // deepest background (sidebar, bottom bar)
  bg1: string;       // main content background
  bg2: string;       // cards / elevated surfaces
  bg3: string;       // inputs, modals
  bgHover: string;   // hover / press state

  // Text
  text: string;
  textSecondary: string;
  textMuted: string;
  textInverse: string;

  // Chat
  chatUser: string;
  chatAssistant: string;
  chatUserText: string;
  chatAssistantText: string;

  // Input
  inputBg: string;
  inputBorder: string;
  inputText: string;
  inputPlaceholder: string;

  // Status
  success: string;
  warning: string;
  error: string;
  info: string;

  // Thermal
  thermalCold: string;
  thermalWarm: string;
  thermalHot: string;

  // Borders & dividers
  border: string;
  divider: string;

  // Tab bar
  tabBarBg: string;
  tabActive: string;
  tabInactive: string;

  // Species
  speciesPoultry: string;
  speciesPig: string;
  speciesCattle: string;

  // Status bar
  statusBarStyle: 'light' | 'dark';
}

// ─────────────────────────────────────────────────────────────────────
// PRESET 1: Seedy Dark — Estilo Open WebUI
// ─────────────────────────────────────────────────────────────────────
export const THEME_DARK: AppTheme = {
  id: 'dark',
  name: 'Seedy Dark',
  isDark: true,

  primary: '#2E7D32',
  primaryDark: '#1B5E20',
  primaryLight: '#4CAF50',
  primarySurface: '#1A2F1C',
  secondary: '#8D6E63',
  accent: '#FF6F00',
  accentLight: '#FFB74D',

  bg0: '#0A0A0A',        // sidebar / bottom bar — true black
  bg1: '#111111',        // main background
  bg2: '#1E1E1E',        // cards
  bg3: '#2A2A2A',        // inputs
  bgHover: '#333333',

  text: '#E5E5E5',
  textSecondary: '#A0A0A0',
  textMuted: '#666666',
  textInverse: '#FFFFFF',

  chatUser: '#2A2A2A',
  chatAssistant: 'transparent',
  chatUserText: '#E5E5E5',
  chatAssistantText: '#D4D4D4',

  inputBg: '#1E1E1E',
  inputBorder: '#333333',
  inputText: '#E5E5E5',
  inputPlaceholder: '#666666',

  success: '#4CAF50',
  warning: '#FF9800',
  error: '#EF5350',
  info: '#42A5F5',

  thermalCold: '#42A5F5',
  thermalWarm: '#FFEE58',
  thermalHot: '#EF5350',

  border: '#2A2A2A',
  divider: '#222222',

  tabBarBg: '#0A0A0A',
  tabActive: '#4CAF50',
  tabInactive: '#555555',

  speciesPoultry: '#FFB300',
  speciesPig: '#F06292',
  speciesCattle: '#A1887F',

  statusBarStyle: 'light',
};

// ─────────────────────────────────────────────────────────────────────
// PRESET 2: NeoFarm — Verde oscuro campo
// ─────────────────────────────────────────────────────────────────────
export const THEME_NEOFARM: AppTheme = {
  id: 'neofarm',
  name: 'NeoFarm',
  isDark: true,

  primary: '#43A047',
  primaryDark: '#2E7D32',
  primaryLight: '#66BB6A',
  primarySurface: '#1B3A1E',
  secondary: '#8D6E63',
  accent: '#FF8F00',
  accentLight: '#FFCA28',

  bg0: '#0D1F10',        // very dark green
  bg1: '#132716',        // main
  bg2: '#1A3A1E',        // cards
  bg3: '#234D28',        // inputs
  bgHover: '#2C5E32',

  text: '#E8F5E9',
  textSecondary: '#A5D6A7',
  textMuted: '#5B8C5E',
  textInverse: '#FFFFFF',

  chatUser: '#234D28',
  chatAssistant: 'transparent',
  chatUserText: '#E8F5E9',
  chatAssistantText: '#C8E6C9',

  inputBg: '#1A3A1E',
  inputBorder: '#2C5E32',
  inputText: '#E8F5E9',
  inputPlaceholder: '#5B8C5E',

  success: '#66BB6A',
  warning: '#FFB74D',
  error: '#EF5350',
  info: '#4FC3F7',

  thermalCold: '#4FC3F7',
  thermalWarm: '#FFD54F',
  thermalHot: '#EF5350',

  border: '#234D28',
  divider: '#1A3A1E',

  tabBarBg: '#0D1F10',
  tabActive: '#66BB6A',
  tabInactive: '#4A7A4E',

  speciesPoultry: '#FFB300',
  speciesPig: '#F06292',
  speciesCattle: '#A1887F',

  statusBarStyle: 'light',
};

// ─────────────────────────────────────────────────────────────────────
// PRESET 3: Arctic — Claro con azul acero
// ─────────────────────────────────────────────────────────────────────
export const THEME_ARCTIC: AppTheme = {
  id: 'arctic',
  name: 'Arctic',
  isDark: false,

  primary: '#37474F',
  primaryDark: '#263238',
  primaryLight: '#546E7A',
  primarySurface: '#ECEFF1',
  secondary: '#78909C',
  accent: '#FF6F00',
  accentLight: '#FFB74D',

  bg0: '#ECEFF1',        // sidebar / bottom
  bg1: '#FAFAFA',        // main
  bg2: '#FFFFFF',        // cards
  bg3: '#F5F5F5',        // inputs
  bgHover: '#E8EAF0',

  text: '#212121',
  textSecondary: '#616161',
  textMuted: '#9E9E9E',
  textInverse: '#FFFFFF',

  chatUser: '#E3F2FD',
  chatAssistant: '#FAFAFA',
  chatUserText: '#212121',
  chatAssistantText: '#333333',

  inputBg: '#F5F5F5',
  inputBorder: '#E0E0E0',
  inputText: '#212121',
  inputPlaceholder: '#9E9E9E',

  success: '#43A047',
  warning: '#EF6C00',
  error: '#D32F2F',
  info: '#1976D2',

  thermalCold: '#1976D2',
  thermalWarm: '#FDD835',
  thermalHot: '#D32F2F',

  border: '#E0E0E0',
  divider: '#EEEEEE',

  tabBarBg: '#FFFFFF',
  tabActive: '#37474F',
  tabInactive: '#B0BEC5',

  speciesPoultry: '#E65100',
  speciesPig: '#C2185B',
  speciesCattle: '#6D4C41',

  statusBarStyle: 'dark',
};

// ─────────────────────────────────────────────────────────────────────
// Lookup
// ─────────────────────────────────────────────────────────────────────
export const THEMES: Record<ThemePreset, AppTheme> = {
  dark: THEME_DARK,
  neofarm: THEME_NEOFARM,
  arctic: THEME_ARCTIC,
};

export const THEME_LIST: AppTheme[] = [THEME_DARK, THEME_NEOFARM, THEME_ARCTIC];

// ── Shared constants ────────────────────────────────────────────────
export const Spacing = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 48,
} as const;

export const FontSize = {
  caption: 12,
  body: 14,
  bodyLarge: 16,
  title: 18,
  titleLarge: 22,
  headline: 28,
} as const;

export const Radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
} as const;

// ── Animal temperature ranges ───────────────────────────────────────
export const ANIMAL_TEMP_RANGES = {
  poultry: { normal: { min: 40.6, max: 41.7 }, fever: 42.0, hypo: 39.5 },
  pig:     { normal: { min: 38.0, max: 39.5 }, fever: 40.0, hypo: 37.0 },
  cattle:  { normal: { min: 38.0, max: 39.5 }, fever: 39.5, hypo: 36.5 },
} as const;
