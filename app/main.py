"""
Punto de entrada de la aplicación SIFEN Paraguay.

Arrancar:
    cd FacturacionElectronica
    uvicorn app.main:app --reload --port 8000

Documentación API: http://localhost:8000/api/docs
Dashboard web:     http://localhost:8000
"""
import sys
from pathlib import Path
from loguru import logger

# sifen_py debe ser importable desde FacturacionElectronica/
sys.path.insert(0, str(Path(__file__).parent.parent))

# Log a archivo — rota a 10 MB, guarda 7 días
_LOG_FILE = Path(__file__).parent.parent / 'logs' / 'sifen.log'
_LOG_FILE.parent.mkdir(exist_ok=True)
logger.add(
    str(_LOG_FILE),
    rotation='10 MB',
    retention='7 days',
    level='DEBUG',
    encoding='utf-8',
    format='{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}',
)

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.api.facturas import router as facturas_router
from app.api.consultas import router as consultas_router
from app.api.notas import router as notas_router
from app.api.catalogos import router as catalogos_router
from app.web.dashboard import router as dashboard_router
from app.web.configuracion import router as config_router
from app.web.emision import router as emision_router
from app.web.clientes import router as clientes_router
from app.web.productos import router as productos_router
from app.web.reenvio import router as reenvio_router

class EncodingFixMiddleware(BaseHTTPMiddleware):
    """
    Si el body llega en Latin-1/ANSI (común en Genexus sin charset explícito),
    lo re-codifica a UTF-8 antes de que FastAPI intente parsearlo como JSON.
    """
    async def dispatch(self, request: Request, call_next):
        content_type = request.headers.get('content-type', '')
        if 'application/json' in content_type and 'utf-8' not in content_type.lower():
            body = await request.body()
            if body:
                try:
                    body.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        body = body.decode('latin-1').encode('utf-8')
                        # Reconstruir el request con el body corregido
                        async def new_receive():
                            return {'type': 'http.request', 'body': body, 'more_body': False}
                        request = Request(request.scope, new_receive)
                    except Exception:
                        pass
        return await call_next(request)


app = FastAPI(
    title="SIFEN Paraguay — Facturación Electrónica",
    description=(
        "API de integración y webapp para facturación electrónica SIFEN Paraguay.\n\n"
        "**Autenticación:** incluir header `X-API-Key` en los endpoints de emisión.\n\n"
        "**Repositorio:** https://github.com/benitezrodrigo89/FacturacionElectronica"
    ),
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

app.add_middleware(EncodingFixMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(facturas_router)
app.include_router(notas_router)
app.include_router(consultas_router)
app.include_router(catalogos_router)
app.include_router(dashboard_router)
app.include_router(config_router)
app.include_router(emision_router)
app.include_router(clientes_router)
app.include_router(productos_router)
app.include_router(reenvio_router)

static_dir = Path(__file__).parent / 'static'
static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')


@app.get('/api/health', tags=['Sistema'])
async def health():
    return {"status": "ok", "version": "2.0.0"}
