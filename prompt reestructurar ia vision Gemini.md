Contexto: Estoy optimizando el pipeline de visión Seedy v3 (abril 2026). Actualmente, la cámara Dahua (4K) tiene un cuello de botella en la captura y el loop de identificación es muy lento (60s).

Tarea: Refactoriza el módulo de captura y detección para implementar una Arquitectura de Doble Stream y optimizar la Dahua WizSense.

Requerimientos Técnicos:

Doble Stream: Usa el Sub-stream (H.264, resolución reducida) de go2rtc para el tracking y detección constante (YOLOv8s/v11) a 10-15 FPS. Reserva el Main-stream (4K) solo para snapshots de alta calidad cuando el Quality Gate detecte un candidato óptimo para identificación de raza.

Optimización Dahua: Crea una función optimize_dahua_settings(ip) que use la API CGI de Dahua para:

Forzar el Exposure a 1/200s (evitar desenfoque de movimiento en aves).

Ajustar el I-Frame Interval para que coincida con los FPS y reducir latencia en go2rtc.

Captura por Eventos: Elimina el cooldown de 60s del loop para la Dahua. En su lugar, dispara una captura de alta resolución si el bird_tracker detecta:

Un ave nueva sin ai_vision_id.

Un evento de mating (monta).

Un pest_alert de severidad 'alert'.

Migración YOLOv11: Prepara el código para cargar yolo11s.pt (TensorRT) en lugar de v8s, optimizando para la RTX 5080.

Salida: Genera el código Python para el nuevo capture_manager.py y las modificaciones en _analyze_frame() que permitan esta lógica de disparo por eventos en lugar de tiempo fijo.