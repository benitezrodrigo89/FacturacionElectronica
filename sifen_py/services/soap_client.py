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
from lxml import etree
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

    # Endpoints HTTP directos para envío
    URLS_ENDPOINT = {
        'test': 'https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl',
        'prod': 'https://sifen.set.gov.py/de/ws/sync/recibe.wsdl',
    }

    # Endpoints HTTP directos para consulta por CDC
    URLS_CONSULTA_DE = {
        'test': 'https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl',
        'prod': 'https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl',
    }

    # Endpoints HTTP directos para consulta de RUC
    URLS_CONSULTA_RUC = {
        'test': 'https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl',
        'prod': 'https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl',
    }

    # Endpoints HTTP directos para eventos (cancelación, inutilización, etc.)
    URLS_EVENTO = {
        'test': 'https://sifen-test.set.gov.py/de/ws/async/recibe-evento.wsdl',
        'prod': 'https://sifen.set.gov.py/de/ws/async/recibe-evento.wsdl',
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
    # 1. RECEPCIÓN SÍNCRONA DIRECTA (sin WSDL, HTTP POST puro)
    # ─────────────────────────────────────────────────────────
    def enviar_de_directo(self, xml_firmado: str) -> RespuestaSIFEN:
        """
        Envía un DE firmado construyendo el envelope SOAP manualmente y
        enviándolo vía HTTP POST con mTLS, sin necesitar cargar el WSDL.

        Útil cuando el WSDL no es accesible desde la IP actual.

        Args:
            xml_firmado: XML del rDE firmado (sin envelope SOAP)

        Returns:
            RespuestaSIFEN con el resultado
        """

        # Construir envelope por concatenación para preservar el xml_firmado intacto:
        # - mantiene xmlns explícito en rDE
        # - mantiene entidades &#243; etc. sin re-parsear a UTF-8 literal
        envelope_str = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">'
            '<env:Header/>'
            '<env:Body>'
            '<rEnviDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
            '<dId>1</dId>'
            f'<xDE>{xml_firmado}</xDE>'
            '</rEnviDe>'
            '</env:Body>'
            '</env:Envelope>'
        )
        envelope = envelope_str.encode('ascii')

        url     = self.URLS_ENDPOINT[self.config.ambiente]
        session = self._get_session()
        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'SOAPAction':   '',
        }

        logger.info(f"Enviando DE directo a: {url}")
        try:
            resp = session.post(
                url,
                data=envelope,
                headers=headers,
                timeout=self.timeout,
            )
        except Exception as e:
            raise SOAPException(f"Error HTTP al enviar DE: {e}") from e

        if resp.status_code not in (200, 400, 500):
            resp.raise_for_status()

        # SIFEN devuelve 400/500 con un envelope SOAP de error — parsearlo igual
        logger.debug(f"HTTP {resp.status_code} — {len(resp.content)} bytes")

        return self._parsear_respuesta_xml(resp.content)

    def consultar_de_directo(self, cdc: str) -> RespuestaSIFEN:
        """
        Consulta el estado de un DE por CDC usando HTTP POST directo (sin zeep).
        Funciona aunque el WSDL no sea accesible desde la IP actual.

        Códigos de respuesta:
            0422 → DE aprobado (incluye dProtAut)
            0420 → DE no existe o fue rechazado

        Args:
            cdc: Código de Control del Documento (44 dígitos)

        Returns:
            RespuestaSIFEN con estado, código, y número de protocolo si está aprobado
        """
        if not cdc or len(cdc) != 44:
            raise SOAPException(f"CDC inválido (debe tener 44 dígitos): {cdc!r}")

        envelope_str = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">'
            '<env:Header/>'
            '<env:Body>'
            '<rConsDE xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
            '<dId>1</dId>'
            f'<dCDC>{cdc}</dCDC>'
            '</rConsDE>'
            '</env:Body>'
            '</env:Envelope>'
        )
        envelope = envelope_str.encode('ascii')

        url     = self.URLS_CONSULTA_DE[self.config.ambiente]
        session = self._get_session()
        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'SOAPAction':   '',
        }

        logger.info(f"Consultando DE por CDC directo: {cdc[:20]}…")
        try:
            resp = session.post(url, data=envelope, headers=headers, timeout=self.timeout)
        except Exception as e:
            raise SOAPException(f"Error HTTP al consultar DE: {e}") from e

        logger.debug(f"HTTP {resp.status_code} — {len(resp.content)} bytes")
        return self._parsear_respuesta_consulta_de_xml(resp.content)

    def consultar_ruc_directo(self, ruc: str) -> RespuestaSIFEN:
        """
        Consulta datos de un RUC en el registro de la SET usando HTTP POST directo.

        Args:
            ruc: RUC a consultar (con o sin guion y DV, ej: '5722781-0' o '57227810')

        Returns:
            RespuestaSIFEN con datos del contribuyente
        """
        ruc_limpio = ruc.replace('-', '')
        envelope_str = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">'
            '<env:Header/>'
            '<env:Body>'
            '<rConsRUC xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
            '<dId>1</dId>'
            f'<dRUCCons>{ruc_limpio}</dRUCCons>'
            '</rConsRUC>'
            '</env:Body>'
            '</env:Envelope>'
        )
        envelope = envelope_str.encode('ascii')

        url     = self.URLS_CONSULTA_RUC[self.config.ambiente]
        session = self._get_session()
        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'SOAPAction':   '',
        }

        logger.info(f"Consultando RUC directo: {ruc}")
        try:
            resp = session.post(url, data=envelope, headers=headers, timeout=self.timeout)
        except Exception as e:
            raise SOAPException(f"Error HTTP al consultar RUC: {e}") from e

        logger.debug(f"HTTP {resp.status_code} — {len(resp.content)} bytes")
        return self._parsear_respuesta_xml(resp.content)

    def enviar_soap_bytes(self, soap_bytes: bytes) -> RespuestaSIFEN:
        """
        Envía un envelope SOAP ya construido (bytes crudos) sin modificarlo.
        Preserva la firma digital intacta.

        Args:
            soap_bytes: Contenido completo del archivo SOAP listo para enviar

        Returns:
            RespuestaSIFEN con el resultado
        """
        url     = self.URLS_ENDPOINT[self.config.ambiente]
        session = self._get_session()
        # Deshabilitar Accept-Encoding para que el servidor no comprima la respuesta
        session.headers.pop('Accept-Encoding', None)
        headers = {
            'Content-Type':    'application/soap+xml;charset=UTF-8',
            'Accept-Encoding': 'identity',
            'Accept':          'application/soap+xml',
            'Connection':      'close',
        }

        logger.info(f"Enviando SOAP bytes a: {url} ({len(soap_bytes)} bytes)")
        try:
            resp = session.post(
                url,
                data=soap_bytes,
                headers=headers,
                timeout=self.timeout,
            )
        except Exception as e:
            raise SOAPException(f"Error HTTP: {e}") from e

        logger.debug(f"HTTP {resp.status_code} — {len(resp.content)} bytes")
        logger.debug(f"Headers respuesta: {dict(resp.headers)}")
        return self._parsear_respuesta_xml(resp.content)

    def _parsear_respuesta_xml(self, xml_bytes: bytes) -> RespuestaSIFEN:
        """Parsea la respuesta SOAP XML de SIFEN directamente."""
        try:
            root   = etree.fromstring(xml_bytes)
            ns     = 'http://ekuatia.set.gov.py/sifen/xsd'
            codigo = ''
            desc   = ''
            prot   = root.find('.//{%s}rProtDe' % ns)
            if prot is not None:
                est    = prot.find('{%s}dEstRes' % ns)
                respr  = prot.find('.//{%s}dCodRes' % ns)
                msgr   = prot.find('.//{%s}dMsgRes' % ns)
                prot_a = prot.find('{%s}dProtAut' % ns)
                codigo = respr.text.strip() if respr is not None else ''
                desc   = msgr.text.strip()  if msgr  is not None else ''
                if prot_a is not None:
                    logger.success(f"Protocolo de autorización: {prot_a.text.strip()}")
            resp = RespuestaSIFEN(codigo, desc, {'xml': xml_bytes.decode('utf-8', errors='replace')})
            logger.info(f"Respuesta SIFEN: {resp}")
            return resp
        except Exception as e:
            logger.error(f"Error parseando respuesta XML: {e}")
            return RespuestaSIFEN('ERR', str(e), {})

    # ─────────────────────────────────────────────────────────
    # 1b. RECEPCIÓN SÍNCRONA vía WSDL/zeep
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

    def enviar_evento_soap(self, soap_str: str) -> RespuestaSIFEN:
        """
        Envía el SOAP de evento completo (ya firmado) al endpoint de eventos.
        Usa el envelope generado por Node.js con <rEnviEventoDe>/<dEvReg>
        en lugar de construir uno nuevo.

        Args:
            soap_str: SOAP completo firmado (string o bytes)

        Returns:
            RespuestaSIFEN con el resultado
        """
        url     = self.URLS_EVENTO[self.config.ambiente]
        session = self._get_session()
        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'SOAPAction':   '',
        }
        soap_bytes = soap_str.encode('utf-8') if isinstance(soap_str, str) else soap_str

        logger.info(f"Enviando evento SOAP a: {url} ({len(soap_bytes)} bytes)")
        logger.debug(f"SOAP evento (primeros 2000 chars):\n{soap_bytes[:2000].decode('utf-8', errors='replace')}")
        try:
            resp = session.post(url, data=soap_bytes, headers=headers, timeout=self.timeout)
        except Exception as e:
            raise SOAPException(f"Error HTTP al enviar evento: {e}") from e

        if resp.status_code not in (200, 400, 500):
            resp.raise_for_status()

        logger.debug(f"HTTP {resp.status_code} — {len(resp.content)} bytes")
        logger.debug(f"Respuesta evento SIFEN:\n{resp.content.decode('utf-8', errors='replace')}")
        return self._parsear_respuesta_evento_xml(resp.content)

    def enviar_evento_directo(self, xml_evento_firmado: str) -> RespuestaSIFEN:
        """
        Envía un evento firmado via HTTP POST directo (sin zeep/WSDL).
        Mismo patrón que enviar_de_directo: construye el envelope por
        concatenación de strings para preservar exactamente el XML firmado.

        Args:
            xml_evento_firmado: <gGroupGesEve> firmado (sin envelope SOAP)

        Returns:
            RespuestaSIFEN con el resultado
        """
        envelope_str = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">'
            '<env:Header/>'
            '<env:Body>'
            '<rEnviEventoDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
            '<dId>1</dId>'
            f'<dEvReg>{xml_evento_firmado}</dEvReg>'
            '</rEnviEventoDe>'
            '</env:Body>'
            '</env:Envelope>'
        )
        envelope = envelope_str.encode('ascii')
        url     = self.URLS_EVENTO[self.config.ambiente]
        session = self._get_session()
        headers = {
            'Content-Type': 'application/soap+xml;charset=UTF-8',
            'SOAPAction':   '',
        }
        logger.info(f"Enviando evento directo a: {url}")
        logger.debug(f"Evento envelope (primeros 1500 chars):\n{envelope[:1500].decode('ascii', errors='replace')}")
        try:
            resp = session.post(url, data=envelope, headers=headers, timeout=self.timeout)
        except Exception as e:
            raise SOAPException(f"Error HTTP al enviar evento: {e}") from e

        if resp.status_code not in (200, 400, 500):
            resp.raise_for_status()

        logger.debug(f"HTTP {resp.status_code} — {len(resp.content)} bytes")
        logger.debug(f"Respuesta evento:\n{resp.content.decode('utf-8', errors='replace')}")
        return self._parsear_respuesta_evento_xml(resp.content)

    def _parsear_respuesta_evento_xml(self, xml_bytes: bytes) -> RespuestaSIFEN:
        """Parsea la respuesta SOAP de rRecepcionEvento (HTTP directo)."""
        try:
            root = etree.fromstring(xml_bytes)
            ns   = 'http://ekuatia.set.gov.py/sifen/xsd'

            cod_el = root.find('.//{%s}dCodRes' % ns)
            msg_el = root.find('.//{%s}dMsgRes' % ns)
            codigo = cod_el.text.strip() if cod_el is not None and cod_el.text else ''
            desc   = msg_el.text.strip() if msg_el is not None and msg_el.text else ''

            if not codigo:
                fault = root.find('.//{http://www.w3.org/2003/05/soap-envelope}Fault')
                if fault is not None:
                    codigo = 'ERR'
                    txt = fault.find('.//{http://www.w3.org/2003/05/soap-envelope}Text')
                    desc = txt.text if txt is not None else 'SOAP Fault'

            xml_str = xml_bytes.decode('utf-8', errors='replace')
            return RespuestaSIFEN(codigo or 'ERR', desc or 'Sin descripción', {'xml': xml_str})
        except Exception as e:
            logger.error(f"Error parseando respuesta evento XML: {e}")
            xml_str = xml_bytes.decode('utf-8', errors='replace') if xml_bytes else ''
            return RespuestaSIFEN('ERR', str(e), {'xml': xml_str})

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

    def _parsear_respuesta_consulta_de_xml(self, xml_bytes: bytes) -> RespuestaSIFEN:
        """
        Parsea la respuesta SOAP de rRetConsDE (consulta por CDC).

        La respuesta aprobada incluye:
            dCodRes  = 0422
            dMsgRes  = 'DE aprobado'
            dProtAut = número de protocolo de autorización
            dEstDE   = 'Aprobado'
            dFecProc = fecha de procesamiento
        """
        try:
            root = etree.fromstring(xml_bytes)
            ns   = 'http://ekuatia.set.gov.py/sifen/xsd'

            prot = root.find('.//{%s}rProtDe' % ns)
            if prot is None:
                # Respuesta de error sin rProtDe (ej. 0160 desde DataPower)
                return self._parsear_respuesta_xml(xml_bytes)

            def _text(tag):
                el = prot.find('.//{%s}%s' % (ns, tag))
                return el.text.strip() if el is not None and el.text else ''

            codigo   = _text('dCodRes')
            desc     = _text('dMsgRes')
            estado   = _text('dEstDE') or _text('dEstRes')
            protocolo = _text('dProtAut')
            cdc      = _text('Id')
            fecha    = _text('dFecProc')

            raw = {
                'xml':       xml_bytes.decode('utf-8', errors='replace'),
                'cdc':       cdc,
                'estado':    estado,
                'protocolo': protocolo,
                'fecha':     fecha,
            }

            resp = RespuestaSIFEN(codigo, desc, raw)
            if protocolo:
                logger.success(f"CDC consultado: {cdc} | Estado: {estado} | Protocolo: {protocolo}")
            else:
                logger.info(f"CDC consultado: {cdc} | Estado: {estado} | Código: {codigo}")
            return resp
        except Exception as e:
            logger.error(f"Error parseando respuesta consulta DE: {e}")
            return RespuestaSIFEN('ERR', str(e), {})

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
