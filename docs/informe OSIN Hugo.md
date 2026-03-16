Contexto: Proyecto Seedy en /home/davidia/Documentos/Seedy/backend/. 
Ya tengo: classifier.py (clasifica en 8 categorías), rag.py (busca en 
Qdrant), reranker.py, embeddings.py, llm.py, prompts.py (8 system prompts 
por worker). El router está en routers/chat.py.

OBJETIVO: Construir el endpoint POST /chat que implemente el flujo completo:
classify → retrieve → rerank → generate, con soporte para tools.

TAREAS:
1. Revisa routers/chat.py actual. Implementa (o completa) el flujo:
   a) Recibe {"message": str, "history": list, "mode": "strict|practical|creative"}
   b) Clasifica con classifier.py → categoría
   c) Selecciona colecciones Qdrant según CATEGORY_COLLECTIONS
   d) Embed query → Qdrant top-30 → rerank → top-6 chunks
   e) Construye prompt: system (por worker) + contexto RAG + history + query
   f) Llama a LLM (seedy:q8 en Ollama) con streaming SSE
   g) Respuesta incluye: answer, sources (título+path de cada chunk usado), 
      category, confidence
2. Añade soporte básico de tools:
   - "python_calc": ejecuta cálculos (consanguinidad, Capon Score, costes)
   - "qdrant_search": búsqueda adicional si el LLM necesita más contexto
3. Implementa rate limiting básico (10 req/min por IP)
4. Añade endpoint GET /health con status de Qdrant + Ollama
5. Tests: crea backend/tests/test_chat.py con pytest, 5 preguntas de prueba 
   (1 IoT, 1 nutrición, 1 genética, 1 avicultura, 1 normativa). Verifica 
   que cada una se clasifica correctamente y devuelve chunks relevantes.

Modelo LLM: seedy:q8 en Ollama (http://ollama:11434/api/generate).
Modelo embeddings: mxbai-embed-large en Ollama.
No uses LangChain. Código directo con httpx + qdrant-client.