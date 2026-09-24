from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio_clientes import RepositorioProductos
from sifen_py.core.constants import CATALOGO_UNIDADES_MEDIDA

router = APIRouter(tags=['Web'])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / 'templates'))

_UNIDADES = {u['codigo']: f"{u['representacion']} — {u['descripcion']}"
             for u in CATALOGO_UNIDADES_MEDIDA}


def _db_repo():
    db = Conexion()
    db.crear_base_si_no_existe()
    db.ejecutar_schema()
    return db, RepositorioProductos(db)


@router.get('/productos', response_class=HTMLResponse)
async def lista_productos(request: Request, q: str = ''):
    db, repo = _db_repo()
    try:
        productos = [dict(p) for p in repo.listar(busqueda=q, solo_activos=False)]
    finally:
        db.cerrar()
    for p in productos:
        p['unidad_medida_desc'] = _UNIDADES.get(p['unidad_medida'], str(p['unidad_medida']))
    return templates.TemplateResponse(request, 'productos/lista.html',
                                      {'productos': productos, 'q': q})


@router.get('/productos/nuevo', response_class=HTMLResponse)
async def form_nuevo_producto(request: Request):
    return templates.TemplateResponse(request, 'productos/form.html', {
        'producto': None,
        'titulo': 'Nuevo producto / servicio',
        'unidades': CATALOGO_UNIDADES_MEDIDA,
    })


@router.get('/productos/{producto_id}/editar', response_class=HTMLResponse)
async def form_editar_producto(request: Request, producto_id: int):
    db, repo = _db_repo()
    try:
        producto = repo.obtener(producto_id)
    finally:
        db.cerrar()
    if not producto:
        raise HTTPException(status_code=404, detail="Producto no encontrado")
    return templates.TemplateResponse(request, 'productos/form.html', {
        'producto': dict(producto),
        'titulo': 'Editar producto / servicio',
        'unidades': CATALOGO_UNIDADES_MEDIDA,
    })


@router.post('/productos', response_class=HTMLResponse)
async def crear_producto(
    request: Request,
    descripcion: str = Form(...),
    precio_unitario: int = Form(...),
    iva: int = Form(...),
    unidad_medida: int = Form(77),
    codigo: str = Form(''),
):
    db, repo = _db_repo()
    try:
        repo.crear(descripcion=descripcion, precio_unitario=precio_unitario,
                   iva=iva, unidad_medida=unidad_medida, codigo=codigo)
    finally:
        db.cerrar()
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/productos', status_code=303)


@router.post('/productos/{producto_id}/editar', response_class=HTMLResponse)
async def actualizar_producto(
    request: Request,
    producto_id: int,
    descripcion: str = Form(...),
    precio_unitario: int = Form(...),
    iva: int = Form(...),
    unidad_medida: int = Form(77),
    codigo: str = Form(''),
):
    db, repo = _db_repo()
    try:
        repo.actualizar(producto_id, descripcion=descripcion,
                        precio_unitario=precio_unitario, iva=iva,
                        unidad_medida=unidad_medida, codigo=codigo)
    finally:
        db.cerrar()
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/productos', status_code=303)


@router.post('/productos/{producto_id}/toggle', response_class=HTMLResponse)
async def toggle_producto(request: Request, producto_id: int):
    db, repo = _db_repo()
    try:
        producto = repo.obtener(producto_id)
        if producto:
            repo.cambiar_estado(producto_id, not dict(producto)['activo'])
    finally:
        db.cerrar()
    from fastapi.responses import RedirectResponse
    return RedirectResponse('/productos', status_code=303)


# ── Endpoint HTMX para autocomplete en formularios de emisión ──
@router.get('/productos/buscar', response_class=HTMLResponse)
async def buscar_productos_htmx(request: Request, q: str = ''):
    if len(q) < 2:
        return HTMLResponse('')
    db, repo = _db_repo()
    try:
        resultados = [dict(p) for p in repo.listar(busqueda=q)]
    finally:
        db.cerrar()
    for p in resultados:
        p['unidad_medida_desc'] = _UNIDADES.get(p['unidad_medida'], str(p['unidad_medida']))
    return templates.TemplateResponse(request, 'productos/_resultados.html',
                                      {'resultados': resultados})
