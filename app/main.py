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

# sifen_py debe ser importable desde FacturacionElectronica/
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.facturas import router as facturas_router
from app.api.consultas import router as consultas_router
from app.api.notas import router as notas_router
from app.web.dashboard import router as dashboard_router
from app.web.configuracion import router as config_router
from app.web.emision import router as emision_router

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(facturas_router)
app.include_router(notas_router)
app.include_router(consultas_router)
app.include_router(dashboard_router)
app.include_router(config_router)
app.include_router(emision_router)

static_dir = Path(__file__).parent / 'static'
static_dir.mkdir(exist_ok=True)
app.mount('/static', StaticFiles(directory=str(static_dir)), name='static')


@app.get('/api/health', tags=['Sistema'])
async def health():
    return {"status": "ok", "version": "2.0.0"}
