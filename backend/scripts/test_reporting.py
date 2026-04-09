"""Test del reporting agent — ejecutar manualmente."""
import asyncio
import sys
import os
sys.path.insert(0, "/app")

async def test():
    from services.reporting_agent import run_report
    report = await run_report()
    
    a = report["analysis"]
    act = a["actividad"]
    critic = a["critic"]
    gold = a["gold_capture"]
    ka = a["knowledge_agent"]
    qdrant = a["qdrant"]
    
    print("=== REPORTING AGENT TEST ===")
    print(f"Mensajes Open WebUI: {act['total_mensajes']}")
    print(f"  Usuario: {act['mensajes_usuario']}")
    print(f"  Asistente: {act['respuestas_asistente']}")
    print(f"  Chats unicos: {act['conversaciones_unicas']}")
    print(f"Critic: {critic['total_evaluaciones']} eval, {critic['pass']} pass, {critic['block']} block")
    print(f"Gold: {gold['sft_nuevos']} SFT, {gold['dpo_nuevos']} DPO")
    print(f"Knowledge: {ka['ciclos']} ciclos, {ka['busquedas']} busq, {ka['chunks_indexados']} idx, {ka['chunks_promovidos']} prom")
    print(f"Qdrant total: {qdrant['total_chunks']:,}")
    print(f"Queries sin respuesta: {len(a['queries_sin_respuesta'])}")
    print(f"Mejoras ejecutadas: {len(report['improvements'])}")
    print(f"Email enviado: {report['email_sent']}")
    
    import os
    files = sorted(os.listdir("/app/data/reporting_agent/"))
    print(f"Archivos: {files}")

asyncio.run(test())
