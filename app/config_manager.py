"""Manejo centralizado de la configuración del emisor."""
import json
from pathlib import Path
from typing import Optional

from sifen_py.core.config import SifenConfig

BASE_DIR = Path(__file__).parent.parent
CONFIG_PATH = BASE_DIR / 'config.json'

_DEFAULTS = {
    "ambiente": "test",
    "ruc": "",
    "razon_social": "",
    "nombre_fantasia": "",
    "tipo_contribuyente": 2,
    "tipo_regimen": 8,
    "actividad_economica_codigo": "",
    "actividad_economica_descripcion": "",
    "certificado_path": "certificado_sifen.pfx",
    "certificado_password": "",
    "csc": "",
    "csc_id": "0001",
    "timbrado_numero": "",
    "timbrado_fecha": "",
    "establecimiento": "001",
    "establecimiento_denominacion": "Casa Central",
    "punto_expedicion": "001",
    "departamento": 1,
    "departamento_descripcion": "ASUNCION",
    "distrito": 1,
    "distrito_descripcion": "ASUNCION (DISTRITO)",
    "ciudad": 1,
    "ciudad_descripcion": "ASUNCION (DISTRITO)",
    "numero_casa": "0",
    "direccion": "",
    "telefono": "",
    "email": "",
    "api_keys": [],
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(_DEFAULTS)
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return {**_DEFAULTS, **data}


def save_config(updates: dict) -> None:
    current = load_config()
    current.update(updates)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(current, f, ensure_ascii=False, indent=2)


def get_sifen_config() -> SifenConfig:
    c = load_config()
    return SifenConfig(
        ambiente=c['ambiente'],
        ruc=c['ruc'],
        razon_social=c['razon_social'],
        nombre_fantasia=c.get('nombre_fantasia', c['razon_social']),
        certificado_path=c['certificado_path'],
        certificado_password=c['certificado_password'],
        csc=c['csc'],
        csc_id=c['csc_id'],
        timbrado_numero=c['timbrado_numero'],
        timbrado_fecha=c['timbrado_fecha'],
        establecimiento=c['establecimiento'],
        punto_expedicion=c['punto_expedicion'],
        departamento=c['departamento'],
        distrito=c['distrito'],
        ciudad=c['ciudad'],
        actividad_economica=c.get('actividad_economica_descripcion', ''),
        direccion=c.get('direccion', ''),
        telefono=c.get('telefono', ''),
        email=c.get('email', ''),
    )


def get_api_keys() -> list:
    return load_config().get('api_keys', [])
