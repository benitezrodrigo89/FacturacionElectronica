from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Optional

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE
from app.config_manager import get_api_keys

router = APIRouter(tags=['Web'])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / 'templates'))


def _rows(filas) -> list:
    return [dict(f) if hasattr(f, 'keys') else f for f in (filas or [])]


@router.get('/', response_class=HTMLResponse)
async def index(request: Request):
    keys    = get_api_keys()
    api_key = keys[0] if keys else ''
    return templates.TemplateResponse(request, 'dashboard.html', {'api_key': api_key})


@router.get('/facturas/aprobadas-por-ruc', response_class=HTMLResponse)
async def facturas_aprobadas_por_ruc(request: Request, ruc: str = ''):
    """Fragmento HTMX: lista de FE aprobadas de un receptor para seleccionar en NCE."""
    facturas = []
    if ruc.strip():
        try:
            db = Conexion()
            db.conectar()
            repo = RepositorioDE(db)
            filas = _rows(repo.listar_aprobadas_por_ruc(ruc.strip()))
            db.cerrar()
            for f in filas:
                estab  = str(f.get('establecimiento', '001')).zfill(3)
                punto  = str(f.get('punto_expedicion', '001')).zfill(3)
                numero = str(f.get('numero_doc', 1)).zfill(7)
                monto  = int(f.get('monto_total') or 0)
                fecha  = f['fecha_emision'].strftime('%d/%m/%Y') if f.get('fecha_emision') else '—'
                facturas.append({
                    'cdc':    f['cdc'],
                    'nro':    f"{estab}-{punto}-{numero}",
                    'monto':  monto,
                    'monto_str': f"Gs. {monto:,}".replace(',', '.'),
                    'fecha':  fecha,
                })
        except Exception:
            pass
    return templates.TemplateResponse(request, '_facturas_selector.html',
                                      {'facturas': facturas, 'ruc': ruc})


@router.get('/documentos-tabla', response_class=HTMLResponse)
async def tabla_documentos(
    request: Request,
    estado: Optional[str] = Query(None),
    periodo: str = Query('hoy'),
    limit: int = Query(100),
):
    """Fragmento HTMX: resumen + tabla de documentos."""
    docs = []
    resumen = {}
    resumen_tipo = {}
    docs_ref = {}
    error = None
    try:
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        docs = _rows(
            repo.listar_por_estado(estado, limite=limit, periodo=periodo)
            if estado else
            repo.listar_recientes(limite=limit, periodo=periodo)
        )
        resumen = repo.resumen_estados(periodo=periodo)
        resumen_tipo = repo.resumen_por_tipo(periodo=periodo)

        # Para cada FE/NDE/etc., buscar si tiene NCE/NDE asociada
        for doc in docs:
            cdc = doc.get('cdc')
            if cdc:
                asociados = _rows(repo.obtener_docs_referenciados_por(cdc))
                if asociados:
                    docs_ref[cdc] = asociados

        db.cerrar()
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(request, '_tabla_docs.html', {
        "docs": docs,
        "docs_ref": docs_ref,
        "resumen": resumen,
        "resumen_tipo": resumen_tipo,
        "estado_filtro": estado,
        "periodo": periodo,
        "error": error,
    })
