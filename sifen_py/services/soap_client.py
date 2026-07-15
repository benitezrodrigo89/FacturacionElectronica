"""
Cliente SOAP para los servicios web de SIFEN Paraguay.
Implementa todos los endpoints del Manual Técnico v150.

URLs de test:
  Recepción sync:    https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl
  Recepción lotes:   https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl
  Consulta lote:     https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl
  Consulta CDC:      https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl
  Consulta RUC:      https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl
  Recepción evento:  https://sifen-test.set.gov.py/de/ws/async/recibe-evento.wsdl
"""
import zipfile
import io
import time
from typing import Optional
from pathlib import Path
from loguru import logger

try:
    from zeep import Client
    from zeep.transports import Transport
    from zeep.exceptions import Fault as ZeepFault
    import requests
    from requests.adapters import HTTPAdapter
    ZEEP_AVAILABLE = True
except ImportError:
    ZEEP_AVAILABLE = False

from sifen_py.core.config import SifenConfig
from sifen_py.core.constants import (
    LIMITE_DOCS_POR_LOTE, LIMITE_ITEMS_POR_DOC,
    TAMANO_MAX_LOTE_KB, CODIGOS_RESPUESTA_LOTE,
    CODIGOS_RESPUESTA_DE,
)
from sifen_py.core.exceptions import SOAPException, BatchException


class RespuestaSIFEN:
    """Respuesta normalizada de cualquier operación SIFEN."""

    def __init__(self, codigo: str, descripcion: str, raw: dict = None):
        self.codigo      = codigo
        self.descripcion = descripcion
        self.raw         = raw or {}
        self.exitoso     = codigo in ('0300', '0360', '0362', '0420', '0422', 'OK')

    def __repr__(self):
        return f"RespuestaSIFEN(codigo={self.codigo!r}, desc={self.descripcion!r}, exitoso={self.exitoso})"


class SifenSOAPClient:
    """
    Cliente SOAP para todos los servicios web de SIFEN.

    Requiere:
        - Certificado .pfx/.p12 del contribuyente (autenticación mutua TLS)
        - zeep >= 4.0
        - requests

    Ejemplo::

        config = SifenConfig(
            ambiente='test',
            ruc='80000001-1',
            razon_social='Mi Empresa SA',
            certificado_path='cert.pfx',
            certificado_password='mi_clave',
            csc='00000001',
        )
        client = SifenSOAPClient(config)
        resp = client.consultar_ruc('80000001-1')
    """

    # URLs de los WSDLs — se añade el endpoint sync (recibe individual)
    WSDL_KEYS = {
        'recibe':         'recibe',        # sync — recepción individual (nuevo)
        'recibe_lote':    'recibe_lote',
        'consulta_lote':  'consulta_lote',
        'consulta_de':    'consulta_de',
        'consulta_ruc':   'consulta_ruc',
        'recibe_evento':  'recibe_evento',
    }

    # URLs hardcodeadas para sync (no estaban en constants)
    URLS_SYNC = {
        'test': 'https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl',
        'prod': 'https://sifen.set.gov.py/de/ws/sync/recibe.wsdl',
    }

    def __init__(self, config: SifenConfig, timeout: int = 60):
        if not ZEEP_AVAILABLE:
            raise SOAPException(
                "zeep y requests son requeridos. Instala con: pip install zeep requests"
            )
        self.config  = config
        self.timeout = timeout
        self._clients: dict = {}
        logger.info(f"SifenSOAPClient inicializado — ambiente: {config.ambiente}")

    def _get_session(self) -> 'requests.Session':
        """Crea una sesión requests con el certificado del contribuyente (mTLS)."""
        session = requests.Session()
        cert_path = str(self.config.certificado_path)
        # zeep/requests acepta (cert, key) o un .pfx directamente en algunos casos;
        # la forma más portable es exportar el .pfx a PEM temporalmente o usar
        # requests-pkcs12 si está disponible.
        try:
            import requests_pkcs12
            adapter = requests_pkcs12.Pkcs12Adapter(
                pkcs12_filename=cert_path,
                pkcs12_password=self.config.certificado_password,
            )
            session.mount('https://', adapter)
            logger.debug("mTLS: usando requests-pkcs12")
        except ImportError:
            # Sin mTLS — funciona para consultas públicas y ambiente test sin cert
            logger.warning(
                "requests-pkcs12 no instalado. Las llamadas irán sin mTLS. "
                "Instala con: pip install requests-pkcs12"
            )
        session.verify = True
        return session

    def _get_client(self, servicio: str) -> 'Client':
        """Obtiene (o crea y cachea) el cliente SOAP para un servicio."""
        if servicio in self._clients:
            return self._clients[servicio]

        if servicio == 'recibe':
            wsdl_url = self.URLS_SYNC[self.config.ambiente]
        else:
            wsdl_url = self.config.get_url(servicio)

        logger.debug(f"Creando cliente SOAP para: {wsdl_url}")
        session   = self._get_session()
        transport = Transport(session=session, timeout=self.timeout)
        try:
            client = Client(wsdl_url, transport=transport)
        except Exception as e:
            raise SOAPException(f"No se pudo cargar WSDL [{servicio}]: {e}") from e
        self._clients[servicio] = client
        return client

    # ─────────────────────────────────────────────────────────
    # 1. RECEPCIÓN SÍNCRONA (1 documento)
    # ─────────────────────────────────────────────────────────
    def recibir_de(self, xml_firmado: str) -> RespuestaSIFEN:
        """
        Envía un único Documento Electrónico firmado de forma síncrona.
        Servicio: /de/ws/sync/recibe.wsdl

        Args:
            xml_firmado: XML del DE firmado digitalmente (string)

        Returns:
            RespuestaSIFEN con el resultado
        """
        logger.info("Enviando DE de forma síncrona a SIFEN")
        try:
            client  = self._get_client('recibe')
            # El parámetro se llama 'dId' (XML del DE como string)
            result  = client.service.rRecepcionar(dId=xml_firmado)
            return self._parsear_respuesta_de(result)
        except ZeepFault as e:
            raise SOAPException(f"SOAP Fault en recibir_de: {e}") from e
        except Exception as e:
            raise SOAPException(f"Error en recibir_de: {e}") from e

    # ─────────────────────────────────────────────────────────
    # 2. RECEPCIÓN ASÍNCRONA (lote)
    # ─────────────────────────────────────────────────────────
    def enviar_lote(
        self,
        xmls_firmados: list[str],
        numero_lote: Optional[str] = None,
    ) -> RespuestaSIFEN:
        """
        Envía un lote de hasta 50 DEs firmados a SIFEN.
        Servicio: /de/ws/async/recibe-lote.wsdl

        Args:
            xmls_firmados:  Lista de strings XML firmados (máx 50)
            numero_lote:    Identificador del lote (se genera automático si None)

        Returns:
            RespuestaSIFEN — código 0300 = recibido, 0301 = no encolado
        """
        if not xmls_firmados:
            raise BatchException("La lista de XMLs no puede estar vacía")
        if len(xmls_firmados) > LIMITE_DOCS_POR_LOTE:
            raise BatchException(
                f"El lote excede el máximo de {LIMITE_DOCS_POR_LOTE} documentos "
                f"(recibidos: {len(xmls_firmados)})"
            )

        # Generar número de lote si no se proveyó
        if not numero_lote:
            numero_lote = str(int(time.time()))

        # Comprimir los XMLs en ZIP
        zip_bytes = self._comprimir_xmls(xmls_firmados, numero_lote)
        tam_kb    = len(zip_bytes) / 1024
        if tam_kb > TAMANO_MAX_LOTE_KB:
            raise BatchException(
                f"El lote comprimido supera el máximo de {TAMANO_MAX_LOTE_KB} KB "
                f"(tamaño: {tam_kb:.1f} KB)"
            )

        logger.info(
            f"Enviando lote #{numero_lote} — {len(xmls_firmados)} DEs, "
            f"{tam_kb:.1f} KB comprimido"
        )

        try:
            client = self._get_client('recibe_lote')
            result = client.service.rRecepcionLote(
                dIdLote=numero_lote,
                dArchivo=zip_bytes,
            )
            return self._parsear_respuesta_lote(result, numero_lote)
        except ZeepFault as e:
            raise SOAPException(f"SOAP Fault en enviar_lote: {e}") from e
        except Exception as e:
            raise SOAPException(f"Error en enviar_lote: {e}") from e

    # ─────────────────────────────────────────────────────────
    # 3. CONSULTA ESTADO DE LOTE
    # ─────────────────────────────────────────────────────────
    def consultar_lote(self, numero_lote: str) -> RespuestaSIFEN:
        """
        Consulta el estado de procesamiento de un lote enviado.
        Servicio: /de/ws/consultas/consulta-lote.wsdl

        Códigos de respuesta:
            0300 → Lote recibido con éxito (aún no procesado)
            0361 → Lote en procesamiento
            0362 → Procesamiento concluido — revisar DEs individualmente
            0360 → No existe número de lote
            0364 → Consulta extemporánea

        Args:
            numero_lote: ID del lote previamente enviado

        Returns:
            RespuestaSIFEN con el estado del lote y detalle de DEs si está disponible
        """
        logger.info(f"Consultando estado de lote: {numero_lote}")
        try:
            client = self._get_client('consulta_lote')
            result = client.service.rConsultaLote(dIdLote=numero_lote)
            return self._parsear_respuesta_consulta_lote(result, numero_lote)
        except ZeepFault as e:
            raise SOAPException(f"SOAP Fault en consultar_lote: {e}") from e
        except Exception as e:
            raise SOAPException(f"Error en consultar_lote: {e}") from e

    def esperar_procesamiento_lote(
        self,
        numero_lote: str,
        intentos: int = 10,
        espera_seg: float = 5.0,
    ) -> RespuestaSIFEN:
        """
        Espera hasta que un lote sea procesado, consultando periódicamente.

        Args:
            numero_lote: ID del lote
            intentos:    Número máximo de intentos (default 10)
            espera_seg:  Segundos entre intentos (default 5)

        Returns:
            RespuestaSIFEN del estado final

        Raises:
            SOAPException si se agota el número de intentos
        """
        for intento in range(1, intentos + 1):
            resp = self.consultar_lote(numero_lote)
            logger.info(f"Lote {numero_lote} — intento {intento}/{intentos}: {resp}")
            # 0362 = procesamiento concluido
            if resp.codigo == '0362':
                return resp
            # 0360 = no existe, 0364 = extemporáneo — no tiene sentido seguir
            if resp.codigo in ('0360', '0364'):
                return resp
            if intento < intentos:
                logger.debug(f"Esperando {espera_seg}s antes del próximo intento…")
                time.sleep(espera_seg)

        raise SOAPException(
            f"Lote {numero_lote} no fue procesado en {intentos} intentos "
            f"({intentos * espera_seg:.0f}s)"
        )

    # ─────────────────────────────────────────────────────────
    # 4. CONSULTA POR CDC
    # ─────────────────────────────────────────────────────────
    def consultar_de(self, cdc: str) -> RespuestaSIFEN:
        """
        Consulta el estado de un Documento Electrónico por su CDC.
        Servicio: /de/ws/consultas/consulta.wsdl

        Códigos de respuesta:
            0422 → DE aprobado
            0420 → DE no existe o fue rechazado

        Args:
            cdc: Código de Control de Documento (44 dígitos)

        Returns:
            RespuestaSIFEN con el estado del DE
        """
        if not cdc or len(cdc) != 44:
            raise SOAPException(f"CDC inválido (debe tener 44 dígitos): {cdc!r}")

        logger.info(f"Consultando DE por CDC: {cdc}")
        try:
            client = self._get_client('consulta_de')
            result = client.service.rConsultaDE(dCDC=cdc)
            return self._parsear_respuesta_de(result)
        except ZeepFault as e:
            raise SOAPException(f"SOAP Fault en consultar_de: {e}") from e
        except Exception as e:
            raise SOAPException(f"Error en consultar_de: {e}") from e

    # ─────────────────────────────────────────────────────────
    # 5. CONSULTA DE RUC
    # ─────────────────────────────────────────────────────────
    def consultar_ruc(self, ruc: str) -> RespuestaSIFEN:
        """
        Consulta información de un RUC en el registro de la SET.
        Servicio: /de/ws/consultas/consulta-ruc.wsdl

        Args:
            ruc: RUC a consultar (formato: 80000001-1 o 80000001)

        Returns:
            RespuestaSIFEN con datos del contribuyente si existe
        """
        # Normalizar formato
        ruc_normalizado = ruc.replace('-', '')
        logger.info(f"Consultando RUC: {ruc}")
        try:
            client = self._get_client('consulta_ruc')
            result = client.service.rConsultaRUC(dRUCCons=ruc_normalizado)
            return self._parsear_respuesta_ruc(result)
        except ZeepFault as e:
            raise SOAPException(f"SOAP Fault en consultar_ruc: {e}") from e
        except Exception as e:
            raise SOAPException(f"Error en consultar_ruc: {e}") from e

    # ─────────────────────────────────────────────────────────
    # 6. ENVÍO DE EVENTOS
    # ─────────────────────────────────────────────────────────
    def enviar_evento(self, xml_evento_firmado: str) -> RespuestaSIFEN:
        """
        Envía un evento (cancelación, inutilización, conformidad, etc.) firmado.
        Servicio: /de/ws/async/recibe-evento.wsdl

        Args:
            xml_evento_firmado: XML del evento firmado

        Returns:
            RespuestaSIFEN con el resultado
        """
        logger.info("Enviando evento a SIFEN")
        try:
            client = self._get_client('recibe_evento')
            result = client.service.rRecepcionEvento(dId=xml_evento_firmado)
            return self._parsear_respuesta_evento(result)
        except ZeepFault as e:
            raise SOAPException(f"SOAP Fault en enviar_evento: {e}") from e
        except Exception as e:
            raise SOAPException(f"Error en enviar_evento: {e}") from e

    # ─────────────────────────────────────────────────────────
    # HELPERS INTERNOS
    # ─────────────────────────────────────────────────────────
    def _comprimir_xmls(self, xmls: list[str], numero_lote: str) -> bytes:
        """Crea un ZIP en memoria con todos los XMLs del lote."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for i, xml in enumerate(xmls, start=1):
                filename = f"DE_{numero_lote}_{str(i).zfill(3)}.xml"
                zf.writestr(filename, xml.encode('utf-8'))
        buffer.seek(0)
        return buffer.read()

    def _parsear_respuesta_de(self, result) -> RespuestaSIFEN:
        """Parsea la respuesta de rRecepcionar / rConsultaDE."""
        try:
            raw = dict(result) if result else {}
            # SIFEN responde con xRetCodRes y xRetMsgRes en algunos WSDLs
            codigo = str(
                raw.get('dCodRes') or
                raw.get('xRetCodRes') or
                raw.get('codigo') or
                'ERR'
            )
            desc = str(
                raw.get('dMsgRes') or
                raw.get('xRetMsgRes') or
                raw.get('descripcion') or
                CODIGOS_RESPUESTA_DE.get(codigo, 'Sin descripción')
            )
            resp = RespuestaSIFEN(codigo, desc, raw)
            logger.info(f"Respuesta DE: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Error parseando respuesta DE: {e} — raw: {result}")
            return RespuestaSIFEN('ERR', str(e), {})

    def _parsear_respuesta_lote(self, result, numero_lote: str) -> RespuestaSIFEN:
        """Parsea la respuesta de rRecepcionLote."""
        try:
            raw    = dict(result) if result else {}
            codigo = str(raw.get('dCodRes') or raw.get('codigo') or 'ERR')
            desc   = str(
                raw.get('dMsgRes') or
                raw.get('descripcion') or
                CODIGOS_RESPUESTA_LOTE.get(codigo, 'Sin descripción')
            )
            raw['numero_lote'] = numero_lote
            resp = RespuestaSIFEN(codigo, desc, raw)
            logger.info(f"Respuesta lote #{numero_lote}: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Error parseando respuesta lote: {e}")
            return RespuestaSIFEN('ERR', str(e), {})

    def _parsear_respuesta_consulta_lote(self, result, numero_lote: str) -> RespuestaSIFEN:
        """Parsea la respuesta de rConsultaLote, incluyendo detalle de DEs."""
        try:
            raw    = dict(result) if result else {}
            codigo = str(raw.get('dCodRes') or raw.get('codigo') or 'ERR')
            desc   = str(
                raw.get('dMsgRes') or
                raw.get('descripcion') or
                CODIGOS_RESPUESTA_LOTE.get(codigo, 'Sin descripción')
            )
            raw['numero_lote'] = numero_lote
            # Intentar extraer detalle de DEs si el lote ya fue procesado (0362)
            if codigo == '0362':
                detalle = raw.get('xDetalle') or raw.get('detalle') or []
                raw['detalle_des'] = [dict(d) for d in detalle] if detalle else []
            resp = RespuestaSIFEN(codigo, desc, raw)
            logger.info(f"Consulta lote #{numero_lote}: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Error parseando respuesta consulta lote: {e}")
            return RespuestaSIFEN('ERR', str(e), {})

    def _parsear_respuesta_ruc(self, result) -> RespuestaSIFEN:
        """Parsea la respuesta de rConsultaRUC."""
        try:
            raw    = dict(result) if result else {}
            codigo = str(raw.get('dCodRes') or raw.get('codigo') or 'ERR')
            desc   = str(raw.get('dMsgRes') or raw.get('descripcion') or 'Sin descripción')
            resp   = RespuestaSIFEN(codigo, desc, raw)
            logger.info(f"Consulta RUC: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Error parseando respuesta RUC: {e}")
            return RespuestaSIFEN('ERR', str(e), {})

    def _parsear_respuesta_evento(self, result) -> RespuestaSIFEN:
        """Parsea la respuesta de rRecepcionEvento."""
        try:
            raw    = dict(result) if result else {}
            codigo = str(raw.get('dCodRes') or raw.get('codigo') or 'ERR')
            desc   = str(raw.get('dMsgRes') or raw.get('descripcion') or 'Sin descripción')
            resp   = RespuestaSIFEN(codigo, desc, raw)
            logger.info(f"Respuesta evento: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Error parseando respuesta evento: {e}")
            return RespuestaSIFEN('ERR', str(e), {})
