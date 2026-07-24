"""
Tests para core/exceptions.py
"""
import pytest
from sifen_py.core.exceptions import (
    SifenException,
    ValidationException,
    SignatureException,
    SOAPException,
    CertificateException,
    CDCException,
    XMLGenerationException,
    BatchException,
    EventException,
    KuDEException,
    ConfigurationException,
)


class TestSifenException:
    def test_mensaje_basico(self):
        e = SifenException("Error base")
        assert str(e) == "Error base"
        assert e.message == "Error base"

    def test_con_codigo(self):
        e = SifenException("Error", code="ERR001")
        assert str(e) == "[ERR001] Error"
        assert e.code == "ERR001"

    def test_sin_codigo_no_incluye_brackets(self):
        e = SifenException("Error sin código")
        assert '[' not in str(e)

    def test_details_default_dict_vacio(self):
        e = SifenException("Error")
        assert e.details == {}

    def test_details_personalizado(self):
        e = SifenException("Error", details={"key": "value"})
        assert e.details["key"] == "value"

    def test_hereda_de_exception(self):
        e = SifenException("Error")
        assert isinstance(e, Exception)

    def test_se_puede_lanzar_y_capturar(self):
        with pytest.raises(SifenException, match="Error base"):
            raise SifenException("Error base")


class TestSubclases:
    """Verifica que todas las subclases heredan correctamente."""

    @pytest.mark.parametrize("exc_class", [
        ValidationException,
        SignatureException,
        SOAPException,
        CertificateException,
        CDCException,
        XMLGenerationException,
        BatchException,
        EventException,
        KuDEException,
        ConfigurationException,
    ])
    def test_hereda_de_sifen_exception(self, exc_class):
        assert issubclass(exc_class, SifenException)

    @pytest.mark.parametrize("exc_class", [
        ValidationException,
        SignatureException,
        SOAPException,
        CertificateException,
        CDCException,
        XMLGenerationException,
        BatchException,
        EventException,
        KuDEException,
        ConfigurationException,
    ])
    def test_se_puede_instanciar_con_mensaje(self, exc_class):
        e = exc_class("mensaje de prueba")
        assert "mensaje de prueba" in str(e)

    @pytest.mark.parametrize("exc_class", [
        ValidationException,
        SignatureException,
        SOAPException,
        CertificateException,
        CDCException,
        XMLGenerationException,
        BatchException,
        EventException,
        KuDEException,
        ConfigurationException,
    ])
    def test_se_captura_como_sifen_exception(self, exc_class):
        with pytest.raises(SifenException):
            raise exc_class("error")

    @pytest.mark.parametrize("exc_class", [
        ValidationException,
        SignatureException,
        SOAPException,
        CertificateException,
        CDCException,
        XMLGenerationException,
        BatchException,
        EventException,
        KuDEException,
        ConfigurationException,
    ])
    def test_acepta_code_y_details(self, exc_class):
        e = exc_class("msg", code="X01", details={"a": 1})
        assert e.code == "X01"
        assert e.details["a"] == 1
