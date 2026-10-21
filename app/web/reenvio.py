"""
Sección de reenvío por lote — documentos en estado pendiente/error.

Flujo:
  1. GET /reenvio          → muestra docs pendiente/error por tipo
  2. POST /reenvio/procesar → consulta cada CDC en SIFEN;
                              los que no existen los envía en lote async.
                              Guarda dProtConsLote en BD.
  3. POST /reenvio/consultar-lote → consulta el resultado del lote
                                    y actualiza estados en BD.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE
from sifen_py.services.soap_client import SifenSOAPClient
from app.config_manager import get_sifen_config

router     = APIRouter(tags=['Web'])
templates  = Jinja2Templates(directory=str(Path(__file__).parent.parent / 'templates'))

TIPOS_DOC = {1: 'Factura Electrónica', 4: 'Autofactura', 5: 'Nota de Crédito', 6: 'Nota de Débito', 7: 'Nota de Remisión'}


def _rows(filas) -> list:
    return [dict(f) if hasattr(f, 'keys') else f for f in (filas or [])]


def _resumen_reenvio(repo: RepositorioDE) -> dict:
    """Cuenta pendientes/error por tipo de documento."""
    from sifen_py.db.conexion import Conexion as _C
    conn = repo.db.conectar()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT tipo_documento, estado, COUNT(*) AS total
            FROM documentos_electronicos
            WHERE estado IN ('pendiente', 'error')
              AND (protocolo_lote IS NULL OR protocolo_lote = '')
            GROUP BY tipo_documento, estado
            ORDER BY tipo_documento, estado
        """)
        rows = cur.fetchall()
    resultado = {}
    for r in rows:
        r = dict(r) if hasattr(r, 'keys') else {'tipo_documento': r[0], 'estado': r[1], 'total': r[2]}
        t = r['tipo_documento']
        if t not in resultado:
            resultado[t] = {'nombre': TIPOS_DOC.get(t, f'Tipo {t}'), 'pendiente': 0, 'error': 0}
        resultado[t][r['estado']] = r['total']
    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# PÁGINA PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@router.get('/reenvio', response_class=HTMLResponse)
async def pagina_reenvio(request: Request):
    resumen = {}
    lotes_pendientes = []
    error = None
    try:
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        resumen = _resumen_reenvio(repo)

        # Lotes enviados que aún no tienen resultado (0300 = recibido, no procesado)
        conn = db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT protocolo_lote, tipo_documento, COUNT(*) AS cantidad,
                       MAX(fecha_envio) AS ultima_fecha
                FROM documentos_electronicos
                WHERE protocolo_lote IS NOT NULL
                  AND protocolo_lote != ''
                  AND estado = 'pendiente'
                GROUP BY protocolo_lote, tipo_documento
                ORDER BY ultima_fecha DESC
                LIMIT 20
            """)
            lotes_pendientes = [dict(r) if hasattr(r, 'keys') else
                                {'protocolo_lote': r[0], 'tipo_documento': r[1], 'cantidad': r[2], 'ultima_fecha': r[3]}
                                for r in cur.fetchall()]

        db.cerrar()
    except Exception as e:
        error = str(e)

    return templates.TemplateResponse(request, 'reenvio.html', {
        'resumen':          resumen,
        'lotes_pendientes': lotes_pendientes,
        'tipos_doc':        TIPOS_DOC,
        'error':            error,
    })


# ─────────────────────────────────────────────────────────────────────────────
# FRAGMENTO HTMX: tabla de docs pendiente/error de un tipo
# ─────────────────────────────────────────────────────────────────────────────

@router.get('/reenvio/docs/{tipo_documento}', response_class=HTMLResponse)
async def tabla_docs_reenvio(request: Request, tipo_documento: int):
    docs  = []
    error = None
    try:
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)
        docs = _rows(repo.obtener_para_reenvio(tipo_documento=tipo_documento, limite=50))
        db.cerrar()
    except Exception as e:
        error = str(e)
    return templates.TemplateResponse(request, '_reenvio_tabla.html', {
        'docs':           docs,
        'tipo_documento': tipo_documento,
        'nombre_tipo':    TIPOS_DOC.get(tipo_documento, f'Tipo {tipo_documento}'),
        'error':          error,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACCIÓN: procesar reenvío por lote (fragmento HTMX)
# ─────────────────────────────────────────────────────────────────────────────

@router.post('/reenvio/procesar/{tipo_documento}', response_class=HTMLResponse)
async def procesar_reenvio(request: Request, tipo_documento: int):
    """
    Para cada doc pendiente/error del tipo indicado:
      1. Consulta su CDC en SIFEN
      2. Si está aprobado (0422): actualiza BD
      3. Si no existe (0420): lo acumula para el lote
    Al final envía el lote y guarda el dProtConsLote.
    """
    resultado = {'aprobados': [], 'lote': None, 'en_lote': [], 'errores': [], 'protocolo_lote': None}
    error_general = None

    try:
        sifen_config  = get_sifen_config()
        client        = SifenSOAPClient(sifen_config)
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)

        docs = _rows(repo.obtener_para_reenvio(tipo_documento=tipo_documento, limite=50))

        for_lote_cdcs = []
        for_lote_xmls = []

        for doc in docs:
            cdc = doc['cdc']
            try:
                resp_consulta = client.consultar_de_directo(cdc)

                if resp_consulta.codigo == '0422':
                    # Ya está aprobado en SIFEN — actualizar BD
                    repo.actualizar_estado_consulta(
                        cdc=cdc,
                        codigo=resp_consulta.codigo,
                        descripcion=resp_consulta.descripcion,
                        protocolo=resp_consulta.raw.get('protocolo'),
                        respuesta_xml=resp_consulta.raw.get('xml'),
                    )
                    resultado['aprobados'].append(cdc)

                elif resp_consulta.codigo == '0420':
                    # No existe en SIFEN → va al lote
                    for_lote_cdcs.append(cdc)
                    for_lote_xmls.append(doc['xml_firmado'])
                else:
                    resultado['errores'].append({'cdc': cdc, 'codigo': resp_consulta.codigo, 'msg': resp_consulta.descripcion})

            except Exception as exc:
                resultado['errores'].append({'cdc': cdc, 'codigo': 'ERR', 'msg': str(exc)})

        # Enviar lote si hay docs para ello
        if for_lote_xmls:
            resp_lote = client.enviar_lote_directo(for_lote_xmls)
            protocolo_lote = resp_lote.raw.get('protocolo_lote', '')

            if resp_lote.codigo == '0300' and protocolo_lote:
                repo.marcar_en_lote(for_lote_cdcs, protocolo_lote)
                resultado['protocolo_lote'] = protocolo_lote
                resultado['en_lote'] = for_lote_cdcs
            else:
                resultado['errores'].append({
                    'cdc': 'LOTE',
                    'codigo': resp_lote.codigo,
                    'msg': resp_lote.descripcion,
                })

        db.cerrar()

    except Exception as e:
        error_general = str(e)

    return templates.TemplateResponse(request, '_reenvio_resultado.html', {
        'resultado':      resultado,
        'tipo_documento': tipo_documento,
        'nombre_tipo':    TIPOS_DOC.get(tipo_documento, f'Tipo {tipo_documento}'),
        'error_general':  error_general,
    })


# ─────────────────────────────────────────────────────────────────────────────
# ACCIÓN: consultar resultado de un lote (fragmento HTMX)
# ─────────────────────────────────────────────────────────────────────────────

@router.post('/reenvio/consultar-lote/{protocolo_lote:path}', response_class=HTMLResponse)
async def consultar_resultado_lote(request: Request, protocolo_lote: str):
    """
    Consulta el estado del lote en SIFEN y actualiza la BD con los resultados.
    """
    resultado  = {'procesado': False, 'en_proceso': False, 'des': [], 'codigo': '', 'msg': ''}
    error_general = None

    try:
        sifen_config = get_sifen_config()
        client       = SifenSOAPClient(sifen_config)
        db = Conexion()
        db.conectar()
        repo = RepositorioDE(db)

        resp = client.consultar_lote_directo(protocolo_lote)
        resultado['codigo'] = resp.codigo
        resultado['msg']    = resp.descripcion

        if resp.codigo == '0362':
            resultado['procesado'] = True
            for item in resp.raw.get('detalle_des', []):
                cdc    = item.get('cdc', '')
                codigo = item.get('codigo', '')
                if cdc:
                    repo.actualizar_respuesta(
                        cdc=cdc,
                        codigo=codigo,
                        descripcion=item.get('mensaje', ''),
                    )
                resultado['des'].append(item)

        elif resp.codigo == '0361':
            resultado['en_proceso'] = True

        db.cerrar()

    except Exception as e:
        error_general = str(e)

    return templates.TemplateResponse(request, '_reenvio_resultado_lote.html', {
        'resultado':      resultado,
        'protocolo_lote': protocolo_lote,
        'error_general':  error_general,
    })
