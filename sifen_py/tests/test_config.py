"""
Tests para core/config.py — SifenConfig
"""
import pytest
from pathlib import Path
from sifen_py.core.config import SifenConfig
from sifen_py.core.exceptions import ConfigurationException


# ─── Creación válida ──────────────────────────────────────────────────────────

class TestSifenConfigCreacion:
    def test_crea_config_test(self, cert_pfx_path):
        cfg = SifenConfig(
            ambiente='test',
            ruc='80069563-1',
            razon_social='TIPS S.A.',
            certificado_path=cert_pfx_path,
            certificado_password='pass',
            csc='00000001',
        )
        assert cfg.ambiente == 'test'
        assert cfg.ruc == '80069563-1'

    def test_crea_config_prod(self, cert_pfx_path):
        cfg = SifenConfig(
            ambiente='prod',
            ruc='12345678-9',
            razon_social='EMPRESA S.A.',
            certificado_path=cert_pfx_path,
            certificado_password='pass',
            csc='99999999',
        )
        assert cfg.ambiente == 'prod'

    def test_nombre_fantasia_default_a_razon_social(self, cert_pfx_path):
        cfg = SifenConfig(
            ambiente='test',
            ruc='80069563-1',
            razon_social='TIPS S.A.',
            certificado_path=cert_pfx_path,
            certificado_password='pass',
            csc='00000001',
        )
        assert cfg.nombre_fantasia == 'TIPS S.A.'

    def test_nombre_fantasia_personalizado(self, cert_pfx_path):
        cfg = SifenConfig(
            ambiente='test',
            ruc='80069563-1',
            razon_social='TIPS S.A.',
            nombre_fantasia='MiMarca',
            certificado_path=cert_pfx_path,
            certificado_password='pass',
            csc='00000001',
        )
        assert cfg.nombre_fantasia == 'MiMarca'

    def test_certificado_path_es_path_object(self, config_test):
        assert isinstance(config_test.certificado_path, Path)

    def test_timbrado_relleno_a_8_digitos(self, cert_pfx_path):
        cfg = SifenConfig(
            ambiente='test',
            ruc='80069563-1',
            razon_social='TEST',
            certificado_path=cert_pfx_path,
            certificado_password='pass',
            csc='00000001',
            timbrado_numero='123',
        )
        assert cfg.timbrado_numero == '00000123'
        assert len(cfg.timbrado_numero) == 8

    def test_establecimiento_default_001(self, config_test):
        assert config_test.establecimiento == '001'

    def test_punto_expedicion_default_001(self, config_test):
        assert config_test.punto_expedicion == '001'


# ─── Validaciones de ambiente ────────────────────────────────────────────────

class TestSifenConfigAmbiente:
    def test_ambiente_invalido_lanza_excepcion(self, cert_pfx_path):
        with pytest.raises(ConfigurationException, match='Ambiente inválido'):
            SifenConfig(
                ambiente='staging',
                ruc='80069563-1',
                razon_social='TEST',
                certificado_path=cert_pfx_path,
                certificado_password='pass',
                csc='00000001',
            )

    def test_ambiente_vacio_lanza_excepcion(self, cert_pfx_path):
        with pytest.raises(ConfigurationException):
            SifenConfig(
                ambiente='',
                ruc='80069563-1',
                razon_social='TEST',
                certificado_path=cert_pfx_path,
                certificado_password='pass',
                csc='00000001',
            )


# ─── Validaciones de RUC ─────────────────────────────────────────────────────

class TestSifenConfigRuc:
    def test_ruc_sin_guion_lanza_excepcion(self, cert_pfx_path):
        with pytest.raises(ConfigurationException, match='RUC'):
            SifenConfig(
                ambiente='test',
                ruc='800695631',
                razon_social='TEST',
                certificado_path=cert_pfx_path,
                certificado_password='pass',
                csc='00000001',
            )

    def test_ruc_con_letras_lanza_excepcion(self, cert_pfx_path):
        with pytest.raises(ConfigurationException):
            SifenConfig(
                ambiente='test',
                ruc='ABC123-1',
                razon_social='TEST',
                certificado_path=cert_pfx_path,
                certificado_password='pass',
                csc='00000001',
            )

    def test_ruc_dos_guiones_lanza_excepcion(self, cert_pfx_path):
        with pytest.raises(ConfigurationException):
            SifenConfig(
                ambiente='test',
                ruc='123-456-7',
                razon_social='TEST',
                certificado_path=cert_pfx_path,
                certificado_password='pass',
                csc='00000001',
            )


# ─── Validación de certificado ───────────────────────────────────────────────

class TestSifenConfigCertificado:
    def test_certificado_inexistente_lanza_excepcion(self):
        with pytest.raises(ConfigurationException, match='Certificado no encontrado'):
            SifenConfig(
                ambiente='test',
                ruc='80069563-1',
                razon_social='TEST',
                certificado_path='/ruta/inexistente/cert.pfx',
                certificado_password='pass',
                csc='00000001',
            )


# ─── Métodos utilitarios ─────────────────────────────────────────────────────

class TestSifenConfigMetodos:
    def test_get_ruc_emisor_sin_dv(self, config_test):
        assert config_test.get_ruc_emisor() == '80069563'

    def test_get_dv_emisor(self, config_test):
        assert config_test.get_dv_emisor() == '1'

    def test_es_test_true(self, config_test):
        assert config_test.es_test() is True
        assert config_test.es_produccion() is False

    def test_es_produccion_true(self, config_prod):
        assert config_prod.es_produccion() is True
        assert config_prod.es_test() is False

    def test_get_url_test_recibe(self, config_test):
        url = config_test.get_url('recibe')
        assert 'sifen-test.set.gov.py' in url
        assert 'recibe.wsdl' in url

    def test_get_url_prod_recibe(self, config_prod):
        url = config_prod.get_url('recibe')
        assert 'sifen.set.gov.py' in url
        assert 'sifen-test' not in url

    def test_get_url_recibe_lote(self, config_test):
        url = config_test.get_url('recibe_lote')
        assert 'recibe-lote.wsdl' in url

    def test_get_url_consulta_ruc(self, config_test):
        url = config_test.get_url('consulta_ruc')
        assert 'consulta-ruc.wsdl' in url

    def test_repr_contiene_ambiente_y_ruc(self, config_test):
        r = repr(config_test)
        assert 'test' in r
        assert '80069563-1' in r
