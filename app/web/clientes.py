from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Optional

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio_clientes import RepositorioClientes

router = APIRouter(tags=['Web'])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / 'templates'))


def _db_repo():
    db = Conexion()
    db.crear_base_si_no_existe()
    db.ejecutar_schema()
    return db, RepositorioClientes(db)


@router.get('/clientes', response_class=HTMLResponse)
async def lista_clientes(request: Request, q: str = ''):
    db, repo = _db_repo()
    try:
        clientes = [dict(c) for c in repo.listar(busqueda=q, solo_activos=False)]
    finally:
        db.cerrar()
    return templates.TemplateResponse(request, 'clientes/lista.html',
                                      {'clientes': clientes, 'q': q})


@router.get('/clientes/nuevo', response_class=HTMLResponse)
async def form_nuevo_cliente(request: Request):
    return templates.TemplateResponse(request, 'clientes/form.html',
                                      {'cliente': None, 'titulo': 'Nuevo cliente'})


@router.get('/clientes/{cliente_id}/editar', response_class=HTMLResponse)
async def form_editar_cliente(request: Request, cliente_id: int):
    db, repo = _db_repo()
    try:
        cliente = repo.obtener(cliente_id)
    finally:
        db.cerrar()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado")
    return templates.TemplateResponse(request, 'clientes/form.html',
                                      {'cliente': dict(cliente), 'titulo': 'Editar cliente'})


@router.post('/clientes', response_class=HTMLResponse)
async def crear_cliente(
    request: Request,
    ruc: str = Form(...),
    razon_social: str = Form(...),
    direccion: str = Form(''),
    telefono: str = Form(''),
    email: str = Form(''),
):
    db, repo = _db_repo()
    try:
        repo.crear(ruc=ruc, razon_social=razon_social,
                   direccion=direccion, telefono=telefono, email=email)
    finally:
        db.cerrar()
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/clientes', status_code=303)


@router.post('/clientes/{cliente_id}/editar', response_class=HTMLResponse)
async def actualizar_cliente(
    request: Request,
    cliente_id: int,
    ruc: str = Form(...),
    razon_social: str = Form(...),
    direccion: str = Form(''),
    telefono: str = Form(''),
    email: str = Form(''),
):
    db, repo = _db_repo()
    try:
        repo.actualizar(cliente_id, ruc=ruc, razon_social=razon_social,
                        direccion=direccion, telefono=telefono, email=email)
    finally:
        db.cerrar()
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/clientes', status_code=303)


@router.post('/clientes/{cliente_id}/toggle', response_class=HTMLResponse)
async def toggle_cliente(request: Request, cliente_id: int):
    db, repo = _db_repo()
    try:
        cliente = repo.obtener(cliente_id)
        if cliente:
            repo.cambiar_estado(cliente_id, not dict(cliente)['activo'])
    finally:
        db.cerrar()
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/clientes', status_code=303)


# ── Endpoint HTMX para autocomplete en formularios de emisión ──
@router.get('/clientes/buscar', response_class=HTMLResponse)
async def buscar_clientes_htmx(request: Request, q: str = ''):
    if len(q) < 2:
        return HTMLResponse('')
    db, repo = _db_repo()
    try:
        resultados = [dict(c) for c in repo.listar(busqueda=q)]
    finally:
        db.cerrar()
    return templates.TemplateResponse(request, 'clientes/_resultados.html',
                                      {'resultados': resultados})
