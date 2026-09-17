from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
from typing import Optional

from app.config_manager import load_config, save_config

router = APIRouter(tags=['Web'])
templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / 'templates'))


@router.get('/configuracion', response_class=HTMLResponse)
async def ver_configuracion(request: Request):
    return templates.TemplateResponse(request, 'configuracion.html', {
        "cfg": load_config(),
        "guardado": False,
        "error": None,
    })


@router.post('/configuracion', response_class=HTMLResponse)
async def guardar_configuracion(
    request: Request,
    ambiente: str = Form(...),
    ruc: str = Form(...),
    razon_social: str = Form(...),
    nombre_fantasia: str = Form(''),
    actividad_economica_codigo: str = Form(''),
    actividad_economica_descripcion: str = Form(''),
    tipo_contribuyente: int = Form(2),
    tipo_regimen: int = Form(8),
    establecimiento: str = Form('001'),
    establecimiento_denominacion: str = Form('Casa Central'),
    punto_expedicion: str = Form('001'),
    departamento: int = Form(1),
    departamento_descripcion: str = Form(''),
    distrito: int = Form(1),
    distrito_descripcion: str = Form(''),
    ciudad: int = Form(1),
    ciudad_descripcion: str = Form(''),
    numero_casa: str = Form('0'),
    direccion: str = Form(''),
    telefono: str = Form(''),
    email: str = Form(''),
    certificado_path: str = Form('certificado_sifen.pfx'),
    certificado_password: str = Form(''),
    csc: str = Form(''),
    csc_id: str = Form('0001'),
    timbrado_numero: str = Form(''),
    timbrado_fecha: str = Form(''),
):
    error = None
    try:
        save_config({
            "ambiente": ambiente,
            "ruc": ruc.strip(),
            "razon_social": razon_social.strip(),
            "nombre_fantasia": nombre_fantasia.strip(),
            "actividad_economica_codigo": actividad_economica_codigo.strip(),
            "actividad_economica_descripcion": actividad_economica_descripcion.strip(),
            "tipo_contribuyente": tipo_contribuyente,
            "tipo_regimen": tipo_regimen,
            "establecimiento": establecimiento.strip(),
            "establecimiento_denominacion": establecimiento_denominacion.strip(),
            "punto_expedicion": punto_expedicion.strip(),
            "departamento": departamento,
            "departamento_descripcion": departamento_descripcion.strip(),
            "distrito": distrito,
            "distrito_descripcion": distrito_descripcion.strip(),
            "ciudad": ciudad,
            "ciudad_descripcion": ciudad_descripcion.strip(),
            "numero_casa": numero_casa.strip(),
            "direccion": direccion.strip(),
            "telefono": telefono.strip(),
            "email": email.strip(),
            "certificado_path": certificado_path.strip(),
            "certificado_password": certificado_password,
            "csc": csc.strip(),
            "csc_id": csc_id.strip(),
            "timbrado_numero": timbrado_numero.strip(),
            "timbrado_fecha": timbrado_fecha.strip(),
        })
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(request, 'configuracion.html', {
        "cfg": load_config(),
        "guardado": error is None,
        "error": error,
    })
