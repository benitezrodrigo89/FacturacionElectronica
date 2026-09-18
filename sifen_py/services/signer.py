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
        Firma un XML con el certificado digital según XMLDSig Enveloped Signature.

        Algoritmo (Manual Técnico SIFEN v150 sección 7.6):
          1. DigestValue = SHA256(exc-C14N(elemento <DE>))
          2. Construir Signature y anexar al <rDE>
          3. Canonicalizar SignedInfo DENTRO del documento para heredar namespaces
          4. SignatureValue = RSA-SHA256(inc-C14N(SignedInfo-en-contexto))

        Args:
            xml_string: XML a firmar (string o bytes)

        Returns:
            XML firmado sin declaración XML ni whitespace entre etiquetas
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        try:
            if isinstance(xml_string, str):
                xml_string = xml_string.encode('utf-8')

            root = etree.fromstring(xml_string)

            logger.info("Iniciando proceso de firma digital...")

            sifen_ns = "http://ekuatia.set.gov.py/sifen/xsd"
            ds_ns    = "http://www.w3.org/2000/09/xmldsig#"

            # ── 1. Localizar <DE> (documento) o <rEve> (evento) ─────────────
            de_elem = root.find('{%s}DE' % sifen_ns)
            if de_elem is None:
                # Puede ser un evento: <gGroupGesEve><rGesEve><rEve Id="1">
                reve_elem = root.find('.//{%s}rEve' % sifen_ns)
                if reve_elem is not None:
                    return self._firmar_xml_evento(root, reve_elem)
                raise SignatureException("No se encontró el elemento <DE> ni <rEve> en el XML")
            cdc = de_elem.get('Id', '')

            # ── 2. DigestValue sobre <DE> con C14N exclusivo ─────────────────
            # Transforms declarados: enveloped-signature (no-op) + exc-C14N
            de_c14n = etree.tostring(de_elem, method='c14n', exclusive=True)
            digest_b64 = base64.b64encode(hashlib.sha256(de_c14n).digest()).decode()

            # ── 3. Construir estructura Signature (SignatureValue vacío) ──────
            nsmap     = {None: ds_ns}
            signature = etree.Element("{%s}Signature" % ds_ns, nsmap=nsmap)

            signed_info = etree.SubElement(signature, "{%s}SignedInfo" % ds_ns)

            etree.SubElement(signed_info, "{%s}CanonicalizationMethod" % ds_ns,
                             Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#")
            etree.SubElement(signed_info, "{%s}SignatureMethod" % ds_ns,
                             Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")

            reference = etree.SubElement(signed_info, "{%s}Reference" % ds_ns,
                                         URI='#' + cdc)
            transforms = etree.SubElement(reference, "{%s}Transforms" % ds_ns)
            etree.SubElement(transforms, "{%s}Transform" % ds_ns,
                             Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
            etree.SubElement(transforms, "{%s}Transform" % ds_ns,
                             Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#")

            etree.SubElement(reference, "{%s}DigestMethod" % ds_ns,
                             Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
            dv_elem = etree.SubElement(reference, "{%s}DigestValue" % ds_ns)
            dv_elem.text = digest_b64

            sig_value_elem = etree.SubElement(signature, "{%s}SignatureValue" % ds_ns)

            key_info  = etree.SubElement(signature, "{%s}KeyInfo" % ds_ns)
            x509_data = etree.SubElement(key_info,  "{%s}X509Data" % ds_ns)
            x509_cert = etree.SubElement(x509_data, "{%s}X509Certificate" % ds_ns)
            cert_pem  = self.certificate.public_bytes(serialization.Encoding.PEM)
            cert_b64  = (cert_pem.decode()
                         .replace('-----BEGIN CERTIFICATE-----', '')
                         .replace('-----END CERTIFICATE-----', '')
                         .replace('\n', ''))
            x509_cert.text = cert_b64

            # ── 4. Insertar Signature y gCamFuFD en el árbol ANTES de firmar ──
            # Ambos elementos deben estar en el árbol cuando se canonicaliza
            # SignedInfo, para que SIFEN compute la misma C14N al verificar.
            root.append(signature)

            gcam = etree.SubElement(root, "{%s}gCamFuFD" % sifen_ns)
            dcar = etree.SubElement(gcam, "{%s}dCarQR" % sifen_ns)
            dcar.text = self._generar_car_qr(de_elem, cdc, digest_b64)

            # ── 5. Canonicalizar SignedInfo con exclusive C14N ────────────────
            # Exclusive C14N evita herencia de xmlns:xsi del padre <rDE>
            si_in_doc = root.find('.//{%s}SignedInfo' % ds_ns)
            signed_info_c14n = etree.tostring(si_in_doc, method='c14n', exclusive=True)

            # ── 6. Firmar y fijar SignatureValue ─────────────────────────────
            sig_bytes = self.private_key.sign(
                signed_info_c14n,
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            sig_value_elem.text = base64.b64encode(sig_bytes).decode()

            # Sin declaración XML ni whitespace (Manual Técnico sección 7.2.4)
            # ASCII encoding convierte ó→&#243; etc. para compatibilidad con SoapUI/Windows
            xml_firmado = etree.tostring(root, pretty_print=False, encoding='ASCII', xml_declaration=False).decode('ascii')

            logger.success("XML firmado exitosamente")
            return xml_firmado

        except etree.XMLSyntaxError as e:
            raise SignatureException(f"XML inválido: {str(e)}", code="INVALID_XML")
        except SignatureException:
            raise
        except Exception as e:
            logger.exception("Error al firmar XML")
            raise SignatureException(f"Error al firmar el XML: {str(e)}", code="SIGNATURE_ERROR")

    def _firmar_xml_evento(self, root, reve_elem) -> str:
        """
        Firma un XML de evento SIFEN usando <rEve> como referencia.
        La firma se inserta en <rGesEve> (padre de <rEve>), como hermano
        posterior a <rEve>. No genera gCamFuFD (solo para DEs).
        """
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        ds_ns   = "http://www.w3.org/2000/09/xmldsig#"
        reve_id = reve_elem.get('Id', '1')

        # 1. DigestValue sobre <rEve>
        reve_c14n  = etree.tostring(reve_elem, method='c14n', exclusive=True)
        digest_b64 = base64.b64encode(hashlib.sha256(reve_c14n).digest()).decode()

        # 2. Construir estructura Signature
        nsmap     = {None: ds_ns}
        signature = etree.Element("{%s}Signature" % ds_ns, nsmap=nsmap)

        signed_info = etree.SubElement(signature, "{%s}SignedInfo" % ds_ns)
        etree.SubElement(signed_info, "{%s}CanonicalizationMethod" % ds_ns,
                         Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#")
        etree.SubElement(signed_info, "{%s}SignatureMethod" % ds_ns,
                         Algorithm="http://www.w3.org/2001/04/xmldsig-more#rsa-sha256")

        reference = etree.SubElement(signed_info, "{%s}Reference" % ds_ns, URI='#' + reve_id)
        transforms = etree.SubElement(reference, "{%s}Transforms" % ds_ns)
        etree.SubElement(transforms, "{%s}Transform" % ds_ns,
                         Algorithm="http://www.w3.org/2000/09/xmldsig#enveloped-signature")
        etree.SubElement(transforms, "{%s}Transform" % ds_ns,
                         Algorithm="http://www.w3.org/2001/10/xml-exc-c14n#")
        etree.SubElement(reference, "{%s}DigestMethod" % ds_ns,
                         Algorithm="http://www.w3.org/2001/04/xmlenc#sha256")
        dv_elem      = etree.SubElement(reference, "{%s}DigestValue" % ds_ns)
        dv_elem.text = digest_b64

        sig_value_elem = etree.SubElement(signature, "{%s}SignatureValue" % ds_ns)

        key_info  = etree.SubElement(signature, "{%s}KeyInfo" % ds_ns)
        x509_data = etree.SubElement(key_info, "{%s}X509Data" % ds_ns)
        x509_cert = etree.SubElement(x509_data, "{%s}X509Certificate" % ds_ns)
        cert_pem  = self.certificate.public_bytes(serialization.Encoding.PEM)
        cert_b64  = (cert_pem.decode()
                     .replace('-----BEGIN CERTIFICATE-----', '')
                     .replace('-----END CERTIFICATE-----', '')
                     .replace('\n', ''))
        x509_cert.text = cert_b64

        # 3. Insertar Signature en <rGesEve> (padre de <rEve>)
        rgeseve = reve_elem.getparent()
        rgeseve.append(signature)

        # 4. Canonicalizar SignedInfo en contexto del documento
        si_in_doc        = root.find('.//{%s}SignedInfo' % ds_ns)
        signed_info_c14n = etree.tostring(si_in_doc, method='c14n', exclusive=True)

        # 5. Firmar y fijar SignatureValue
        sig_bytes = self.private_key.sign(
            signed_info_c14n,
            padding.PKCS1v15(),
            hashes.SHA256()
        )
        sig_value_elem.text = base64.b64encode(sig_bytes).decode()

        xml_firmado = etree.tostring(
            root, pretty_print=False, encoding='ASCII', xml_declaration=False
        ).decode('ascii')

        logger.success("Evento XML firmado exitosamente")
        return xml_firmado

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

    def _generar_car_qr(self, de_elem, cdc: str, digest_value_b64: str) -> str:
        """
        Genera dCarQR (campo J002) según Manual Técnico SIFEN v150 sección 13.8.
        Parámetros: nVersion, Id, dFeEmiDE(hex), dRucRec, dTotGralOpe, dTotIVA,
                    cItems, DigestValue(hex), IdCSC → SHA256(params + CSC) = cHashQR
        """
        sifen_ns = "http://ekuatia.set.gov.py/sifen/xsd"

        def _txt(xpath):
            el = de_elem.find('.//{%s}%s' % (sifen_ns, xpath))
            return el.text.strip() if el is not None and el.text else ''

        def _to_hex(s: str) -> str:
            return s.encode('utf-8').hex()

        url_base = (
            'https://ekuatia.set.gov.py/consultas-test/qr?'
            if self.config.ambiente == 'test'
            else 'https://ekuatia.set.gov.py/consultas/qr?'
        )

        fe_emi_hex     = _to_hex(_txt('dFeEmiDE'))
        ruc_rec        = _txt('dRucRec') or '0'
        tot_gral       = _txt('dTotGralOpe') or '0'
        tot_iva        = _txt('dTotIVA') or '0'
        # Contar ítems: cantidad de elementos dCodInt (uno por ítem)
        c_items        = str(len(de_elem.findall('.//{%s}gCamItem' % sifen_ns)))
        digest_hex     = digest_value_b64.encode('utf-8').hex()
        csc_id         = getattr(self.config, 'csc_id', '0001')
        csc_val        = getattr(self.config, 'csc', '')

        params = (
            f"nVersion=150"
            f"&Id={cdc}"
            f"&dFeEmiDE={fe_emi_hex}"
            f"&dRucRec={ruc_rec}"
            f"&dTotGralOpe={tot_gral}"
            f"&dTotIVA={tot_iva}"
            f"&cItems={c_items}"
            f"&DigestValue={digest_hex}"
            f"&IdCSC={csc_id}"
        )

        # CSC se concatena directamente sin "&" ni nombre de parámetro
        hash_input = params + csc_val
        c_hash_qr  = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()

        return url_base + params + f"&cHashQR={c_hash_qr}"

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
