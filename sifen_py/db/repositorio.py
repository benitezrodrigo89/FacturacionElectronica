"""
Repositorio de Documentos Electrónicos — operaciones CRUD sobre la tabla
documentos_electronicos.
"""
from datetime import datetime, timezone
from typing import Optional
from loguru import logger

from .conexion import Conexion


class RepositorioDE:
    """
    CRUD para documentos_electronicos.

    Uso típico::

        repo = RepositorioDE(conexion)

        # Guardar antes de enviar
        repo.guardar_pendiente(cdc, numero_doc, xml_firmado, soap_envelope, ...)

        # Actualizar con la respuesta de SIFEN
        repo.actualizar_respuesta(cdc, codigo='0260', descripcion='Aprobado',
                                  protocolo='50017901', respuesta_xml='...')
    """

    def __init__(self, conexion: Conexion):
        self.db = conexion

    # ─────────────────────────────────────────────────────────────────
    # ESCRITURA
    # ─────────────────────────────────────────────────────────────────

    def guardar_pendiente(
        self,
        cdc:                   str,
        numero_doc:            int,
        xml_firmado:           str,
        soap_envelope:         str           = None,
        establecimiento:       str           = '001',
        punto_expedicion:      str           = '001',
        tipo_documento:        int           = 1,
        fecha_emision:         datetime      = None,
        ruc_receptor:          str           = None,
        razon_social_receptor: str           = None,
        monto_total:           int           = None,
    ) -> int:
        """
        Inserta un DE en estado 'pendiente' antes de enviarlo a SIFEN.
        Devuelve el id generado. Si el CDC ya existe actualiza el intento.
        """
        fecha_emision = fecha_emision or datetime.now(timezone.utc)
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO documentos_electronicos (
                    cdc, numero_doc, establecimiento, punto_expedicion,
                    tipo_documento, fecha_emision, ruc_receptor,
                    razon_social_receptor, monto_total,
                    xml_firmado, soap_envelope, estado, fecha_envio
                ) VALUES (
                    %(cdc)s, %(numero_doc)s, %(establecimiento)s, %(punto_expedicion)s,
                    %(tipo_documento)s, %(fecha_emision)s, %(ruc_receptor)s,
                    %(razon_social_receptor)s, %(monto_total)s,
                    %(xml_firmado)s, %(soap_envelope)s, 'pendiente', NOW()
                )
                ON CONFLICT (cdc) DO UPDATE SET
                    intentos    = documentos_electronicos.intentos + 1,
                    fecha_envio = NOW(),
                    soap_envelope = EXCLUDED.soap_envelope
                RETURNING id
            """, {
                'cdc':                   cdc,
                'numero_doc':            numero_doc,
                'establecimiento':       establecimiento,
                'punto_expedicion':      punto_expedicion,
                'tipo_documento':        tipo_documento,
                'fecha_emision':         fecha_emision,
                'ruc_receptor':          ruc_receptor,
                'razon_social_receptor': razon_social_receptor,
                'monto_total':           monto_total,
                'xml_firmado':           xml_firmado,
                'soap_envelope':         soap_envelope,
            })
            row = cur.fetchone()
            id_ = row[0] if isinstance(row, tuple) else row['id']
        conn.commit()
        logger.debug(f"DE guardado (id={id_}, cdc={cdc[:20]}…, estado=pendiente)")
        return id_

    def actualizar_respuesta(
        self,
        cdc:           str,
        codigo:        str,
        descripcion:   str,
        respuesta_xml: str  = None,
        protocolo:     str  = None,
    ):
        """
        Actualiza el estado del DE con la respuesta de SIFEN.

        código → estado:
            0260  → aprobado
            1001  → duplicado (SIFEN ya lo tiene — significa que estaba aprobado)
            0160  → rechazado
            otros → rechazado

        Regla: un registro 'aprobado' nunca se degrada a otro estado.
        Si llega 1001 (duplicado) y ya era 'aprobado', se mantiene 'aprobado'.
        """
        estado = _codigo_a_estado(codigo)
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE documentos_electronicos SET
                    estado = CASE
                        WHEN estado = 'aprobado' THEN 'aprobado'
                        ELSE %(estado)s
                    END,
                    codigo_sifen           = %(codigo)s,
                    descripcion_sifen      = %(descripcion)s,
                    protocolo_autorizacion = COALESCE(%(protocolo)s, protocolo_autorizacion),
                    respuesta_xml          = %(respuesta_xml)s,
                    fecha_respuesta        = NOW()
                WHERE cdc = %(cdc)s
            """, {
                'cdc':           cdc,
                'estado':        estado,
                'codigo':        codigo,
                'descripcion':   descripcion,
                'protocolo':     protocolo,
                'respuesta_xml': respuesta_xml,
            })
        conn.commit()
        logger.info(f"DE actualizado — CDC: {cdc[:20]}… | estado: {estado} | código: {codigo}")

    def actualizar_estado_consulta(
        self,
        cdc:       str,
        codigo:    str,
        descripcion: str,
        protocolo: str = None,
        respuesta_xml: str = None,
    ):
        """Actualiza el estado de un DE a partir de una consulta posterior a SIFEN."""
        estado = _codigo_consulta_a_estado(codigo)
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE documentos_electronicos SET
                    estado                 = %(estado)s,
                    codigo_sifen           = %(codigo)s,
                    descripcion_sifen      = %(descripcion)s,
                    protocolo_autorizacion = COALESCE(%(protocolo)s, protocolo_autorizacion),
                    respuesta_xml          = COALESCE(%(respuesta_xml)s, respuesta_xml),
                    fecha_respuesta        = NOW()
                WHERE cdc = %(cdc)s
            """, {
                'cdc':           cdc,
                'estado':        estado,
                'codigo':        codigo,
                'descripcion':   descripcion,
                'protocolo':     protocolo,
                'respuesta_xml': respuesta_xml,
            })
        conn.commit()
        logger.info(f"Estado actualizado por consulta — CDC: {cdc[:20]}… | {estado}")

    # ─────────────────────────────────────────────────────────────────
    # LECTURA
    # ─────────────────────────────────────────────────────────────────

    def obtener_por_cdc(self, cdc: str) -> Optional[dict]:
        """Devuelve el registro completo de un DE por su CDC."""
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM documentos_electronicos WHERE cdc = %s", (cdc,)
            )
            return cur.fetchone()

    def listar_por_estado(self, estado: str, limite: int = 100) -> list:
        """
        Devuelve los DEs según su estado.
        Estados: 'pendiente' | 'aprobado' | 'rechazado' | 'duplicado' | 'error'
        """
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, cdc, numero_doc, estado, codigo_sifen,
                       protocolo_autorizacion, fecha_emision, fecha_envio, intentos
                FROM documentos_electronicos
                WHERE estado = %s
                ORDER BY fecha_envio DESC
                LIMIT %s
            """, (estado, limite))
            return cur.fetchall()

    def listar_recientes(self, limite: int = 20) -> list:
        """Devuelve los últimos N documentos enviados."""
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, cdc, numero_doc, estado, codigo_sifen,
                       descripcion_sifen, protocolo_autorizacion,
                       fecha_emision, fecha_envio, intentos
                FROM documentos_electronicos
                ORDER BY created_at DESC
                LIMIT %s
            """, (limite,))
            return cur.fetchall()

    def proximo_numero_doc(
        self,
        establecimiento:  str = '001',
        punto_expedicion: str = '001',
        tipo_documento:   int = 1,
    ) -> int:
        """
        Devuelve el próximo número de documento disponible para el
        establecimiento/punto dado (máximo guardado + 1).
        Si no hay registros devuelve 1.
        """
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COALESCE(MAX(numero_doc), 0) + 1
                FROM documentos_electronicos
                WHERE establecimiento   = %s
                  AND punto_expedicion  = %s
                  AND tipo_documento    = %s
            """, (establecimiento, punto_expedicion, tipo_documento))
            row = cur.fetchone()
        return row[0] if isinstance(row, tuple) else list(row.values())[0]

    def ultimo_enviado(self) -> Optional[dict]:
        """Devuelve el registro del último documento enviado (por fecha_envio)."""
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, cdc, numero_doc, estado, codigo_sifen,
                       descripcion_sifen, protocolo_autorizacion,
                       fecha_emision, fecha_envio, intentos
                FROM documentos_electronicos
                ORDER BY fecha_envio DESC
                LIMIT 1
            """)
            return cur.fetchone()

    def resumen_estados(self) -> dict:
        """Devuelve conteo de documentos por estado."""
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT estado, COUNT(*) AS total
                FROM documentos_electronicos
                GROUP BY estado
                ORDER BY estado
            """)
            rows = cur.fetchall()
        return {r['estado']: r['total'] for r in rows}


# ─────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────

def _codigo_a_estado(codigo: str) -> str:
    """Mapea código de respuesta de envío al estado del DE."""
    return {
        '0260': 'aprobado',
        '1001': 'aprobado',  # CDC duplicado = ya existe en SIFEN = estaba aprobado
    }.get(codigo, 'rechazado')


def _codigo_consulta_a_estado(codigo: str) -> str:
    """Mapea código de respuesta de consulta al estado del DE."""
    return {
        '0422': 'aprobado',
        '0420': 'rechazado',
    }.get(codigo, 'rechazado')
