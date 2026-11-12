"""Endpoints para Nota de Crédito (NCE) y Nota de Remisión (NRE)."""
import re
import random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.services.signer import XMLSigner
from sifen_py.generators.kude import KuDEGenerator
from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE

from app.config_manager import get_sifen_config, load_config
from app.api.facturas import _build_condicion
from app.api.auth import require_api_key
from app.api.schemas import (
    NotaCreditoRequest, NotaRemisionRequest, FacturaResponse,
    NotaDebitoRequest, AutofacturaRequest,
)

router = APIRouter(prefix='/api/v1', tags=['Notas'])

_DESC_PRUEBA = (
    "DOCUMENTO ELECTRONICO SIN VALOR COMERCIAL NI FISCAL"
    " - GENERADO EN AMBIENTE DE PRUEBA"
)

MOTIVOS_NCE = {
    1: 'Devolución y Ajuste de precios',
    2: 'Devolución',
    3: 'Descuento',
    4: 'Bonificación',
    5: 'Crédito incobrable',
    6: 'Recupero de costo',
    7: 'Recupero de gasto',
    8: 'Otros',
}


def _build_data_nce(req: NotaCreditoRequest, numero_doc: int, cfg: dict) -> dict:
    total      = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    monto_pago = req.condicion_pago.monto or total
    ruc        = req.receptor.ruc.strip()
    doc_numero = ruc.split('-')[0] if '-' in ruc else ruc
    es_prueba  = cfg.get('ambiente') == 'test'
    codigo_seg = str(random.randint(100_000_000, 999_999_999))

    data = {
        "tipoDocumento": 5,
        "establecimiento": cfg['establecimiento'],
        "punto": cfg['punto_expedicion'],
        "numero": numero_doc,
        "codigoSeguridadAleatorio": codigo_seg,
        "descripcion": req.descripcion or f"Nota de Crédito — {MOTIVOS_NCE.get(int(req.motivo), 'Otros')}",
        "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tipoEmision": 1,
        "tipoTransaccion": 1,
        "tipoImpuesto": 1,
        "moneda": "PYG",
        "timbrado": cfg['timbrado_numero'],
        "notaCreditoDebito": {
            "motivo": int(req.motivo),
        },
        "cliente": {
            "contribuyente": True,
            "ruc": ruc,
            "razonSocial": req.receptor.razon_social,
            "tipoOperacion": 1,
            "direccion": req.receptor.direccion or "Sin especificar",
            "numeroCasa": "0",
            "departamento": 1,
            "departamentoDescripcion": "ASUNCION",
            "distrito": 1,
            "distritoDescripcion": "ASUNCION (DISTRITO)",
            "ciudad": 1,
            "ciudadDescripcion": "ASUNCION (DISTRITO)",
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
            "tipoContribuyente": 2,
            "documentoTipo": 1,
            "documentoNumero": doc_numero,
            "telefono": req.receptor.telefono or "",
            "email": req.receptor.email or "",
        },
        "usuario": {
            "documentoTipo": 1,
            "documentoNumero": doc_numero,
            "nombre": req.receptor.razon_social,
            "cargo": "Cliente",
        },
        "condicion": _build_condicion(req.condicion_pago, monto_pago),
        "items": [
            {
                "codigo": item.codigo or str(i + 1).zfill(3),
                "descripcion": _DESC_PRUEBA if es_prueba else item.descripcion,
                "cantidad": item.cantidad,
                "precioUnitario": item.precio_unitario,
                "unidadMedida": item.unidad_medida,
                "ivaTipo": 1,
                "ivaBase": 100,
                "iva": int(item.iva),
                "cambio": 0.0,
            }
            for i, item in enumerate(req.items)
        ],
    }

    # Documento de referencia (factura original)
    if req.documento_referencia:
        ref = req.documento_referencia
        data["documentoAsociado"] = [{
            "tipoDocumento": 1,
            "formato":       ref.formato,
            "cdc":           ref.cdc,
            "timbrado":      ref.timbrado or cfg['timbrado_numero'],
            "establecimiento": ref.establecimiento or cfg['establecimiento'],
            "punto":         ref.punto or cfg['punto_expedicion'],
            "numero":        ref.numero or 0,
            "fecha":         ref.fecha or datetime.now().strftime("%Y-%m-%d"),
        }]

    return data


@router.post('/notas-credito', response_model=FacturaResponse, status_code=201,
             summary="Emitir Nota de Crédito Electrónica (NCE)")
async def emitir_nota_credito(req: NotaCreditoRequest, _key: str = Depends(require_api_key)):
    """
    Genera, firma y envía una Nota de Crédito Electrónica (tipo 5) a SIFEN.

    Indicar `documento_referencia` con el CDC de la factura original que se acredita.
    """
    cfg          = load_config()
    sifen_config = get_sifen_config()

    # 1. Número de documento + validación del documento referenciado
    db   = Conexion()
    repo = None
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo       = RepositorioDE(db)
        numero_doc = repo.proximo_numero_doc(tipo_documento=5)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {e}")

    # Verificar que la factura referenciada exista y esté aprobada
    if req.documento_referencia and req.documento_referencia.cdc:
        ref_cdc = req.documento_referencia.cdc
        try:
            doc_ref = repo.obtener_por_cdc(ref_cdc)
        except Exception as e:
            db.cerrar()
            raise HTTPException(status_code=503, detail=f"Error consultando documento referenciado: {e}")

        if doc_ref:
            doc_ref = dict(doc_ref) if hasattr(doc_ref, 'keys') else doc_ref
            estado_ref = doc_ref.get('estado', '')
            if estado_ref != 'aprobado':
                db.cerrar()
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"El documento referenciado (CDC: {ref_cdc}) "
                        f"no está en estado aprobado — estado actual: '{estado_ref}'. "
                        f"No se puede emitir una NCE sobre un documento {estado_ref}."
                    ),
                )
        else:
            # No está en BD local → consultar directamente a SIFEN
            try:
                client_consulta = SifenSOAPClient(sifen_config)
                resp_consulta   = client_consulta.consultar_de_directo(ref_cdc)
            except Exception as e:
                db.cerrar()
                raise HTTPException(
                    status_code=503,
                    detail=f"No se pudo verificar el documento referenciado en SIFEN: {e}",
                )
            if resp_consulta.codigo != '0422':
                db.cerrar()
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"El documento referenciado (CDC: {ref_cdc}) no está aprobado en SIFEN "
                        f"— código: {resp_consulta.codigo}, {resp_consulta.descripcion}."
                    ),
                )
            if resp_consulta.raw.get('cancelado'):
                db.cerrar()
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"El documento referenciado (CDC: {ref_cdc}) está cancelado en SIFEN. "
                        f"No se puede emitir una NCE sobre un documento cancelado."
                    ),
                )

    # 2. Generar XML
    data = _build_data_nce(req, numero_doc, cfg)
    try:
        wrapper      = XMLGeneratorWrapper(sifen_config)
        xml_generado = wrapper.generar_xml_de(data)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error generando XML: {e}")

    # 3. Firmar XML
    try:
        signer     = XMLSigner(sifen_config)
        xml_firmado = signer.firmar_xml(xml_generado)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error firmando XML: {e}")

    # 4. Extraer CDC
    m   = re.search(r'DE Id="([^"]+)"', xml_firmado)
    cdc = m.group(1) if m else ''

    # 5. Guardar en BD — el daemon_enviador se encarga del envío a SIFEN
    total   = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    cdc_ref = req.documento_referencia.cdc if req.documento_referencia else None
    try:
        repo.guardar_pendiente(
            cdc=cdc,
            numero_doc=numero_doc,
            tipo_documento=5,
            xml_firmado=xml_firmado,
            ruc_receptor=req.receptor.ruc,
            razon_social_receptor=req.receptor.razon_social,
            monto_total=total,
            data_documento={**data, 'timbrado': cfg['timbrado_numero']},
            cdc_doc_referenciado=cdc_ref,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando en BD: {e}")
    finally:
        db.cerrar()

    return FacturaResponse(
        cdc=cdc,
        numero_doc=numero_doc,
        estado='pendiente',
        codigo_sifen=None,
        descripcion_sifen='',
        protocolo_autorizacion=None,
        kude_url=f"/api/v1/facturas/{cdc}/kude",
        fecha_envio=datetime.now(),
    )


# ── Nota de Remisión ──────────────────────────────────────────────────────────

MOTIVOS_NRE = {
    1: 'Traslado entre locales del emisor',
    2: 'Traslado a terceros',
    3: 'Exportación',
    4: 'Consignación',
    5: 'Devolución',
    9: 'Otros',
}


def _build_data_nre(req: NotaRemisionRequest, numero_doc: int, cfg: dict) -> dict:
    ruc        = req.receptor.ruc.strip()
    doc_numero = ruc.split('-')[0] if '-' in ruc else ruc
    codigo_seg = str(random.randint(100_000_000, 999_999_999))
    es_prueba  = cfg.get('ambiente') == 'test'
    motivo_str = MOTIVOS_NRE.get(int(req.motivo), 'Otros')

    # Transportista y vehículo
    transporte = {
        "tipo": 1,
        "modTransp": 9,
        "condNego": 1,
    }
    if req.transportista:
        t = req.transportista
        transporte["transportista"] = [{
            "contribuyente": False,
            "nombre": t.nombre,
            "documentoTipo": 5,
            "documentoNumero": t.documento_numero,
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
        }]
        if t.vehiculo:
            transporte["vehiculo"] = {
                "tipo": 1,
                "marca": t.vehiculo.marca or "Sin especificar",
                "documentoNumero": t.vehiculo.matricula,
                "obs": t.vehiculo.matricula,
            }

    return {
        "tipoDocumento": 7,
        "establecimiento": cfg['establecimiento'],
        "punto": cfg['punto_expedicion'],
        "numero": numero_doc,
        "codigoSeguridadAleatorio": codigo_seg,
        "descripcion": req.descripcion or f"Nota de Remisión — {motivo_str}",
        "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tipoEmision": 1,
        "tipoTransaccion": 1,
        "tipoImpuesto": 4,  # 4 = No genera IVA
        "moneda": "PYG",
        "timbrado": cfg['timbrado_numero'],
        # Campos usados por KuDE
        "motivoRemision": motivo_str,
        "origen": req.direccion_origen or cfg.get('direccion', 'Sin especificar'),
        "destino": req.direccion_destino or "Sin especificar",
        "transportista": {
            "nombre": req.transportista.nombre if req.transportista else "Sin especificar",
            "matricula": req.transportista.vehiculo.matricula if (req.transportista and req.transportista.vehiculo) else "Sin matrícula",
        },
        "cliente": {
            "contribuyente": True,
            "ruc": ruc,
            "razonSocial": req.receptor.razon_social,
            "tipoOperacion": 1,
            "direccion": req.receptor.direccion or "Sin especificar",
            "numeroCasa": "0",
            "departamento": 1,
            "departamentoDescripcion": "ASUNCION",
            "distrito": 1,
            "distritoDescripcion": "ASUNCION (DISTRITO)",
            "ciudad": 1,
            "ciudadDescripcion": "ASUNCION (DISTRITO)",
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
            "tipoContribuyente": 2,
            "documentoTipo": 1,
            "documentoNumero": doc_numero,
            "telefono": req.receptor.telefono or "",
            "email": req.receptor.email or "",
        },
        "usuario": {
            "documentoTipo": 1,
            "documentoNumero": doc_numero,
            "nombre": req.receptor.razon_social,
            "cargo": "Cliente",
        },
        "transporte": transporte,
        "items": [
            {
                "codigo": item.codigo or str(i + 1).zfill(3),
                "descripcion": _DESC_PRUEBA if es_prueba else item.descripcion,
                "cantidad": item.cantidad,
                "precioUnitario": item.precio_unitario or 1,
                "unidadMedida": item.unidad_medida,
                "ivaTipo": 1,
                "ivaBase": 100,
                "iva": 0,
                "cambio": 0.0,
            }
            for i, item in enumerate(req.items)
        ],
    }


def _emit_documento(data: dict, tipo_doc: int, cfg: dict, sifen_config,
                    ruc_receptor: str, razon_social_receptor: str) -> FacturaResponse:
    """Flujo común: XML → firma → BD → retorna pendiente.
    El envío a SIFEN lo realiza el daemon_enviador por lote asíncrono."""
    db   = Conexion()
    repo = None
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo       = RepositorioDE(db)
        numero_doc = data['numero']
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {e}")

    try:
        wrapper      = XMLGeneratorWrapper(sifen_config)
        xml_generado = wrapper.generar_xml_de(data)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error generando XML: {e}")

    try:
        signer      = XMLSigner(sifen_config)
        xml_firmado = signer.firmar_xml(xml_generado)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error firmando XML: {e}")

    m   = re.search(r'DE Id="([^"]+)"', xml_firmado)
    cdc = m.group(1) if m else ''

    try:
        repo.guardar_pendiente(
            cdc=cdc,
            numero_doc=numero_doc,
            tipo_documento=tipo_doc,
            xml_firmado=xml_firmado,
            ruc_receptor=ruc_receptor,
            razon_social_receptor=razon_social_receptor,
            monto_total=None,
            data_documento={**data, 'timbrado': cfg['timbrado_numero']},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error guardando en BD: {e}")
    finally:
        db.cerrar()

    return FacturaResponse(
        cdc=cdc,
        numero_doc=numero_doc,
        estado='pendiente',
        codigo_sifen=None,
        descripcion_sifen='',
        protocolo_autorizacion=None,
        kude_url=f"/api/v1/facturas/{cdc}/kude",
        fecha_envio=datetime.now(),
    )


# ── Nota de Débito ────────────────────────────────────────────────────────────

MOTIVOS_NDE = MOTIVOS_NCE  # mismos códigos; el generador usa la misma lista


def _build_data_nde(req: NotaDebitoRequest, numero_doc: int, cfg: dict) -> dict:
    total      = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    monto_pago = req.condicion_pago.monto or total
    ruc        = req.receptor.ruc.strip()
    doc_numero = ruc.split('-')[0] if '-' in ruc else ruc
    es_prueba  = cfg.get('ambiente') == 'test'
    codigo_seg = str(random.randint(100_000_000, 999_999_999))

    data = {
        "tipoDocumento": 6,
        "establecimiento": cfg['establecimiento'],
        "punto": cfg['punto_expedicion'],
        "numero": numero_doc,
        "codigoSeguridadAleatorio": codigo_seg,
        "descripcion": req.descripcion or f"Nota de Débito — {MOTIVOS_NDE.get(int(req.motivo), 'Otros')}",
        "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tipoEmision": 1,
        "tipoTransaccion": 1,
        "tipoImpuesto": 1,
        "moneda": "PYG",
        "timbrado": cfg['timbrado_numero'],
        "notaCreditoDebito": {
            "motivo": int(req.motivo),
        },
        "cliente": {
            "contribuyente": True,
            "ruc": ruc,
            "razonSocial": req.receptor.razon_social,
            "tipoOperacion": 1,
            "direccion": req.receptor.direccion or "Sin especificar",
            "numeroCasa": "0",
            "departamento": 1,
            "departamentoDescripcion": "ASUNCION",
            "distrito": 1,
            "distritoDescripcion": "ASUNCION (DISTRITO)",
            "ciudad": 1,
            "ciudadDescripcion": "ASUNCION (DISTRITO)",
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
            "tipoContribuyente": 2,
            "documentoTipo": 1,
            "documentoNumero": doc_numero,
            "telefono": req.receptor.telefono or "",
            "email": req.receptor.email or "",
        },
        "usuario": {
            "documentoTipo": 1,
            "documentoNumero": doc_numero,
            "nombre": req.receptor.razon_social,
            "cargo": "Cliente",
        },
        "condicion": _build_condicion(req.condicion_pago, monto_pago),
        "items": [
            {
                "codigo": item.codigo or str(i + 1).zfill(3),
                "descripcion": _DESC_PRUEBA if es_prueba else item.descripcion,
                "cantidad": item.cantidad,
                "precioUnitario": item.precio_unitario,
                "unidadMedida": item.unidad_medida,
                "ivaTipo": 1,
                "ivaBase": 100,
                "iva": int(item.iva),
                "cambio": 0.0,
            }
            for i, item in enumerate(req.items)
        ],
    }

    if req.documento_referencia:
        ref = req.documento_referencia
        data["documentoAsociado"] = [{
            "tipoDocumento": 1,
            "formato":       ref.formato,
            "cdc":           ref.cdc,
            "timbrado":      ref.timbrado or cfg['timbrado_numero'],
            "establecimiento": ref.establecimiento or cfg['establecimiento'],
            "punto":         ref.punto or cfg['punto_expedicion'],
            "numero":        ref.numero or 0,
            "fecha":         ref.fecha or datetime.now().strftime("%Y-%m-%d"),
        }]

    return data


@router.post('/notas-debito', response_model=FacturaResponse, status_code=201,
             summary="Emitir Nota de Débito Electrónica (NDE)")
async def emitir_nota_debito(req: NotaDebitoRequest, _key: str = Depends(require_api_key)):
    """
    Genera, firma y envía una Nota de Débito Electrónica (tipo 6) a SIFEN.

    Usada para incrementar el valor de una factura ya emitida (intereses, comisiones, ajustes).
    Indicar `documento_referencia` con el CDC de la factura original.
    """
    cfg          = load_config()
    sifen_config = get_sifen_config()

    db = Conexion()
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo       = RepositorioDE(db)
        numero_doc = repo.proximo_numero_doc(tipo_documento=6)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {e}")
    finally:
        db.cerrar()

    data = _build_data_nde(req, numero_doc, cfg)
    return _emit_documento(
        data=data,
        tipo_doc=6,
        cfg=cfg,
        sifen_config=sifen_config,
        ruc_receptor=req.receptor.ruc,
        razon_social_receptor=req.receptor.razon_social,
    )


# ── Autofactura ────────────────────────────────────────────────────────────────

def _build_data_afe(req: AutofacturaRequest, numero_doc: int, cfg: dict) -> dict:
    total      = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    monto_pago = req.condicion_pago.monto or total
    es_prueba  = cfg.get('ambiente') == 'test'
    codigo_seg = str(random.randint(100_000_000, 999_999_999))
    ruc_emisor = cfg['ruc']
    doc_emisor = ruc_emisor.split('-')[0] if '-' in ruc_emisor else ruc_emisor
    v          = req.vendedor
    c          = req.constancia

    return {
        "tipoDocumento": 4,
        "establecimiento": cfg['establecimiento'],
        "punto": cfg['punto_expedicion'],
        "numero": numero_doc,
        "codigoSeguridadAleatorio": codigo_seg,
        "descripcion": req.descripcion or "Autofactura Electrónica",
        "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tipoEmision": 1,
        "tipoTransaccion": 1,
        "tipoImpuesto": 1,
        "moneda": "PYG",
        "timbrado": cfg['timbrado_numero'],
        # El cliente de la AFE es el propio emisor (la empresa compradora)
        "cliente": {
            "contribuyente": True,
            "ruc": ruc_emisor,
            "razonSocial": cfg.get('razon_social', ''),
            "tipoOperacion": 1,
            "direccion": cfg.get('direccion', 'Sin especificar'),
            "numeroCasa": "0",
            "departamento": cfg.get('departamento', 1),
            "departamentoDescripcion": "ASUNCION",
            "distrito": cfg.get('distrito', 1),
            "distritoDescripcion": "ASUNCION (DISTRITO)",
            "ciudad": cfg.get('ciudad', 1),
            "ciudadDescripcion": "ASUNCION (DISTRITO)",
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
            "tipoContribuyente": 1,
            "documentoTipo": 1,
            "documentoNumero": doc_emisor,
            "telefono": cfg.get('telefono', ''),
            "email": cfg.get('email', ''),
        },
        "usuario": {
            "documentoTipo": 1,
            "documentoNumero": doc_emisor,
            "nombre": cfg.get('razon_social', ''),
            "cargo": "Responsable",
        },
        # Datos del vendedor (persona física no contribuyente)
        "autoFactura": {
            "tipoVendedor":    v.tipo_vendedor,
            "documentoTipo":   v.documento_tipo,
            "documentoNumero": v.documento_numero,
            "nombre":          v.nombre,
            "direccion":       v.direccion,
            "numeroCasa":      v.numero_casa,
            "departamento":    v.departamento,
            "distrito":        v.distrito,
            "ciudad":          v.ciudad,
            "ubicacion": {
                "lugar":        c.lugar,
                "departamento": c.departamento,
                "distrito":     c.distrito,
                "ciudad":       c.ciudad,
            },
        },
        # Constancia de no ser contribuyente
        "documentoAsociado": [{
            "constanciaNumero":  c.constancia_numero,
            "constanciaControl": c.constancia_control,
        }],
        "condicion": _build_condicion(req.condicion_pago, monto_pago),
        "items": [
            {
                "codigo": item.codigo or str(i + 1).zfill(3),
                "descripcion": _DESC_PRUEBA if es_prueba else item.descripcion,
                "cantidad": item.cantidad,
                "precioUnitario": item.precio_unitario,
                "unidadMedida": item.unidad_medida,
                "ivaTipo": 1,
                "ivaBase": 100,
                "iva": int(item.iva),
                "cambio": 0.0,
            }
            for i, item in enumerate(req.items)
        ],
    }


@router.post('/autofacturas', response_model=FacturaResponse, status_code=201,
             summary="Emitir Autofactura Electrónica (AFE)")
async def emitir_autofactura(req: AutofacturaRequest, _key: str = Depends(require_api_key)):
    """
    Genera, firma y envía una Autofactura Electrónica (tipo 4) a SIFEN.

    Usada cuando la empresa compra a una persona física no contribuyente.
    El `vendedor` es la persona física que vendió, y la `constancia` es la
    Constancia de No ser Contribuyente que entregó el vendedor.
    """
    cfg          = load_config()
    sifen_config = get_sifen_config()

    db = Conexion()
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo       = RepositorioDE(db)
        numero_doc = repo.proximo_numero_doc(tipo_documento=4)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {e}")
    finally:
        db.cerrar()

    data = _build_data_afe(req, numero_doc, cfg)
    return _emit_documento(
        data=data,
        tipo_doc=4,
        cfg=cfg,
        sifen_config=sifen_config,
        ruc_receptor=cfg['ruc'],
        razon_social_receptor=cfg.get('razon_social', ''),
    )


@router.post('/notas-remision', response_model=FacturaResponse, status_code=201,
             summary="Emitir Nota de Remisión Electrónica (NRE)")
async def emitir_nota_remision(req: NotaRemisionRequest, _key: str = Depends(require_api_key)):
    """
    Genera, firma y envía una Nota de Remisión Electrónica (tipo 7) a SIFEN.

    Usada para traslado de mercaderías. Los ítems no requieren precio.
    Incluir `transportista` con matrícula del vehículo cuando corresponda.
    """
    cfg          = load_config()
    sifen_config = get_sifen_config()

    db = Conexion()
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo       = RepositorioDE(db)
        numero_doc = repo.proximo_numero_doc(tipo_documento=7)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {e}")
    finally:
        db.cerrar()

    data = _build_data_nre(req, numero_doc, cfg)
    return _emit_documento(
        data=data,
        tipo_doc=7,
        cfg=cfg,
        sifen_config=sifen_config,
        ruc_receptor=req.receptor.ruc,
        razon_social_receptor=req.receptor.razon_social,
    )
