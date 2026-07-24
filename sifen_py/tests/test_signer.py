"""
Tests para services/signer.py — XMLSigner.
Los tests que requieren certificado real se marcan skip;
los que solo validan lógica XML usan mocks del certificado.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
from lxml import etree

from sifen_py.services.signer import XMLSigner
from sifen_py.core.exceptions import SignatureException


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _mock_private_key():
    """Clave privada mock que simula firmar bytes."""
    key = MagicMock()
    key.sign.return_value = b'\x00' * 64
    return key


def _mock_certificate():
    """Certificado mock con subject mínimo."""
    from cryptography.x509 import NameAttribute
    from cryptography.x509.oid import NameOID
    from unittest.mock import PropertyMock

    cert = MagicMock()

    attr = MagicMock()
    attr.oid._name = 'commonName'
    attr.value = 'RUC: 80069563-1 / TIPS S.A.'
    cert.subject.__iter__ = MagicMock(return_value=iter([attr]))

    # public_bytes devuelve PEM falso
    pem = b'-----BEGIN CERTIFICATE-----\nABCD\n-----END CERTIFICATE-----\n'
    cert.public_bytes.return_value = pem

    return cert


def _build_signer(config_test):
    """Construye XMLSigner salteando _load_certificate."""
    with patch.object(XMLSigner, '_load_certificate', return_value=None):
        signer = XMLSigner(config_test)
    signer.private_key = _mock_private_key()
    signer.certificate = _mock_certificate()
    return signer


# ─── Inicialización ───────────────────────────────────────────────────────────

class TestXMLSignerInit:
    def test_archivo_no_encontrado_lanza_excepcion(self, config_test):
        with patch('builtins.open', side_effect=FileNotFoundError):
            with pytest.raises(SignatureException, match='no encontrado'):
                XMLSigner(config_test)

    def test_pfx_invalido_lanza_excepcion(self, config_test):
        with patch('builtins.open', mock_open(read_data=b'datos_invalidos')):
            with pytest.raises(SignatureException):
                XMLSigner(config_test)


# ─── firmar_xml ───────────────────────────────────────────────────────────────

class TestFirmarXml:
    def test_retorna_string(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        assert isinstance(resultado, str)

    def test_resultado_es_xml_valido(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        root = etree.fromstring(resultado.encode())
        assert root is not None

    def test_contiene_elemento_signature(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        root = etree.fromstring(resultado.encode())
        ns = '{http://www.w3.org/2000/09/xmldsig#}'
        sig = root.find(f'.//{ns}Signature')
        assert sig is not None

    def test_contiene_signed_info(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        root = etree.fromstring(resultado.encode())
        ns = '{http://www.w3.org/2000/09/xmldsig#}'
        signed_info = root.find(f'.//{ns}SignedInfo')
        assert signed_info is not None

    def test_contiene_signature_value(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        root = etree.fromstring(resultado.encode())
        ns = '{http://www.w3.org/2000/09/xmldsig#}'
        sv = root.find(f'.//{ns}SignatureValue')
        assert sv is not None
        assert sv.text  # no vacío

    def test_contiene_x509_certificate(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        root = etree.fromstring(resultado.encode())
        ns = '{http://www.w3.org/2000/09/xmldsig#}'
        x509 = root.find(f'.//{ns}X509Certificate')
        assert x509 is not None
        assert x509.text  # tiene datos del certificado

    def test_contiene_digest_value(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        root = etree.fromstring(resultado.encode())
        ns = '{http://www.w3.org/2000/09/xmldsig#}'
        dv = root.find(f'.//{ns}DigestValue')
        assert dv is not None
        assert dv.text

    def test_acepta_bytes(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple.encode('utf-8'))
        assert isinstance(resultado, str)

    def test_xml_invalido_lanza_excepcion(self, config_test):
        signer = _build_signer(config_test)
        with pytest.raises(SignatureException):
            signer.firmar_xml('esto no es xml válido <<<')

    def test_xml_vacio_lanza_excepcion(self, config_test):
        signer = _build_signer(config_test)
        with pytest.raises(SignatureException):
            signer.firmar_xml('')

    def test_firma_preserva_contenido_original(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        root = etree.fromstring(resultado.encode())
        # El elemento raíz del XML original debe seguir presente
        assert 'rDE' in root.tag

    def test_algoritmo_canonicalizacion_correcto(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        assert 'xml-exc-c14n' in resultado

    def test_algoritmo_firma_rsa_sha256(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        assert 'rsa-sha256' in resultado

    def test_digest_method_sha256(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        resultado = signer.firmar_xml(xml_de_simple)
        assert 'xmlenc#sha256' in resultado


# ─── verificar_firma ─────────────────────────────────────────────────────────

class TestVerificarFirma:
    def test_xml_con_signature_retorna_true(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        xml_firmado = signer.firmar_xml(xml_de_simple)
        assert signer.verificar_firma(xml_firmado) is True

    def test_xml_sin_signature_retorna_false(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        assert signer.verificar_firma(xml_de_simple) is False

    def test_xml_invalido_retorna_false(self, config_test):
        signer = _build_signer(config_test)
        assert signer.verificar_firma('no es xml') is False

    def test_acepta_bytes(self, config_test, xml_de_simple):
        signer = _build_signer(config_test)
        xml_firmado = signer.firmar_xml(xml_de_simple)
        assert signer.verificar_firma(xml_firmado.encode('utf-8')) is True


# ─── get_certificate_info ────────────────────────────────────────────────────

class TestGetCertificateInfo:
    def test_sin_certificado_retorna_dict_vacio(self, config_test):
        with patch.object(XMLSigner, '_load_certificate', return_value=None):
            signer = XMLSigner(config_test)
        signer.certificate = None
        assert signer.get_certificate_info() == {}

    def test_con_certificado_retorna_claves_esperadas(self, config_test):
        signer = _build_signer(config_test)
        info = signer.get_certificate_info()
        assert 'subject' in info
        assert 'issuer' in info
