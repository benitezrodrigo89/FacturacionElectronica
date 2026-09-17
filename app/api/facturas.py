"""Endpoint principal: emisión de facturas electrónicas."""
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
from app.api.schemas import FacturaRequest, FacturaResponse, CancelacionRequest

router = APIRouter(prefix='/api/v1', tags=['Facturas'])

_DESC_PRUEBA = (
    "DOCUMENTO ELECTRONICO SIN VALOR COMERCIAL NI FISCAL"
    " - GENERADO EN AMBIENTE DE PRUEBA"
)


def _build_data(req: FacturaRequest, numero_doc: int, cfg: dict) -> dict:
    total = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    monto_pago = req.condicion_pago.monto or total
    ruc = req.receptor.ruc.strip()
    doc_numero = ruc.split('-')[0] if '-' in ruc else ruc
    es_prueba = cfg.get('ambiente') == 'test'
    codigo_seg = str(random.randint(100_000_000, 999_999_999))

    return {
        "tipoDocumento": 1,
        "establecimiento": cfg['establecimiento'],
        "punto": cfg['punto_expedicion'],
        "numero": numero_doc,
        "codigoSeguridadAleatorio": codigo_seg,
        "descripcion": req.descripcion or "Venta de mercaderías",
        "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tipoEmision": 1,
        "tipoTransaccion": 1,
        "tipoImpuesto": 1,
        "moneda": "PYG",
        "timbrado": cfg['timbrado_numero'],
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
        "factura": {"presencia": 1},
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


@router.post('/facturas', response_model=FacturaResponse, status_code=201,
             summary="Emitir factura electrónica")
async def emitir_factura(req: FacturaRequest, _key: str = Depends(require_api_key)):
    """
    Recibe datos de negocio, genera el XML, firma y envía a SIFEN.
    Devuelve CDC, estado y URL del KuDE en PDF.
    """
    cfg = load_config()
    sifen_config = get_sifen_config()

    # 1. Número de documento desde BD
    db = Conexion()
    repo = None
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo = RepositorioDE(db)
        numero_doc = repo.proximo_numero_doc()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Error de base de datos: {e}")

    # 2. Generar XML via Node.js
    data = _build_data(req, numero_doc, cfg)
    try:
        wrapper = XMLGeneratorWrapper(sifen_config)
        xml_generado = wrapper.generar_xml_de(data)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error generando XML: {e}")

    # 3. Firmar XML
    try:
        signer = XMLSigner(sifen_config)
        xml_firmado = signer.firmar_xml(xml_generado)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=500, detail=f"Error firmando XML: {e}")

    # 4. Extraer CDC del XML firmado
    m = re.search(r'DE Id="([^"]+)"', xml_firmado)
    cdc = m.group(1) if m else ''

    # 5. Guardar como pendiente antes de enviar
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
        client = SifenSOAPClient(sifen_config)
        respuesta = client.enviar_de_directo(xml_firmado)
    except Exception as e:
        db.cerrar()
        raise HTTPException(status_code=502, detail=f"Error enviando a SIFEN: {e}")

    # 7. Actualizar BD con respuesta
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


@router.post('/documentos/{cdc}/cancelar', summary="Cancelar documento electrónico (FE, NCE, NRE)")
@router.post('/facturas/{cdc}/cancelar',   summary="Cancelar factura electrónica (alias)", include_in_schema=False)
async def cancelar_factura(cdc: str, body: CancelacionRequest, _key: str = Depends(require_api_key)):
    """
    Cancela un DE aprobado enviando el evento de cancelación a SIFEN.
    Solo se puede cancelar un documento en estado 'aprobado'.
    """
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")

    # Verificar que existe y está aprobado
    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        fila = repo.obtener_por_cdc(cdc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.cerrar()

    if not fila:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    fila = dict(fila) if hasattr(fila, 'keys') else fila
    if fila.get('estado') != 'aprobado':
        raise HTTPException(
            status_code=422,
            detail=f"Solo se pueden cancelar documentos aprobados. Estado actual: {fila.get('estado')}"
        )

    sifen_config = get_sifen_config()

    # Generar XML del evento de cancelación
    try:
        wrapper = XMLGeneratorWrapper(sifen_config)
        xml_evento = wrapper.generar_xml_evento_cancelacion(cdc, body.motivo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando evento: {e}")

    # Firmar el evento
    try:
        signer = XMLSigner(sifen_config)
        xml_evento_firmado = signer.firmar_xml(xml_evento)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error firmando evento: {e}")

    # Enviar a SIFEN
    try:
        client = SifenSOAPClient(sifen_config)
        respuesta = client.enviar_evento_directo(xml_evento_firmado)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error enviando evento a SIFEN: {e}")

    # Actualizar BD
    try:
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        repo.marcar_cancelado(
            cdc=cdc,
            codigo=respuesta.codigo,
            descripcion=respuesta.descripcion,
            respuesta_xml=respuesta.raw.get('xml', ''),
        )
        db.cerrar()
    except Exception:
        pass

    estado_resultado = 'cancelado' if respuesta.codigo == '0422' else 'pendiente_cancelacion'
    return {
        "cdc": cdc,
        "codigo_sifen": respuesta.codigo,
        "descripcion": respuesta.descripcion,
        "estado": estado_resultado,
    }


@router.get('/facturas/{cdc}/kude', summary="Descargar KuDE en PDF",
            response_class=Response,
            responses={200: {"content": {"application/pdf": {}}}})
async def descargar_kude(cdc: str):
    """Genera y descarga el KuDE en PDF para el documento indicado."""
    import json
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener exactamente 44 dígitos")

    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        fila = repo.obtener_por_cdc(cdc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        db.cerrar()

    if not fila:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    fila = dict(fila) if hasattr(fila, 'keys') else fila
    data_json = fila.get('data_json')
    if not data_json:
        raise HTTPException(status_code=422, detail="Documento sin datos para generar KuDE")

    try:
        data = json.loads(data_json)
    except Exception:
        raise HTTPException(status_code=500, detail="Error leyendo datos del documento")

    estado_map = {'aprobado': 'A', 'rechazado': 'R'}
    estado_kude = estado_map.get(fila.get('estado', ''), 'P')

    try:
        gen = KuDEGenerator(get_sifen_config())
        pdf = gen.generar(
            data=data,
            cdc=cdc,
            estado=estado_kude,
            numero_protocolo=fila.get('protocolo_autorizacion'),
            fecha_procesamiento=str(fila.get('fecha_respuesta') or ''),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generando KuDE: {e}")

    numero = fila.get('numero_doc', cdc[:10])
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="kude_{numero}.pdf"'},
    )
