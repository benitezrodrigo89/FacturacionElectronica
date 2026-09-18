"""Endpoints de consulta de documentos."""
from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE
from sifen_py.services.soap_client import SifenSOAPClient

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


@router.post('/facturas/{cdc}/consultar', summary="Consultar estado en SIFEN")
async def consultar_sifen(cdc: str):
    """Consulta el estado real en SIFEN y actualiza la BD."""
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")
    try:
        client = SifenSOAPClient(get_sifen_config())
        # consultar_de usa zeep (carga el WSDL automáticamente) → construye el
        # SOAP correcto sin adivinar el nombre del elemento body.
        # consultar_de_directo es el fallback para cuando el WSDL no es accesible.
        try:
            resp = client.consultar_de(cdc)
        except Exception:
            resp = client.consultar_de_directo(cdc)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error consultando SIFEN: {e}")

    try:
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        if repo.obtener_por_cdc(cdc) and resp.codigo in ('0422', '0420'):
            repo.actualizar_estado_consulta(
                cdc=cdc,
                codigo=resp.codigo,
                descripcion=resp.descripcion,
                protocolo=resp.raw.get('protocolo'),
                respuesta_xml=resp.raw.get('xml'),
            )
        db.cerrar()
    except Exception:
        pass

    return {
        "cdc": cdc,
        "codigo_sifen": resp.codigo,
        "descripcion": resp.descripcion,
        "protocolo_autorizacion": resp.raw.get('protocolo'),
        "estado_sifen": resp.raw.get('estado'),
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
