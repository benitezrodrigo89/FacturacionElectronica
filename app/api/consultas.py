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
    Devuelve el estado del documento desde la BD local.
    Intenta enriquecer con datos frescos de SIFEN si el servicio de consulta
    es accesible; si no, devuelve lo que hay en la BD.
    """
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")

    # 1. Leer siempre desde la BD primero
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

    # 2. Intentar consulta en SIFEN como enriquecimiento (no falla si no funciona)
    resp_sifen = None
    try:
        client = SifenSOAPClient(get_sifen_config())
        try:
            logger.info("Intentando consultar_de (zeep)...")
            resp_sifen = client.consultar_de(cdc)
            logger.info(f"consultar_de (zeep) exitoso: {resp_sifen.codigo}")
        except Exception as e_zeep:
            logger.warning(f"consultar_de (zeep) falló: {e_zeep}. Usando directo.")
            resp_sifen = client.consultar_de_directo(cdc)

        if resp_sifen and resp_sifen.codigo in ('0422', '0420'):
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
        pass  # SIFEN no accesible — se retorna solo la info de BD

    estado_sifen_map = {
        'aprobado':   'Aprobado',
        'rechazado':  'Rechazado',
        'cancelado':  'Cancelado',
        'pendiente':  'Pendiente',
    }

    return {
        "cdc":                   cdc,
        "estado":                fila.get('estado', ''),
        "estado_sifen":          estado_sifen_map.get(fila.get('estado', ''), fila.get('estado', '')),
        "codigo_sifen":          resp_sifen.codigo if resp_sifen else fila.get('codigo_sifen', ''),
        "descripcion":           resp_sifen.descripcion if resp_sifen else fila.get('descripcion_sifen', ''),
        "protocolo_autorizacion": resp_sifen.raw.get('protocolo') if resp_sifen else fila.get('protocolo_autorizacion'),
        "fuente":                "sifen" if resp_sifen and resp_sifen.codigo not in ('0160', 'ERR') else "bd_local",
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
