Contexto: Proyecto Seedy en /home/davidia/Documentos/Seedy/. 
Tengo un docker-compose.yml con 8 servicios (ollama GPU, open-webui, qdrant, 
seedy-backend FastAPI, influxdb, mosquitto, nodered, grafana). El backend 
FastAPI está en backend/ con servicios: classifier.py, embeddings.py, 
llm.py, rag.py, reranker.py, y ingestion/ con chunker.py + ingest.py.

Carpeta conocimientos/ tiene 7 subcarpetas con documentos .md (30KB+ cada uno):
1.PorciData, 2.Nutricion, 3.Genetica, 4.Estrategia, 5.Digital Twins, 
6.Normativa, 7.Avicultura.

El mapeo carpeta→colección Qdrant está en backend/services/rag.py 
(FOLDER_TO_COLLECTION). El modelo de embeddings es mxbai-embed-large 
en Ollama (http://ollama:11434).

TAREAS (en orden):
1. Revisa backend/ingestion/ingest.py y backend/ingestion/chunker.py. 
   Asegúrate de que el chunker use ~800 tokens, overlap 120 tokens, 
   y preserve encabezados markdown (##, ###).
2. Crea un script CLI (backend/ingestion/run_ingest.py) que:
   a) Recorra conocimientos/ recursivamente
   b) Lea cada .md, lo chunk con chunker.py
   c) Genere embeddings con mxbai-embed-large vía Ollama 
   d) Haga upsert en Qdrant en la colección correcta según FOLDER_TO_COLLECTION
   e) Incluya payload: doc_id, title, source_path, date_ingested, chunk_index
   f) Tenga modo --dry-run para validar sin escribir
3. Verifica que docker-compose.yml tiene healthchecks correctos para qdrant 
   y ollama, y que seedy-backend depende de ambos.
4. Crea un .env con las variables necesarias (QDRANT_HOST, OLLAMA_HOST, etc.)
5. Prueba: levanta solo qdrant + ollama, ejecuta el ingest, y verifica con 
   curl a Qdrant que las colecciones tienen puntos.

NO crees documentación extra. Solo código funcional y el .env.