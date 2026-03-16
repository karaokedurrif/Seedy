/**
 * NeoFarm Seedy — Theme & Colors
 * Paleta agrotech: verdes naturales + tierra + acento NeoFarm
 */

export const Colors = {
  // Primary – Verde NeoFarm
  primary: '#2E7D32',
  primaryDark: '#1B5E20',
  primaryLight: '#4CAF50',
  primarySurface: '#E8F5E9',

  // Secondary – Tierra cálida
  secondary: '#8D6E63',
  secondaryDark: '#5D4037',
  secondaryLight: '#BCAAA4',

  // Accent – Naranja IoT
  accent: '#FF6F00',
  accentLight: '#FFB74D',

  // Backgrounds
  background: '#FAFAFA',
  surface: '#FFFFFF',
  card: '#FFFFFF',
  cardElevated: '#F5F5F5',

  // Text
  text: '#212121',
  textSecondary: '#757575',
  textInverse: '#FFFFFF',
  textMuted: '#9E9E9E',

  // Chat
  chatUser: '#E3F2FD',
  chatAssistant: '#E8F5E9',
  chatSystem: '#FFF3E0',

  // Status
  success: '#4CAF50',
  warning: '#FF9800',
  error: '#F44336',
  info: '#2196F3',

  // Thermal camera
  thermalCold: '#0000FF',
  thermalWarm: '#FFFF00',
  thermalHot: '#FF0000',

  // Borders & dividers
  border: '#E0E0E0',
  divider: '#EEEEEE',

  // Species colors
  speciesPoultry: '#FF8F00',
  speciesPig: '#E91E63',
  speciesCattle: '#795548',
} as const;

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
