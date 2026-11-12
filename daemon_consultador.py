"""
Daemon consultador de lotes — ejecutar cada 15 minutos via cron (desfasado 10 min).

    cd FacturacionElectronica
    python daemon_consultador.py

Levanta todos los protocolo_lote distintos en estado 'en_lote' cuyo
fecha_envio tiene al menos 10 minutos de antigüedad, consulta el resultado
en SIFEN y actualiza el estado de cada DE.

Códigos de respuesta de consulta-lote:
    0361 → Lote en procesamiento — se reintenta en el próximo ciclo
    0362 → Procesado — actualiza cada DE a aprobado/rechazado
    0364 → Venció el plazo de 48 hs — fallback: consulta CDC por CDC
    0360 → Lote no existe — marca los DEs como error

Cron sugerido (cada 15 min, desfasado 10 min respecto al enviador):
    10,25,40,55 * * * * cd /ruta/FacturacionElectronica && python daemon_consultador.py >> logs/daemon_consultador.log 2>&1
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE
from sifen_py.services.soap_client import SifenSOAPClient
from app.config_manager import get_sifen_config


def _log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def _actualizar_desde_lote(repo: RepositorioDE, detalle_des: list):
    """Procesa el detalle_des de un lote 0362 y actualiza cada DE."""
    aprobados  = 0
    rechazados = 0
    for item in detalle_des:
        cdc    = item.get('cdc', '')
        codigo = item.get('codigo', '')
        if not cdc:
            continue
        repo.actualizar_respuesta(
            cdc=cdc,
            codigo=codigo,
            descripcion=item.get('mensaje', ''),
        )
        if codigo in ('0260', '1001'):
            aprobados += 1
        else:
            rechazados += 1
    return aprobados, rechazados


def _fallback_consulta_individual(repo: RepositorioDE, client: SifenSOAPClient,
                                  protocolo_lote: str):
    """
    Fallback cuando el lote venció (0364 — más de 48 hs).
    Consulta cada CDC del lote individualmente con consultar_de_directo().
    """
    docs = repo.obtener_cdcs_por_protocolo_lote(protocolo_lote)
    _log(f"  Fallback individual: {len(docs)} DE(s) en lote vencido {protocolo_lote}")

    for doc in docs:
        cdc = doc['cdc'] if isinstance(doc, dict) else doc[0]
        try:
            resp = client.consultar_de_directo(cdc)
            repo.actualizar_estado_consulta(
                cdc=cdc,
                codigo=resp.codigo,
                descripcion=resp.descripcion,
                protocolo=resp.raw.get('protocolo'),
                respuesta_xml=resp.raw.get('xml'),
            )
            _log(f"    CDC {cdc[:20]}… → {resp.codigo}")
        except Exception as e:
            _log(f"    ERROR consultando CDC {cdc[:20]}…: {e}")


def consultar_lotes():
    sifen_config = get_sifen_config()
    client       = SifenSOAPClient(sifen_config)
    db           = Conexion()
    repo         = RepositorioDE(db)

    lotes = repo.obtener_lotes_para_consultar()

    if not lotes:
        _log("Sin lotes para consultar.")
        db.cerrar()
        return

    _log(f"Consultando {len(lotes)} lote(s)...")

    total_aprobados  = 0
    total_rechazados = 0
    total_en_proceso = 0
    total_errores    = 0

    for protocolo_lote in lotes:
        _log(f"  Lote {protocolo_lote}...")
        try:
            resp = client.consultar_lote_directo(protocolo_lote)
        except Exception as e:
            _log(f"    ERROR al consultar: {e}")
            total_errores += 1
            continue

        if resp.codigo == '0362':
            aprobados, rechazados = _actualizar_desde_lote(
                repo, resp.raw.get('detalle_des', [])
            )
            _log(f"    Procesado — aprobados: {aprobados} | rechazados: {rechazados}")
            total_aprobados  += aprobados
            total_rechazados += rechazados

        elif resp.codigo == '0361':
            _log(f"    En procesamiento — se reintenta en el próximo ciclo")
            total_en_proceso += 1

        elif resp.codigo == '0364':
            _log(f"    Lote vencido (>48 hs) — consultando CDC por CDC...")
            _fallback_consulta_individual(repo, client, protocolo_lote)

        elif resp.codigo == '0360':
            _log(f"    Lote no existe en SIFEN — marcando DEs como error")
            docs = repo.obtener_cdcs_por_protocolo_lote(protocolo_lote)
            for doc in docs:
                cdc = doc['cdc'] if isinstance(doc, dict) else doc[0]
                repo.actualizar_respuesta(
                    cdc=cdc,
                    codigo='0360',
                    descripcion='Lote no existe en SIFEN',
                )
            total_errores += len(docs)

        else:
            _log(f"    Respuesta inesperada — código: {resp.codigo} | {resp.descripcion}")
            total_errores += 1

    db.cerrar()
    _log(
        f"Finalizado — aprobados: {total_aprobados} | rechazados: {total_rechazados}"
        f" | en_proceso: {total_en_proceso} | errores: {total_errores}"
    )


if __name__ == '__main__':
    _log("=== daemon_consultador iniciado ===")
    try:
        consultar_lotes()
    except Exception as e:
        _log(f"ERROR FATAL: {e}")
        sys.exit(1)
