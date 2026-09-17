"""Endpoints para Nota de Crédito (NCE) y Nota de Remisión (NRE)."""
import re
import random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.services.signer import XMLSigner
from sifen_py.services.soap_client import SifenSOAPClient
from sifen_py.generators.kude import KuDEGenerator
from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE

from app.config_manager import get_sifen_config, load_config
from app.api.auth import require_api_key
from app.api.schemas import NotaCreditoRequest, NotaRemisionRequest, FacturaResponse

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
        "condicion": {
            "tipo": req.condicion_pago.tipo,
            "entregas": [{
                "tipo": int(req.condicion_pago.forma_pago),
                "monto": str(monto_pago),
                "moneda": "PYG",
                "monedaDescripcion": "Guarani",
                "cambio": 0.0,
            }],
        },
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

    # 1. Número de documento desde BD
    db   = Conexion()
    repo = None
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo       = RepositorioDE(db)
        numero_doc = repo.proximo_numero_doc()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {e}")

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

    # 5. Guardar como pendiente
    soap_env = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">'
        '<env:Header/><env:Body>'
        '<rEnviDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
        f'<dId>1</dId><xDE>{xml_firmado}</xDE>'
        '</rEnviDe></env:Body></env:Envelope>'
    )
    total = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    try:
        repo.guardar_pendiente(
            cdc=cdc,
            numero_doc=numero_doc,
            tipo_documento=5,
            xml_firmado=xml_firmado,
            soap_envelope=soap_env,
            ruc_receptor=req.receptor.ruc,
            razon_social_receptor=req.receptor.razon_social,
            monto_total=total,
            data_documento={**data, 'timbrado': cfg['timbrado_numero']},
        )
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error guardando en BD: {e}")

    # 6. Enviar a SIFEN
    try:
        client    = SifenSOAPClient(sifen_config)
        respuesta = client.enviar_de_directo(xml_firmado)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=502, detail=f"Error enviando a SIFEN: {e}")

    # 7. Actualizar BD
    try:
        repo.actualizar_respuesta(
            cdc=cdc,
            codigo=respuesta.codigo,
            descripcion=respuesta.descripcion,
            respuesta_xml=respuesta.raw.get('xml', ''),
            protocolo=respuesta.raw.get('protocolo'),
        )
    except Exception:
        pass
    finally:
        db.cerrar()

    estado = 'aprobado' if respuesta.codigo in ('0260', '1001') else 'rechazado'
    return FacturaResponse(
        cdc=cdc,
        numero_doc=numero_doc,
        estado=estado,
        codigo_sifen=respuesta.codigo,
        descripcion_sifen=respuesta.descripcion,
        protocolo_autorizacion=respuesta.raw.get('protocolo'),
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
    """Flujo común: XML → firma → BD → SIFEN → respuesta."""
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

    soap_env = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">'
        '<env:Header/><env:Body>'
        '<rEnviDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
        f'<dId>1</dId><xDE>{xml_firmado}</xDE>'
        '</rEnviDe></env:Body></env:Envelope>'
    )

    try:
        repo.guardar_pendiente(
            cdc=cdc,
            numero_doc=numero_doc,
            tipo_documento=tipo_doc,
            xml_firmado=xml_firmado,
            soap_envelope=soap_env,
            ruc_receptor=ruc_receptor,
            razon_social_receptor=razon_social_receptor,
            monto_total=None,
            data_documento={**data, 'timbrado': cfg['timbrado_numero']},
        )
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error guardando en BD: {e}")

    try:
        client    = SifenSOAPClient(sifen_config)
        respuesta = client.enviar_de_directo(xml_firmado)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=502, detail=f"Error enviando a SIFEN: {e}")

    try:
        repo.actualizar_respuesta(
            cdc=cdc,
            codigo=respuesta.codigo,
            descripcion=respuesta.descripcion,
            respuesta_xml=respuesta.raw.get('xml', ''),
            protocolo=respuesta.raw.get('protocolo'),
        )
    except Exception:
        pass
    finally:
        db.cerrar()

    estado = 'aprobado' if respuesta.codigo in ('0260', '1001') else 'rechazado'
    return FacturaResponse(
        cdc=cdc,
        numero_doc=numero_doc,
        estado=estado,
        codigo_sifen=respuesta.codigo,
        descripcion_sifen=respuesta.descripcion,
        protocolo_autorizacion=respuesta.raw.get('protocolo'),
        kude_url=f"/api/v1/facturas/{cdc}/kude",
        fecha_envio=datetime.now(),
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
        numero_doc = repo.proximo_numero_doc()
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
