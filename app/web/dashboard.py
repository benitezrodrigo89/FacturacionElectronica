from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Optional

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE

router = APIRouter(tags=['Web'])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / 'templates'))


def _rows(filas) -> list:
    return [dict(f) if hasattr(f, 'keys') else f for f in (filas or [])]


@router.get('/', response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, 'dashboard.html')


@router.get('/documentos-tabla', response_class=HTMLResponse)
async def tabla_documentos(
    request: Request,
    estado: Optional[str] = Query(None),
    limit: int = Query(50),
):
    """Fragmento HTMX: resumen + tabla de documentos."""
    docs = []
    resumen = {}
    error = None
    try:
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        docs = _rows(repo.listar_por_estado(estado, limite=limit) if estado else repo.listar_recientes(limite=limit))
        resumen = repo.resumen_estados()
        db.cerrar()
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(request, '_tabla_docs.html', {
        "docs": docs,
        "resumen": resumen,
        "estado_filtro": estado,
        "error": error,
    })
