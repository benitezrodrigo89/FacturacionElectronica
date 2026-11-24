"""Endpoint principal: emisión de facturas electrónicas."""
import re
import random
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.services.signer import XMLSigner
from sifen_py.events.gestor_eventos import GestorEventos
from sifen_py.generators.kude import KuDEGenerator
from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE

from app.config_manager import get_sifen_config, load_config
from app.api.auth import require_api_key
from app.api.schemas import (
    FacturaRequest, FacturaResponse,
    CancelacionRequest, InutilizacionRequest, ConformidadRequest,
)

router = APIRouter(prefix='/api/v1', tags=['Facturas'])

_DESC_PRUEBA = (
    "DOCUMENTO ELECTRONICO SIN VALOR COMERCIAL NI FISCAL"
    " - GENERADO EN AMBIENTE DE PRUEBA"
)


def _build_condicion(condicion_pago, monto_pago: int) -> dict:
    if condicion_pago.entregas:
        entregas_list = [
            {
                "tipo": int(e.forma_pago),
                "monto": str(e.monto),
                "moneda": "PYG",
                "monedaDescripcion": "Guarani",
                "cambio": 0.0,
            }
            for e in condicion_pago.entregas
        ]
    else:
        entregas_list = [{
            "tipo": int(condicion_pago.forma_pago),
            "monto": str(monto_pago),
            "moneda": "PYG",
            "monedaDescripcion": "Guarani",
            "cambio": 0.0,
        }]

    condicion = {
        "tipo": condicion_pago.tipo,
        "entregas": entregas_list,
    }
    if condicion_pago.tipo == 2 and condicion_pago.credito:
        c = condicion_pago.credito
        credito: dict = {"tipo": c.tipo}
        if c.plazo:
            credito["plazo"] = c.plazo
        if c.cuotas is not None:
            credito["cuotas"] = c.cuotas
        if c.info_cuotas:
            credito["info_cuotas"] = [
                {"moneda": q.moneda, "monto": q.monto, "vencimiento": q.vencimiento}
                for q in c.info_cuotas
            ]
        condicion["credito"] = credito
    return condicion


def _build_data(req: FacturaRequest, numero_doc: int, cfg: dict) -> dict:
    total = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    monto_pago = req.condicion_pago.monto or total
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
        "cliente": req.receptor.build_cliente_block(),
        "usuario": req.receptor.build_usuario_block(),
        "factura": {"presencia": 1},
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


@router.post('/facturas', response_model=FacturaResponse, status_code=201,
             summary="Emitir factura electrónica")
async def emitir_factura(req: FacturaRequest, _key: str = Depends(require_api_key)):
    """
    Genera y firma una Factura Electrónica, la guarda en BD como `pendiente` y retorna el CDC.

    **Flujo:** genera XML → firma XMLDSig → guarda en BD → retorna `pendiente`.
    El envío a SIFEN lo realiza el daemon_enviador cada 15 minutos por lote asíncrono.

    **Número de documento (`numero_doc`):**
    - Si se envía, el sistema lo usa directamente. Útil cuando el ERP/POS ya tiene su propia numeración.
    - Si se omite, se asigna automáticamente el próximo número disponible en la BD.
    - Devuelve `409` si el número ya existe en la base de datos.

    **Respuesta:** CDC de 44 dígitos, estado `pendiente`, URL del KuDE en PDF.
    """
    cfg = load_config()
    sifen_config = get_sifen_config()

    # 1. Número de documento — externo o auto-incremento
    db = Conexion()
    repo = None
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo = RepositorioDE(db)
        if req.numero_doc is not None:
            # Verificar que el número no esté ya registrado en la BD
            existente = repo.obtener_por_numero_doc(req.numero_doc, tipo_documento=1)
            if existente:
                db.cerrar()
                raise HTTPException(
                    status_code=409,
                    detail=f"El número de documento {req.numero_doc} ya existe en la base de datos.",
                )
            numero_doc = req.numero_doc
        else:
            numero_doc = repo.proximo_numero_doc()
    except HTTPException:
        raise
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

    # 5. Guardar en BD — el daemon_enviador se encarga del envío a SIFEN
    total = sum(int(i.cantidad * i.precio_unitario) for i in req.items)
    try:
        repo.guardar_pendiente(
            cdc=cdc,
            numero_doc=numero_doc,
            xml_firmado=xml_firmado,
            ruc_receptor=req.receptor.id_para_bd(),
            razon_social_receptor=req.receptor.razon_social,
            monto_total=total,
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

    try:
        gestor = GestorEventos(sifen_config)
        respuesta = gestor.cancelar(cdc=cdc, motivo=body.motivo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando cancelación: {e}")

    # Actualizar BD
    # Actualizar BD solo si SIFEN aceptó el evento (0300 = recibido en cola)
    if respuesta.exitoso:
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

    estado_resultado = 'cancelado' if respuesta.exitoso else 'aprobado'
    return {
        "cdc": cdc,
        "codigo_sifen": respuesta.codigo,
        "descripcion": respuesta.descripcion,
        "estado": estado_resultado,
    }


def _es_error_receptor(codigo: str) -> bool:
    # 0420 = "DE rechazado" genérico (consulta posterior pisa el código original)
    if codigo == '0420':
        return True
    try:
        return int(codigo) >= 1300
    except (ValueError, TypeError):
        return False


@router.post('/documentos/{cdc}/corregir-receptor',
             summary="Corregir datos del receptor en un documento rechazado")
async def corregir_receptor(
    cdc:              str,
    razon_social:     str,
    contribuyente:    str = 'true',
    ruc:              str = '',
    documento_tipo:   int = None,
    documento_numero: str = '',
    direccion:        str = '',
    telefono:         str = '',
    email:            str = '',
    _key: str = Depends(require_api_key),
):
    """
    Corrige los datos del receptor en un DE rechazado por SIFEN con código
    1300-1349 (errores en datos del receptor). Como ningún dato del receptor
    forma parte del CDC, se reutiliza el mismo número de documento y CDC.
    El documento vuelve a estado 'pendiente' para ser reenviado por el daemon.
    Soporta contribuyentes (ruc) y no contribuyentes (documento_tipo/numero).
    """
    import json as _json
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")

    es_contribuyente = contribuyente.lower() != 'false'
    razon_social     = razon_social.strip()

    if es_contribuyente:
        ruc = ruc.strip()
        if not ruc:
            raise HTTPException(status_code=400, detail="ruc es requerido cuando contribuyente=true")
        if not razon_social:
            raise HTTPException(status_code=400, detail="razon_social es requerida")
    else:
        if documento_tipo is None:
            raise HTTPException(status_code=400, detail="documento_tipo es requerido cuando contribuyente=false")
        if documento_tipo != 5 and not documento_numero.strip():
            raise HTTPException(status_code=400, detail="documento_numero es requerido para el tipo de documento indicado")

    # 1. Cargar documento
    db = Conexion()
    try:
        db.conectar()
        repo = RepositorioDE(db)
        fila = repo.obtener_por_cdc(cdc)
        db.cerrar()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not fila:
        raise HTTPException(status_code=404, detail="Documento no encontrado")

    fila = dict(fila) if hasattr(fila, 'keys') else fila

    if fila.get('estado') != 'rechazado':
        raise HTTPException(
            status_code=422,
            detail=f"Solo se pueden corregir documentos rechazados. Estado actual: {fila.get('estado')}"
        )

    codigo_rechazo = fila.get('codigo_sifen', '')
    if not _es_error_receptor(codigo_rechazo):
        raise HTTPException(
            status_code=422,
            detail=f"El rechazo (código {codigo_rechazo}) no corresponde a un error del receptor corregible. Use inutilización y emita un documento nuevo."
        )

    data_json_raw = fila.get('data_json')
    if not data_json_raw:
        raise HTTPException(status_code=422, detail="Documento sin datos para regenerar XML")

    # 2. Parchear data con el nuevo receptor
    try:
        data = _json.loads(data_json_raw)
        if es_contribuyente:
            doc_numero = ruc.split('-')[0] if '-' in ruc else ruc
            data['cliente']['contribuyente']     = True
            data['cliente']['tipoOperacion']     = 1
            data['cliente']['ruc']               = ruc
            data['cliente']['razonSocial']       = razon_social
            data['cliente']['tipoContribuyente'] = data['cliente'].get('tipoContribuyente', 2)
            data['cliente']['documentoTipo']     = 1
            data['cliente']['documentoNumero']   = doc_numero
            if 'usuario' in data:
                data['usuario']['documentoTipo']   = 1
                data['usuario']['documentoNumero'] = doc_numero
                data['usuario']['nombre']          = razon_social
        else:
            doc_num      = '0' if documento_tipo == 5 else documento_numero.strip()
            razon_final  = 'Sin Nombre' if documento_tipo == 5 else razon_social
            data['cliente']['contribuyente']   = False
            data['cliente']['tipoOperacion']   = 2
            data['cliente']['documentoTipo']   = documento_tipo
            data['cliente']['documentoNumero'] = doc_num
            data['cliente']['razonSocial']     = razon_final
            data['cliente'].pop('ruc', None)
            data['cliente'].pop('tipoContribuyente', None)
            if 'usuario' in data:
                data['usuario']['documentoTipo']   = documento_tipo
                data['usuario']['documentoNumero'] = doc_num
                data['usuario']['nombre']          = razon_final
        if direccion.strip():
            data['cliente']['direccion'] = direccion.strip()
        if telefono.strip():
            data['cliente']['telefono']  = telefono.strip()
        if email.strip():
            data['cliente']['email']     = email.strip()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando datos del documento: {e}")

    # 3. Regenerar XML
    sifen_config = get_sifen_config()
    try:
        wrapper      = XMLGeneratorWrapper(sifen_config)
        xml_generado = wrapper.generar_xml_de(data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error regenerando XML: {e}")

    # 4. Re-firmar
    try:
        signer      = XMLSigner(sifen_config)
        xml_firmado = signer.firmar_xml(xml_generado)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error firmando XML: {e}")

    # 5. Verificar que el CDC no cambió
    m = re.search(r'DE Id="([^"]+)"', xml_firmado)
    nuevo_cdc = m.group(1) if m else ''
    if nuevo_cdc and nuevo_cdc != cdc:
        raise HTTPException(
            status_code=500,
            detail=f"El CDC cambió inesperadamente tras la corrección. CDC original: {cdc[:20]}… CDC nuevo: {nuevo_cdc[:20]}…"
        )

    # 6. Guardar corrección en BD
    try:
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        ruc_bd = ruc if es_contribuyente else (documento_numero.strip() or '0')
        razon_bd = razon_social if es_contribuyente else ('Sin Nombre' if documento_tipo == 5 else razon_social)
        ok = repo.corregir_receptor(
            cdc=cdc,
            xml_firmado=xml_firmado,
            ruc_receptor=ruc_bd,
            razon_social_receptor=razon_bd,
            data_json_str=_json.dumps(data, ensure_ascii=False),
        )
        db.cerrar()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error actualizando BD: {e}")

    if not ok:
        raise HTTPException(status_code=409, detail="No se pudo aplicar la corrección (el documento ya no está en estado rechazado)")

    return {
        "cdc":     cdc,
        "estado":  "pendiente",
        "mensaje": "Corrección aplicada. El documento será reenviado a SIFEN en el próximo ciclo del daemon.",
    }


@router.post('/inutilizaciones', status_code=201, summary="Inutilizar rango de numeración")
async def inutilizar_numeracion(req: InutilizacionRequest, _key: str = Depends(require_api_key)):
    """
    Declara ante SIFEN que un rango de números no será utilizado.

    Usar cuando documentos fueron rechazados o generados por error y esos
    números no se van a reutilizar. SIFEN registra la inutilización y la
    numeración queda formalmente anulada en su sistema.
    """
    if req.numero_hasta < req.numero_desde:
        raise HTTPException(status_code=400, detail="numero_hasta debe ser >= numero_desde")

    cfg          = load_config()
    sifen_config = get_sifen_config()

    try:
        gestor    = GestorEventos(sifen_config)
        respuesta = gestor.inutilizar(
            tipo_documento=req.tipo_documento,
            establecimiento=cfg['establecimiento'],
            punto=cfg['punto_expedicion'],
            numero_desde=req.numero_desde,
            numero_hasta=req.numero_hasta,
            motivo=req.motivo,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando inutilización: {e}")

    # Marcar en BD los documentos del rango que existan
    docs_actualizados = 0
    try:
        db   = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        docs_actualizados = repo.marcar_inutilizados(
            tipo_documento=req.tipo_documento,
            numero_desde=req.numero_desde,
            numero_hasta=req.numero_hasta,
        )
        db.cerrar()
    except Exception:
        pass

    return {
        "tipo_documento":      req.tipo_documento,
        "numero_desde":        req.numero_desde,
        "numero_hasta":        req.numero_hasta,
        "codigo_sifen":        respuesta.codigo,
        "descripcion":         respuesta.descripcion,
        "docs_actualizados_bd": docs_actualizados,
    }


@router.post('/documentos/{cdc}/conformidad', summary="Registrar conformidad de un documento recibido")
async def registrar_conformidad(cdc: str, body: ConformidadRequest, _key: str = Depends(require_api_key)):
    """
    El receptor informa a la SET que recibió el documento (conformidad total o parcial).
    Aplica a documentos que el emisor te envió y ya recibiste.
    """
    if len(cdc) != 44:
        raise HTTPException(status_code=400, detail="CDC debe tener 44 dígitos")

    sifen_config = get_sifen_config()

    try:
        gestor    = GestorEventos(sifen_config)
        respuesta = gestor.conformidad(
            cdc=cdc,
            tipo_conformidad=body.tipo_conformidad,
            fecha_recepcion=body.fecha_recepcion,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando conformidad: {e}")

    return {
        "cdc":          cdc,
        "codigo_sifen": respuesta.codigo,
        "descripcion":  respuesta.descripcion,
        "estado":       "conformidad_registrada" if respuesta.exitoso else "error",
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
        headers={"Content-Disposition": f'inline; filename="kude_{numero}.pdf"'},
    )
