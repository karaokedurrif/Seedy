/**
 * App.tsx — Punto de entrada principal de Seedy Mobile
 *
 * Wraps:
 * - ThemeProvider (3 presets dinámicos)
 * - SafeAreaProvider
 * - PaperProvider (Material Design — tema dinámico)
 * - StatusBar config (basado en theme.statusBarStyle)
 * - AppNavigator
 */

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import {
  Provider as PaperProvider,
  MD3DarkTheme,
  MD3LightTheme,
} from 'react-native-paper';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

import { ThemeProvider, useTheme } from './src/theme/ThemeContext';
import { AppNavigator } from './src/navigation/AppNavigator';

function ThemedApp() {
  const { theme } = useTheme();

  const paperTheme = {
    ...(theme.isDark ? MD3DarkTheme : MD3LightTheme),
    colors: {
      ...(theme.isDark ? MD3DarkTheme.colors : MD3LightTheme.colors),
      primary: theme.primary,
      primaryContainer: theme.primarySurface,
      secondary: theme.secondary,
      background: theme.bg1,
      surface: theme.bg2,
      error: theme.error,
    },
  };

  return (
    <PaperProvider theme={paperTheme}>
      <StatusBar
        style={theme.statusBarStyle}
        backgroundColor={theme.bg0}
      />
      <AppNavigator />
    </PaperProvider>
  );
}

export default function App() {
  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <ThemeProvider>
          <ThemedApp />
        </ThemeProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}
