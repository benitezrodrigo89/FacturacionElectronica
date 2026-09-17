from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config_manager import load_config, get_api_keys

router = APIRouter(tags=['Web'])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / 'templates'))


def _ctx(request, extra=None):
    cfg     = load_config()
    keys    = get_api_keys()
    api_key = keys[0] if keys else ''
    base    = {"request": request, "cfg": cfg, "api_key": api_key}
    return {**base, **(extra or {})}


@router.get('/emitir/factura', response_class=HTMLResponse)
async def form_factura(request: Request):
    return templates.TemplateResponse(request, 'emision/factura.html', _ctx(request))


@router.get('/emitir/nota-credito', response_class=HTMLResponse)
async def form_nota_credito(request: Request):
    return templates.TemplateResponse(request, 'emision/nota_credito.html', _ctx(request))


@router.get('/emitir/nota-remision', response_class=HTMLResponse)
async def form_nota_remision(request: Request):
    return templates.TemplateResponse(request, 'emision/nota_remision.html', _ctx(request))
