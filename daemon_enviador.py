"""
Daemon enviador de lotes — ejecutar cada 15 minutos via cron.

    cd FacturacionElectronica
    python daemon_enviador.py

Levanta todos los DEs en estado 'pendiente' sin protocolo_lote,
los agrupa por tipo_documento (máx 50 por lote) y los envía a SIFEN
usando el WS Asíncrono (recibe-lote). Si SIFEN responde 0300, marca
los DEs como 'en_lote' con el dProtConsLote recibido.

Cron sugerido (cada 15 min):
    */15 * * * * cd /ruta/FacturacionElectronica && python daemon_enviador.py >> logs/daemon_enviador.log 2>&1
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE
from sifen_py.services.soap_client import SifenSOAPClient
from app.config_manager import get_sifen_config

TIPOS_DOCUMENTO = [1, 4, 5, 6, 7]
MAX_POR_LOTE    = 50


def _log(msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


def enviar_lotes():
    sifen_config = get_sifen_config()
    client       = SifenSOAPClient(sifen_config)
    db           = Conexion()
    repo         = RepositorioDE(db)

    total_enviados = 0
    total_errores  = 0

    for tipo in TIPOS_DOCUMENTO:
        docs = repo.obtener_para_reenvio(tipo_documento=tipo, limite=MAX_POR_LOTE)
        # Filtrar solo 'pendiente' — los 'error' se gestionan manualmente
        docs = [dict(d) if hasattr(d, 'keys') else
                {'cdc': d[0], 'xml_firmado': d[1], 'tipo_documento': d[2], 'estado': d[3]}
                for d in docs if (d[3] if not hasattr(d, 'keys') else d['estado']) == 'pendiente']

        if not docs:
            continue

        cdcs = [d['cdc']        for d in docs]
        xmls = [d['xml_firmado'] for d in docs]

        _log(f"Tipo {tipo}: enviando lote con {len(docs)} DE(s)...")

        try:
            resp = client.enviar_lote_directo(xmls)
        except Exception as e:
            _log(f"  ERROR al enviar lote tipo {tipo}: {e}")
            total_errores += len(docs)
            continue

        protocolo_lote = resp.raw.get('protocolo_lote', '')

        if resp.codigo == '0300' and protocolo_lote:
            repo.marcar_en_lote(cdcs, protocolo_lote)
            _log(f"  OK — dProtConsLote: {protocolo_lote} | {len(docs)} DE(s) marcados como en_lote")
            total_enviados += len(docs)
        else:
            _log(f"  SIFEN rechazó el lote — código: {resp.codigo} | {resp.descripcion}")
            total_errores += len(docs)

    db.cerrar()
    _log(f"Finalizado — enviados: {total_enviados} | errores: {total_errores}")


if __name__ == '__main__':
    _log("=== daemon_enviador iniciado ===")
    try:
        enviar_lotes()
    except Exception as e:
        _log(f"ERROR FATAL: {e}")
        sys.exit(1)
