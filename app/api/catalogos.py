"""Endpoints de catálogos SIFEN (solo lectura)."""
from fastapi import APIRouter, HTTPException

from sifen_py.core.constants import (
    CATALOGO_TIPOS_DOCUMENTO,
    CATALOGO_FORMAS_PAGO,
    CATALOGO_MONEDAS,
    CATALOGO_TASAS_IVA,
    CATALOGO_CONDICION_PAGO,
    CATALOGO_MOTIVOS_NCE,
    CATALOGO_FORMATO_DOCUMENTO_ASOCIADO,
    CATALOGO_UNIDADES_MEDIDA,
)

router = APIRouter(prefix='/api/v1/catalogos', tags=['Catálogos'])

_CATALOGOS = {
    'tipos-documento':         CATALOGO_TIPOS_DOCUMENTO,
    'formas-pago':             CATALOGO_FORMAS_PAGO,
    'monedas':                 CATALOGO_MONEDAS,
    'tasas-iva':               CATALOGO_TASAS_IVA,
    'condicion-pago':          CATALOGO_CONDICION_PAGO,
    'motivos-nce':             CATALOGO_MOTIVOS_NCE,
    'formato-documento-asociado': CATALOGO_FORMATO_DOCUMENTO_ASOCIADO,
    'unidades-medida':         CATALOGO_UNIDADES_MEDIDA,
}


@router.get('', summary="Listar catálogos disponibles")
async def listar_catalogos():
    """Devuelve los nombres de todos los catálogos disponibles."""
    return {'catalogos': list(_CATALOGOS.keys())}


@router.get('/{nombre}', summary="Obtener catálogo por nombre")
async def obtener_catalogo(nombre: str):
    """
    Devuelve la lista completa de un catálogo SIFEN.

    **Catálogos disponibles:**
    - `tipos-documento` — FE, NCE, NDE, NRE, AFE
    - `formas-pago` — Efectivo, Tarjeta, Transferencia, etc.
    - `monedas` — PYG, USD, EUR, BRL, ARS
    - `tasas-iva` — 0%, 5%, 10%
    - `condicion-pago` — Contado, Crédito
    - `motivos-nce` — Motivos de Nota de Crédito
    - `formato-documento-asociado` — Electrónico, Impreso, Constancia
    - `unidades-medida` — Todas las unidades del Manual Técnico v150
    """
    catalogo = _CATALOGOS.get(nombre)
    if catalogo is None:
        raise HTTPException(
            status_code=404,
            detail=f"Catálogo '{nombre}' no encontrado. Disponibles: {list(_CATALOGOS.keys())}",
        )
    return {'nombre': nombre, 'total': len(catalogo), 'items': catalogo}
