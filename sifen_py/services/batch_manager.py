"""
Gestor de lotes para envío asíncrono de Documentos Electrónicos a SIFEN.
Manual Técnico v150 — hasta 50 DEs por lote, máximo 1000 KB comprimido.
"""
import time
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from sifen_py.core.constants import LIMITE_DOCS_POR_LOTE
from sifen_py.core.exceptions import BatchException


class EstadoDE(str, Enum):
    PENDIENTE   = 'pendiente'
    EN_LOTE     = 'en_lote'
    ENVIADO     = 'enviado'
    APROBADO    = 'aprobado'
    RECHAZADO   = 'rechazado'
    ERROR       = 'error'


class EstadoLote(str, Enum):
    ARMADO       = 'armado'
    ENVIADO      = 'enviado'       # 0300 — recibido en SIFEN
    PROCESANDO   = 'procesando'    # 0361
    PROCESADO    = 'procesado'     # 0362
    NO_ENCOLADO  = 'no_encolado'   # 0301
    NO_EXISTE    = 'no_existe'     # 0360
    ERROR        = 'error'


@dataclass
class DocumentoEnLote:
    """Representa un DE dentro del gestor de lotes."""
    cdc:         str
    xml_firmado: str
    estado:      EstadoDE = EstadoDE.PENDIENTE
    codigo_resp: Optional[str] = None
    mensaje_resp: Optional[str] = None
    numero_lote: Optional[str] = None
    intentos:    int = 0


@dataclass
class Lote:
    """Representa un lote de DEs."""
    numero:    str
    documentos: list = field(default_factory=list)
    estado:    EstadoLote = EstadoLote.ARMADO
    codigo_resp: Optional[str] = None
    mensaje_resp: Optional[str] = None
    creado_en: float = field(default_factory=time.time)

    @property
    def cantidad(self) -> int:
        return len(self.documentos)

    @property
    def esta_lleno(self) -> bool:
        return self.cantidad >= LIMITE_DOCS_POR_LOTE


class BatchManager:
    """
    Gestor de lotes para envío asíncrono a SIFEN.

    Flujo típico::

        bm = BatchManager(soap_client)
        bm.agregar_de(cdc='...', xml_firmado='...')
        bm.agregar_de(cdc='...', xml_firmado='...')
        lote = bm.enviar_lote_actual()
        resp = bm.esperar_resultado(lote.numero)
        resultados = bm.obtener_resultados_lote(lote.numero)
    """

    def __init__(self, soap_client, max_reintentos: int = 3):
        """
        Args:
            soap_client:    Instancia de SifenSOAPClient
            max_reintentos: Reintentos por lote en caso de error de red
        """
        self.client         = soap_client
        self.max_reintentos = max_reintentos
        self._documentos:   dict[str, DocumentoEnLote] = {}   # cdc → doc
        self._lotes:        dict[str, Lote]            = {}   # numero → lote
        self._lote_actual:  Optional[Lote]             = None

    # ─────────────────────────────────────────────────────────
    # GESTIÓN DE DOCUMENTOS
    # ─────────────────────────────────────────────────────────
    def agregar_de(self, cdc: str, xml_firmado: str) -> DocumentoEnLote:
        """
        Agrega un DE al lote actual.
        Si el lote actual está lleno, lo cierra y crea uno nuevo.

        Args:
            cdc:         CDC del documento (44 dígitos)
            xml_firmado: XML firmado del DE

        Returns:
            DocumentoEnLote con el estado inicial
        """
        if cdc in self._documentos:
            raise BatchException(f"El CDC {cdc} ya fue agregado")

        doc = DocumentoEnLote(cdc=cdc, xml_firmado=xml_firmado)
        self._documentos[cdc] = doc

        # Crear lote actual si no existe
        if self._lote_actual is None:
            self._lote_actual = self._nuevo_lote()

        # Si está lleno, cerrar y crear nuevo
        if self._lote_actual.esta_lleno:
            logger.info(f"Lote {self._lote_actual.numero} lleno ({LIMITE_DOCS_POR_LOTE} DEs), creando nuevo lote")
            self._lote_actual = self._nuevo_lote()

        self._lote_actual.documentos.append(doc)
        doc.estado      = EstadoDE.EN_LOTE
        doc.numero_lote = self._lote_actual.numero
        logger.debug(f"DE {cdc} agregado al lote {self._lote_actual.numero} ({self._lote_actual.cantidad}/{LIMITE_DOCS_POR_LOTE})")
        return doc

    # ─────────────────────────────────────────────────────────
    # ENVÍO
    # ─────────────────────────────────────────────────────────
    def enviar_lote_actual(self) -> Optional[Lote]:
        """
        Envía el lote actual a SIFEN.
        Retorna None si no hay documentos pendientes.
        """
        if not self._lote_actual or self._lote_actual.cantidad == 0:
            logger.warning("No hay documentos en el lote actual")
            return None
        lote = self._lote_actual
        self._lote_actual = None  # Cerrar lote actual antes de enviar
        return self._enviar_lote(lote)

    def enviar_todos_los_lotes(self) -> list[Lote]:
        """
        Envía todos los lotes que tengan documentos pendientes.
        Incluye el lote actual si tiene documentos.
        """
        lotes_enviados = []
        # Cerrar lote actual si tiene docs
        if self._lote_actual and self._lote_actual.cantidad > 0:
            lote = self._lote_actual
            self._lote_actual = None
            lotes_enviados.append(self._enviar_lote(lote))

        # Reenviar lotes en estado ARMADO (si hubo alguno previo sin enviar)
        for lote in self._lotes.values():
            if lote.estado == EstadoLote.ARMADO:
                lotes_enviados.append(self._enviar_lote(lote))

        return lotes_enviados

    def _enviar_lote(self, lote: Lote) -> Lote:
        """Intenta enviar un lote con reintentos."""
        xmls = [doc.xml_firmado for doc in lote.documentos]
        for intento in range(1, self.max_reintentos + 1):
            try:
                logger.info(f"Enviando lote {lote.numero} — intento {intento}/{self.max_reintentos} ({lote.cantidad} DEs)")
                resp = self.client.enviar_lote(xmls, lote.numero)
                lote.codigo_resp  = resp.codigo
                lote.mensaje_resp = resp.descripcion

                if resp.codigo == '0300':
                    lote.estado = EstadoLote.ENVIADO
                    for doc in lote.documentos:
                        doc.estado = EstadoDE.ENVIADO
                    logger.success(f"Lote {lote.numero} enviado exitosamente")
                else:
                    lote.estado = EstadoLote.NO_ENCOLADO
                    for doc in lote.documentos:
                        doc.estado      = EstadoDE.RECHAZADO
                        doc.codigo_resp = resp.codigo
                    logger.warning(f"Lote {lote.numero} no encolado: {resp}")
                return lote

            except Exception as e:
                logger.error(f"Error en intento {intento} para lote {lote.numero}: {e}")
                if intento < self.max_reintentos:
                    time.sleep(2 ** intento)  # backoff exponencial
                else:
                    lote.estado      = EstadoLote.ERROR
                    lote.mensaje_resp = str(e)
                    for doc in lote.documentos:
                        doc.estado = EstadoDE.ERROR
        return lote

    # ─────────────────────────────────────────────────────────
    # CONSULTA DE RESULTADOS
    # ─────────────────────────────────────────────────────────
    def esperar_resultado(
        self,
        numero_lote: str,
        intentos: int = 10,
        espera_seg: float = 5.0,
    ) -> Lote:
        """
        Espera y actualiza el estado de un lote hasta que sea procesado.

        Args:
            numero_lote: Número del lote enviado
            intentos:    Máximo de consultas
            espera_seg:  Segundos entre consultas
        """
        lote = self._lotes.get(numero_lote)
        if not lote:
            raise BatchException(f"Lote {numero_lote} no encontrado en el gestor")
        if lote.estado not in (EstadoLote.ENVIADO, EstadoLote.PROCESANDO):
            logger.info(f"Lote {numero_lote} ya está en estado: {lote.estado}")
            return lote

        resp = self.client.esperar_procesamiento_lote(numero_lote, intentos, espera_seg)
        lote.codigo_resp  = resp.codigo
        lote.mensaje_resp = resp.descripcion

        if resp.codigo == '0362':
            lote.estado = EstadoLote.PROCESADO
            # Actualizar estado de cada DE con el detalle
            detalle = resp.raw.get('detalle_des', [])
            self._actualizar_estados_des(lote, detalle)
        elif resp.codigo == '0361':
            lote.estado = EstadoLote.PROCESANDO
        elif resp.codigo in ('0360', '0364'):
            lote.estado = EstadoLote.NO_EXISTE
        return lote

    def consultar_de(self, cdc: str) -> DocumentoEnLote:
        """
        Consulta el estado de un DE específico directamente en SIFEN y actualiza
        el registro interno.
        """
        doc = self._documentos.get(cdc)
        if not doc:
            raise BatchException(f"CDC {cdc} no encontrado en el gestor")
        resp = self.client.consultar_de(cdc)
        doc.codigo_resp  = resp.codigo
        doc.mensaje_resp = resp.descripcion
        if resp.codigo == '0422':
            doc.estado = EstadoDE.APROBADO
        elif resp.codigo == '0420':
            doc.estado = EstadoDE.RECHAZADO
        return doc

    def obtener_resultados_lote(self, numero_lote: str) -> list[DocumentoEnLote]:
        """Retorna la lista de DEs de un lote con sus estados actualizados."""
        lote = self._lotes.get(numero_lote)
        if not lote:
            raise BatchException(f"Lote {numero_lote} no encontrado")
        return lote.documentos

    # ─────────────────────────────────────────────────────────
    # REPORTE
    # ─────────────────────────────────────────────────────────
    def resumen(self) -> dict:
        """Genera un resumen del estado de todos los lotes y documentos."""
        total = len(self._documentos)
        por_estado = {}
        for doc in self._documentos.values():
            por_estado[doc.estado] = por_estado.get(doc.estado, 0) + 1

        return {
            'total_documentos': total,
            'por_estado':       por_estado,
            'total_lotes':      len(self._lotes),
            'lotes': [
                {
                    'numero':   l.numero,
                    'estado':   l.estado,
                    'cantidad': l.cantidad,
                    'codigo':   l.codigo_resp,
                }
                for l in self._lotes.values()
            ]
        }

    # ─────────────────────────────────────────────────────────
    # HELPERS
    # ─────────────────────────────────────────────────────────
    def _nuevo_lote(self) -> Lote:
        numero = str(int(time.time() * 1000))[-12:]  # 12 dígitos
        lote   = Lote(numero=numero)
        self._lotes[numero] = lote
        logger.debug(f"Nuevo lote creado: {numero}")
        return lote

    def _actualizar_estados_des(self, lote: Lote, detalle: list):
        """Actualiza estados individuales de DEs desde el detalle del lote."""
        for item in detalle:
            cdc    = item.get('dCDC') or item.get('cdc', '')
            codigo = str(item.get('dCodRes') or item.get('codigo', ''))
            msg    = str(item.get('dMsgRes') or item.get('mensaje', ''))
            doc    = self._documentos.get(cdc)
            if doc:
                doc.codigo_resp  = codigo
                doc.mensaje_resp = msg
                doc.estado = EstadoDE.APROBADO if codigo == '0422' else EstadoDE.RECHAZADO
