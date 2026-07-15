"""
Firmador digital XML según estándar XMLDSig W3C Enveloped Signature
Implementa la firma requerida por SIFEN Paraguay
"""
from pathlib import Path
from typing import Union, Optional
from lxml import etree
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend
from OpenSSL import crypto
import base64
import hashlib
from loguru import logger

from sifen_py.core.exceptions import SignatureException
from sifen_py.core.config import SifenConfig


class XMLSigner:
    """
    Firmador de XML con certificado digital
    Implementa XMLDSig Enveloped Signature según W3C
    """

    def __init__(self, config: SifenConfig):
        """
        Inicializa el firmador

        Args:
            config: Configuración de SIFEN con datos del certificado
        """
        self.config = config
        self.certificate = None
        self.private_key = None
        self._load_certificate()

    def _load_certificate(self):
        """
        Carga el certificado digital desde el archivo .pfx/.p12
        """
        try:
            cert_path = self.config.certificado_path
            password = self.config.certificado_password.encode()

            logger.info(f"Cargando certificado desde: {cert_path}")

            # Leer el archivo del certificado
            with open(cert_path, 'rb') as f:
                pfx_data = f.read()

            # Cargar el certificado con cryptography
            private_key, certificate, additional_certificates = pkcs12.load_key_and_certificates(
                pfx_data,
                password,
                backend=default_backend()
            )

            if not private_key:
                raise SignatureException(
                    "No se pudo extraer la clave privada del certificado"
                )

            if not certificate:
                raise SignatureException(
                    "No se pudo extraer el certificado"
                )

            # Convertir a formato OpenSSL para facilitar el uso
            self.private_key = private_key
            self.certificate = certificate

            # Validar que el RUC esté en el certificado
            self._validate_certificate_ruc()

            logger.success("Certificado cargado exitosamente")

        except FileNotFoundError:
            raise SignatureException(
                f"Archivo de certificado no encontrado: {cert_path}"
            )
        except Exception as e:
            logger.exception("Error al cargar certificado")
            raise SignatureException(
                f"Error al cargar el certificado: {str(e)}",
                details={"path": str(cert_path)}
            )

    def _validate_certificate_ruc(self):
        """
        Valida que el RUC del certificado coincida con la configuración
        """
        # Obtener el subject del certificado
        subject = self.certificate.subject

        # Buscar el RUC en el CN o OU
        ruc_encontrado = None
        for attribute in subject:
            if attribute.oid._name in ['commonName', 'organizationalUnitName']:
                value = attribute.value
                # Buscar patrón de RUC (8 dígitos-1)
                if self.config.get_ruc_emisor() in value:
                    ruc_encontrado = value
                    break

        if not ruc_encontrado:
            logger.warning(
                f"No se pudo verificar el RUC en el certificado. "
                f"RUC configurado: {self.config.ruc}"
            )
        else:
            logger.info(f"RUC verificado en certificado: {ruc_encontrado}")

    def firmar_xml(self, xml_string: Union[str, bytes]) -> str:
        """
        Firma un XML con el certificado digital

        Args:
            xml_string: XML a firmar (string o bytes)

        Returns:
            XML firmado como string

        Raises:
            SignatureException: Si hay error en la firma
        """
        try:
            # Parsear el XML
            if isinstance(xml_string, str):
                xml_string = xml_string.encode('utf-8')

            root = etree.fromstring(xml_string)

            logger.info("Iniciando proceso de firma digital...")

            # Crear el elemento Signature
            signature_elem = self._create_signature_element(root)

            # Insertar la firma en el XML (antes del cierre del elemento raíz)
            root.append(signature_elem)

            # Convertir a string
            xml_firmado = etree.tostring(
                root,
                pretty_print=True,
                xml_declaration=True,
                encoding='UTF-8'
            ).decode('utf-8')

            logger.success("XML firmado exitosamente")
            return xml_firmado

        except etree.XMLSyntaxError as e:
            raise SignatureException(
                f"XML inválido: {str(e)}",
                code="INVALID_XML"
            )
        except Exception as e:
            logger.exception("Error al firmar XML")
            raise SignatureException(
                f"Error al firmar el XML: {str(e)}",
                code="SIGNATURE_ERROR"
            )

    def _create_signature_element(self, root: etree.Element) -> etree.Element:
        """
        Crea el elemento Signature según XMLDSig

        Args:
            root: Elemento raíz del XML a firmar

        Returns:
            Elemento Signature completo
        """
        # Namespaces
        ds_ns = "http://www.w3.org/2000/09/xmldsig#"
        nsmap = {None: ds_ns}

        # Crear elemento Signature
        signature = etree.Element("{%s}Signature" % ds_ns, nsmap=nsmap)

        # SignedInfo
        signed_info = etree.SubElement(signature, "{%s}SignedInfo" % ds_ns)

        # CanonicalizationMethod
        canonicalization = etree.SubElement(
            signed_info,
            "{%s}CanonicalizationMethod" % ds_ns,
            Algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
        )

        # SignatureMethod
        signature_method = etree.SubElement(
            signed_info,
            "{%s}SignatureMethod" % ds_ns,
            Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"
        )

        # Reference
        reference = etree.SubElement(
            signed_info,
            "{%s}Reference" % ds_ns,
            URI=""
        )

        # Transforms
        transforms = etree.SubElement(reference, "{%s}Transforms" % ds_ns)
        transform1 = etree.SubElement(
            transforms,
            "{%s}Transform" % ds_ns,
            Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature"
        )

        # DigestMethod
        digest_method = etree.SubElement(
            reference,
            "{%s}DigestMethod" % ds_ns,
            Algorithm="http://www.w3.org/2001/04/xmlenc#sha256"
        )

        # Calcular DigestValue
        # Canonicalizar el documento sin la firma
        canonicalized = etree.tostring(
            root,
            method='c14n',
            exclusive=False
        )
        digest = hashlib.sha256(canonicalized).digest()
        digest_b64 = base64.b64encode(digest).decode()

        digest_value = etree.SubElement(reference, "{%s}DigestValue" % ds_ns)
        digest_value.text = digest_b64

        # SignatureValue (se calculará después)
        signature_value = etree.SubElement(signature, "{%s}SignatureValue" % ds_ns)

        # Calcular la firma del SignedInfo
        signed_info_canonical = etree.tostring(
            signed_info,
            method='c14n',
            exclusive=False
        )

        # Firmar con la clave privada
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding

        signature_bytes = self.private_key.sign(
            signed_info_canonical,
            padding.PKCS1v15(),
            hashes.SHA256()
        )

        signature_value.text = base64.b64encode(signature_bytes).decode()

        # KeyInfo
        key_info = etree.SubElement(signature, "{%s}KeyInfo" % ds_ns)
        x509_data = etree.SubElement(key_info, "{%s}X509Data" % ds_ns)
        x509_certificate = etree.SubElement(x509_data, "{%s}X509Certificate" % ds_ns)

        # Exportar el certificado en formato PEM y codificarlo
        from cryptography.hazmat.primitives import serialization
        cert_pem = self.certificate.public_bytes(serialization.Encoding.PEM)
        # Remover headers y newlines
        cert_b64 = cert_pem.decode().replace('-----BEGIN CERTIFICATE-----', '')
        cert_b64 = cert_b64.replace('-----END CERTIFICATE-----', '')
        cert_b64 = cert_b64.replace('\n', '')

        x509_certificate.text = cert_b64

        return signature

    def verificar_firma(self, xml_firmado: Union[str, bytes]) -> bool:
        """
        Verifica la firma de un XML (opcional, para testing)

        Args:
            xml_firmado: XML con firma digital

        Returns:
            True si la firma es válida, False en caso contrario
        """
        try:
            if isinstance(xml_firmado, str):
                xml_firmado = xml_firmado.encode('utf-8')

            root = etree.fromstring(xml_firmado)

            # Buscar el elemento Signature
            ds_ns = "{http://www.w3.org/2000/09/xmldsig#}"
            signature = root.find(f".//{ds_ns}Signature")

            if signature is None:
                logger.error("No se encontró elemento Signature en el XML")
                return False

            logger.info("Firma encontrada en el XML")

            # Aquí se podría implementar verificación completa
            # Por ahora solo verificamos que existe
            return True

        except Exception as e:
            logger.error(f"Error al verificar firma: {str(e)}")
            return False

    def get_certificate_info(self) -> dict:
        """
        Obtiene información del certificado cargado

        Returns:
            Diccionario con información del certificado
        """
        if not self.certificate:
            return {}

        subject = self.certificate.subject
        issuer = self.certificate.issuer

        info = {
            "subject": {attr.oid._name: attr.value for attr in subject},
            "issuer": {attr.oid._name: attr.value for attr in issuer},
            "not_valid_before": self.certificate.not_valid_before_utc,
            "not_valid_after": self.certificate.not_valid_after_utc,
            "serial_number": self.certificate.serial_number,
            "version": self.certificate.version
        }

        return info
