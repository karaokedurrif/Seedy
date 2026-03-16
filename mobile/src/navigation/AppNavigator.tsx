/**
 * AppNavigator.tsx — Navegación principal de Seedy Mobile (themed)
 *
 * Bottom tabs: Chat | Cámara | Térmica | Ajustes
 * Themed tab bar via useTheme()
 */

import React from 'react';
import { StyleSheet, Platform } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';

import { ChatScreen } from '../screens/ChatScreen';
import { CameraScreen } from '../screens/CameraScreen';
import { ThermalScreen } from '../screens/ThermalScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { useTheme } from '../theme/ThemeContext';

export type RootTabParamList = {
  Chat: undefined;
  Camera: undefined;
  Thermal: undefined;
  Settings: undefined;
};

const Tab = createBottomTabNavigator<RootTabParamList>();

export function AppNavigator() {
  const { theme } = useTheme();

  return (
    <NavigationContainer>
      <Tab.Navigator
        screenOptions={{
          headerShown: false,
          tabBarActiveTintColor: theme.tabActive,
          tabBarInactiveTintColor: theme.tabInactive,
          tabBarStyle: {
            backgroundColor: theme.tabBarBg,
            borderTopWidth: 1,
            borderTopColor: theme.border,
            height: Platform.OS === 'android' ? 60 : 85,
            paddingBottom: Platform.OS === 'android' ? 8 : 28,
            paddingTop: 6,
            elevation: 0,
          },
          tabBarLabelStyle: styles.tabLabel,
          tabBarItemStyle: styles.tabItem,
        }}
      >
        <Tab.Screen
          name="Chat"
          component={ChatScreen}
          options={{
            tabBarLabel: 'Seedy',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="chatbubbles" size={size} color={color} />
            ),
          }}
        />

        <Tab.Screen
          name="Camera"
          component={CameraScreen}
          options={{
            tabBarLabel: 'Cámara',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="camera" size={size} color={color} />
            ),
          }}
        />

        <Tab.Screen
          name="Thermal"
          component={ThermalScreen}
          options={{
            tabBarLabel: 'Térmica',
            tabBarIcon: ({ color, size }) => (
              <MaterialCommunityIcons
                name="thermometer"
                size={size}
                color={color}
              />
            ),
          }}
        />

        <Tab.Screen
          name="Settings"
          component={SettingsScreen}
          options={{
            tabBarLabel: 'Ajustes',
            tabBarIcon: ({ color, size }) => (
              <Ionicons name="settings" size={size} color={color} />
            ),
          }}
        />
      </Tab.Navigator>
    </NavigationContainer>
  );
}

const styles = StyleSheet.create({
  tabLabel: {
    fontSize: 11,
    fontWeight: '600',
  },
  tabItem: {
    paddingTop: 2,
  },
});
