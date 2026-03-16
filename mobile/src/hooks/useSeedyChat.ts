/**
 * useSeedyChat.ts — Hook para chat con Seedy vía SSE streaming
 *
 * Gestiona el historial de mensajes, streaming de tokens,
 * envío de imágenes (cámara/galería) y estado de loading.
 */

import { useState, useCallback, useRef } from 'react';
import { streamChat, ChatMessage } from '../api/seedyClient';

interface UseSeedyChatReturn {
  messages: ChatMessage[];
  isStreaming: boolean;
  error: string | null;
  sendMessage: (text: string, image?: string) => Promise<void>;
  sendImageForAnalysis: (imageBase64: string, prompt?: string) => Promise<void>;
  clearHistory: () => void;
  retryLast: () => Promise<void>;
}

const SYSTEM_MESSAGE: ChatMessage = {
  role: 'system',
  content:
    'Eres Seedy, asistente técnico de NeoFarm. ' +
    'Cuando el usuario envía una foto de un animal, identifica especie, raza, ' +
    'condición corporal, peso estimado y cualquier observación sanitaria visible. ' +
    'Responde en español, prosa profesional.',
};

export function useSeedyChat(): UseSeedyChatReturn {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const lastUserMsg = useRef<ChatMessage | null>(null);

  const sendMessage = useCallback(
    async (text: string, image?: string) => {
      if (isStreaming) return;

      const userMsg: ChatMessage = {
        role: 'user',
        content: text,
        image,
        timestamp: Date.now(),
      };
      lastUserMsg.current = userMsg;

      setMessages((prev) => [...prev, userMsg]);
      setIsStreaming(true);
      setError(null);

      // Preparar mensajes para la API (system + historial + nuevo)
      const apiMessages = [
        SYSTEM_MESSAGE,
        ...messages.slice(-10), // últimos 10 mensajes como contexto
        userMsg,
      ];

      let fullResponse = '';
      const assistantMsg: ChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: Date.now(),
      };

      // Añadir mensaje vacío del asistente para ir llenando
      setMessages((prev) => [...prev, assistantMsg]);

      try {
        for await (const token of streamChat(apiMessages)) {
          fullResponse += token;
          // Actualizar el último mensaje (assistant) con el texto acumulado
          setMessages((prev) => {
            const updated = [...prev];
            updated[updated.length - 1] = {
              ...updated[updated.length - 1],
              content: fullResponse,
            };
            return updated;
          });
        }
      } catch (err: any) {
        const errMsg = err.message || 'Error de conexión con Seedy';
        setError(errMsg);
        // Actualizar mensaje con el error
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: fullResponse || `⚠️ ${errMsg}`,
          };
          return updated;
        });
      } finally {
        setIsStreaming(false);
      }
    },
    [messages, isStreaming],
  );

  const sendImageForAnalysis = useCallback(
    async (imageBase64: string, prompt?: string) => {
      const defaultPrompt =
        'Analiza esta imagen. Identifica la especie, raza, condición corporal, ' +
        'peso estimado y cualquier observación sanitaria visible.';
      await sendMessage(prompt || defaultPrompt, imageBase64);
    },
    [sendMessage],
  );

  const clearHistory = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  const retryLast = useCallback(async () => {
    if (!lastUserMsg.current) return;
    // Eliminar último par user+assistant
    setMessages((prev) => prev.slice(0, -2));
    const { content, image } = lastUserMsg.current;
    await sendMessage(content, image);
  }, [sendMessage]);

  return {
    messages,
    isStreaming,
    error,
    sendMessage,
    sendImageForAnalysis,
    clearHistory,
    retryLast,
  };
}
