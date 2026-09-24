"""Endpoints de consulta de documentos."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE
from sifen_py.services.soap_client import SifenSOAPClient
from loguru import logger

from app.config_manager import get_sifen_config

router = APIRouter(prefix='/api/v1', tags=['Consultas'])


def _row(fila) -> dict:
    if fila is None:
        return None
    return dict(fila) if hasattr(fila, 'keys') else fila


@router.get('/facturas', summary="Listar documentos")
async def listar_facturas(
    estado: Optional[str] = Query(None, description="aprobado | rechazado | pendiente"),
    limit: int = Query(20, ge=1, le=200),
):
    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        filas = repo.listar_por_estado(estado, limite=limit) if estado else repo.listar_recientes(limite=limit)
        return [_row(f) for f in filas]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.cerrar()


@router.get('/facturas/{cdc}', summary="Documento por CDC")
async def obtener_factura(cdc: str):
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")
    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        fila = repo.obtener_por_cdc(cdc)
        if not fila:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        return _row(fila)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.cerrar()


@router.get('/facturas/{cdc}/items', summary="Ítems del documento")
async def obtener_items_factura(cdc: str):
    """
    Devuelve los ítems del documento almacenado en BD.
    Útil para pre-cargar una NCE con los datos de la FE original.
    """
    import json
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")
    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        fila = repo.obtener_por_cdc(cdc)
        if not fila:
            raise HTTPException(status_code=404, detail="Documento no encontrado")
        fila = dict(fila)
        data_json = fila.get('data_json')
        if not data_json:
            raise HTTPException(status_code=422, detail="Documento sin datos de ítems")
        data = json.loads(data_json)
        items = data.get('items', [])
        return {
            'cdc': cdc,
            'numero_doc': fila.get('numero_doc'),
            'monto_total': fila.get('monto_total'),
            'items': [
                {
                    'codigo':          i.get('codigo', ''),
                    'descripcion':     i.get('descripcion', ''),
                    'cantidad':        i.get('cantidad', 1),
                    'precioUnitario':  i.get('precioUnitario', 0),
                    'iva':             i.get('iva', 10),
                    'unidadMedida':    i.get('unidadMedida', 77),
                }
                for i in items
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.cerrar()


@router.post('/facturas/{cdc}/consultar', summary="Consultar estado en SIFEN")
async def consultar_sifen(cdc: str):
    """
    Consulta el estado del documento directamente en SIFEN.
    Si SIFEN no es accesible (error de red/conexión), devuelve los datos de la BD local.

    **Códigos de respuesta SIFEN:**
    - `0422` — DE aprobado (incluye número de protocolo)
    - `0420` — DE no existe o fue rechazado
    - `0160` — DE no encontrado (puede ocurrir si la IP no está habilitada en DataPower)
    """
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")

    # 1. Leer BD local
    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        fila = repo.obtener_por_cdc(cdc)
        db.cerrar()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not fila:
        raise HTTPException(status_code=404, detail="Documento no encontrado en la BD")

    fila = dict(fila) if hasattr(fila, 'keys') else fila

    # 2. Consultar SIFEN — si responde (cualquier código), usamos esa respuesta
    resp_sifen = None
    error_conexion = None
    try:
        client = SifenSOAPClient(get_sifen_config())
        try:
            resp_sifen = client.consultar_de(cdc)
        except Exception:
            resp_sifen = client.consultar_de_directo(cdc)
    except Exception as e:
        error_conexion = str(e)
        logger.warning(f"No se pudo conectar a SIFEN para consultar {cdc}: {e}")

    # 3. Si SIFEN respondió con 0422/0420, actualizar BD
    if resp_sifen and resp_sifen.codigo in ('0422', '0420'):
        try:
            db2 = Conexion()
            db2.conectar()
            repo2 = RepositorioDE(db2)
            repo2.actualizar_estado_consulta(
                cdc=cdc,
                codigo=resp_sifen.codigo,
                descripcion=resp_sifen.descripcion,
                protocolo=resp_sifen.raw.get('protocolo'),
                respuesta_xml=resp_sifen.raw.get('xml'),
            )
            db2.cerrar()
            fila['estado'] = 'aprobado' if resp_sifen.codigo == '0422' else 'rechazado'
        except Exception:
            pass

    # 4. Construir respuesta — priorizar datos de SIFEN sobre BD local
    if resp_sifen:
        codigo    = resp_sifen.codigo
        descripcion = resp_sifen.descripcion
        protocolo   = resp_sifen.raw.get('protocolo') or fila.get('protocolo_autorizacion')
        fuente      = 'sifen'
    else:
        codigo      = fila.get('codigo_sifen', '')
        descripcion = fila.get('descripcion_sifen', '')
        protocolo   = fila.get('protocolo_autorizacion')
        fuente      = 'bd_local'

    estado_labels = {
        'aprobado': 'Aprobado', 'rechazado': 'Rechazado',
        'cancelado': 'Cancelado', 'pendiente': 'Pendiente',
    }

    return {
        "cdc":                    cdc,
        "estado":                 fila.get('estado', ''),
        "estado_sifen":           estado_labels.get(fila.get('estado', ''), fila.get('estado', '')),
        "codigo_sifen":           codigo,
        "descripcion":            descripcion,
        "protocolo_autorizacion": protocolo,
        "fuente":                 fuente,
        "error_conexion":         error_conexion,
    }


@router.get('/resumen', summary="Resumen de documentos por estado")
async def resumen():
    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        estados = repo.resumen_estados()
        return {"estados": estados, "total": sum(estados.values())}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.cerrar()
