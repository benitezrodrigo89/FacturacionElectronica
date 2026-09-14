"""
API REST para consultas de documentos electrónicos SIFEN.

Endpoints:
    GET  /de                     Listar documentos (filtro por estado, limit)
    GET  /de/ultimo              Último documento enviado
    GET  /de/{cdc}               Documento por CDC (desde BD)
    POST /de/{cdc}/consultar     Consultar en SIFEN y actualizar BD
    GET  /resumen                Conteo de documentos por estado

Arrancar:
    cd FacturacionElectronica
    uvicorn api.main:app --reload --port 8000

Documentación interactiva: http://localhost:8000/docs
"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'sifen_py'))

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE
from sifen_py.core.config import SifenConfig
from sifen_py.services.soap_client import SifenSOAPClient

from .schemas import DocumentoResponse, DocumentoListItem, ConsultaSifenResponse, ResumenResponse

# ── Configuración SIFEN (leída de variables de entorno o valores por defecto) ──
CERT_PATH     = os.getenv('SIFEN_CERT_PATH',     'certificado_sifen.pfx')
CERT_PASSWORD = os.getenv('SIFEN_CERT_PASSWORD', 'ferreteria2026.')
RUC           = os.getenv('SIFEN_RUC',           '5722781-0')
CSC           = os.getenv('SIFEN_CSC',           'ABCD0000000000000000000000000000')
CSC_ID        = os.getenv('SIFEN_CSC_ID',        '0001')
TIMBRADO      = os.getenv('SIFEN_TIMBRADO',      '05722781')
TIMBRADO_FECHA = os.getenv('SIFEN_TIMBRADO_FECHA', '2026-06-02')
AMBIENTE      = os.getenv('SIFEN_AMBIENTE',      'test')
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="SIFEN Paraguay — API de Documentos Electrónicos",
    description="Consulta y gestión de documentos electrónicos enviados a SIFEN.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_repo() -> RepositorioDE:
    db = Conexion()
    db.conectar()
    return RepositorioDE(db)


def get_sifen_client() -> SifenSOAPClient:
    config = SifenConfig(
        ambiente=AMBIENTE,
        ruc=RUC,
        razon_social='AMARILLA ORTIZ OSVALDO MATHIAS ANTONIO',
        nombre_fantasia='AMARILLA ORTIZ',
        certificado_path=CERT_PATH,
        certificado_password=CERT_PASSWORD,
        csc=CSC,
        csc_id=CSC_ID,
        timbrado_numero=TIMBRADO,
        timbrado_fecha=TIMBRADO_FECHA,
        establecimiento='001',
        punto_expedicion='001',
        departamento=1,
        distrito=1,
        ciudad=1,
    )
    return SifenSOAPClient(config)


def fila_a_dict(row) -> dict:
    """Convierte una fila psycopg2 (RealDictRow o tuple) a dict."""
    if row is None:
        return None
    if hasattr(row, 'keys'):
        return dict(row)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/de", response_model=List[DocumentoListItem], summary="Listar documentos")
def listar_documentos(
    estado: Optional[str] = Query(None, description="Filtrar por estado: aprobado, rechazado, pendiente"),
    limit:  int           = Query(20,   description="Cantidad máxima de resultados", ge=1, le=200),
):
    """
    Devuelve la lista de documentos enviados a SIFEN.
    Filtrá por estado con el parámetro `?estado=aprobado`.
    """
    repo = get_repo()
    try:
        if estado:
            filas = repo.listar_por_estado(estado, limite=limit)
        else:
            filas = repo.listar_recientes(limite=limit)
        return [fila_a_dict(f) for f in filas]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        repo.db.cerrar()


@app.get("/de/ultimo", response_model=DocumentoListItem, summary="Último documento enviado")
def ultimo_documento():
    """Devuelve el último documento registrado en la base de datos."""
    repo = get_repo()
    try:
        fila = repo.ultimo_enviado()
        if not fila:
            raise HTTPException(status_code=404, detail="No hay documentos en la base de datos")
        return fila_a_dict(fila)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        repo.db.cerrar()


@app.get("/de/{cdc}", response_model=DocumentoResponse, summary="Documento por CDC")
def obtener_documento(cdc: str):
    """
    Devuelve los datos completos de un documento por su CDC (44 dígitos).
    Consulta solo la base de datos local — no llama a SIFEN.
    Para forzar una consulta en SIFEN usá POST /de/{cdc}/consultar.
    """
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="El CDC debe tener exactamente 44 dígitos")
    repo = get_repo()
    try:
        fila = repo.obtener_por_cdc(cdc)
        if not fila:
            raise HTTPException(status_code=404, detail=f"No se encontró el documento con CDC: {cdc}")
        return fila_a_dict(fila)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        repo.db.cerrar()


@app.post("/de/{cdc}/consultar", response_model=ConsultaSifenResponse, summary="Consultar estado en SIFEN")
def consultar_en_sifen(cdc: str):
    """
    Consulta el estado real de un documento directamente en SIFEN por su CDC
    y actualiza la base de datos con el resultado.

    Códigos de respuesta SIFEN:
    - **0422** → Aprobado (incluye número de protocolo)
    - **0420** → No existe o fue rechazado
    """
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="El CDC debe tener exactamente 44 dígitos")

    if not os.path.exists(CERT_PATH):
        raise HTTPException(
            status_code=503,
            detail=f"Certificado no encontrado: {CERT_PATH}. Configurá SIFEN_CERT_PATH."
        )

    try:
        client = get_sifen_client()
        respuesta = client.consultar_de_directo(cdc)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error al consultar SIFEN: {e}")

    # Actualizar BD si hay registro
    estado_bd = None
    try:
        repo = get_repo()
        fila = repo.obtener_por_cdc(cdc)
        if fila and respuesta.codigo in ('0422', '0420'):
            repo.actualizar_estado_consulta(
                cdc=cdc,
                codigo=respuesta.codigo,
                descripcion=respuesta.descripcion,
                protocolo=respuesta.raw.get('protocolo'),
                respuesta_xml=respuesta.raw.get('xml'),
            )
            estado_bd = 'aprobado' if respuesta.codigo == '0422' else 'rechazado'
        repo.db.cerrar()
    except Exception:
        pass

    return ConsultaSifenResponse(
        cdc=cdc,
        codigo_sifen=respuesta.codigo,
        descripcion=respuesta.descripcion,
        estado_sifen=respuesta.raw.get('estado'),
        protocolo_autorizacion=respuesta.raw.get('protocolo'),
        fecha_procesamiento=respuesta.raw.get('fecha'),
        estado_bd=estado_bd,
    )


@app.get("/resumen", response_model=ResumenResponse, summary="Resumen de estados")
def resumen_estados():
    """Devuelve el conteo de documentos agrupado por estado."""
    repo = get_repo()
    try:
        estados = repo.resumen_estados()
        return ResumenResponse(
            estados=estados,
            total=sum(estados.values()),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        repo.db.cerrar()


@app.get("/", include_in_schema=False)
def root():
    return {"mensaje": "SIFEN API activa", "docs": "/docs"}
