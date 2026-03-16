/**
 * ThemeContext.tsx — Proveedor global de tema
 *
 * Persiste la selección en SecureStore.
 * useTheme() devuelve el tema activo + setTheme().
 */

import React, {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  useMemo,
} from 'react';
import * as SecureStore from 'expo-secure-store';
import {
  type AppTheme,
  type ThemePreset,
  THEMES,
  THEME_DARK,
} from './themes';

const STORAGE_KEY = 'seedy_theme_preset';

interface ThemeContextValue {
  theme: AppTheme;
  preset: ThemePreset;
  setPreset: (p: ThemePreset) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  theme: THEME_DARK,
  preset: 'dark',
  setPreset: () => {},
});

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preset, setPresetState] = useState<ThemePreset>('dark');
  const [loaded, setLoaded] = useState(false);

  // Load saved theme
  useEffect(() => {
    (async () => {
      try {
        const saved = await SecureStore.getItemAsync(STORAGE_KEY);
        if (saved && saved in THEMES) {
          setPresetState(saved as ThemePreset);
        }
      } catch {}
      setLoaded(true);
    })();
  }, []);

  const setPreset = useCallback(async (p: ThemePreset) => {
    setPresetState(p);
    await SecureStore.setItemAsync(STORAGE_KEY, p);
  }, []);

  const value = useMemo<ThemeContextValue>(
    () => ({
      theme: THEMES[preset],
      preset,
      setPreset,
    }),
    [preset, setPreset],
  );

  if (!loaded) return null; // splash handles it

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  return useContext(ThemeContext);
}
