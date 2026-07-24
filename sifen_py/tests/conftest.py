"""
Fixtures compartidos para todos los tests de sifen_py.
"""
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ─── Fixture de configuración mínima ─────────────────────────────────────────

@pytest.fixture
def cert_pfx_path(tmp_path):
    """Crea un archivo .pfx falso para que SifenConfig no falle por FileNotFoundError."""
    cert = tmp_path / "test_cert.pfx"
    cert.write_bytes(b"fake_pfx_data")
    return str(cert)


@pytest.fixture
def config_test(cert_pfx_path):
    """SifenConfig de ambiente test con datos de prueba."""
    from sifen_py.core.config import SifenConfig
    return SifenConfig(
        ambiente='test',
        ruc='80069563-1',
        razon_social='TIPS S.A.',
        certificado_path=cert_pfx_path,
        certificado_password='test1234',
        csc='00000001',
        establecimiento='001',
        punto_expedicion='001',
        timbrado_numero='12345678',
    )


@pytest.fixture
def config_prod(cert_pfx_path):
    """SifenConfig de ambiente producción."""
    from sifen_py.core.config import SifenConfig
    return SifenConfig(
        ambiente='prod',
        ruc='12345678-9',
        razon_social='EMPRESA PROD S.A.',
        certificado_path=cert_pfx_path,
        certificado_password='prod_pass',
        csc='99999999',
    )


# ─── CDC de ejemplo válido ────────────────────────────────────────────────────

@pytest.fixture
def cdc_valido():
    """CDC de 44 dígitos construido con la función generar_cdc para garantizar DV correcto."""
    from sifen_py.utils.cdc import generar_cdc
    return generar_cdc(
        tipo_documento=1,
        ruc_emisor='80069563',
        dv_emisor='1',
        establecimiento='001',
        punto_expedicion='001',
        numero='0000001',
        tipo_contribuyente=2,
        fecha_emision=datetime(2026, 1, 15, 10, 30, 0),
        tipo_emision=1,
        codigo_seguridad='00000001',
    )


# ─── Mock del cliente SOAP ───────────────────────────────────────────────────

@pytest.fixture
def mock_soap_client():
    """Cliente SOAP mockeado para pruebas del BatchManager."""
    client = MagicMock()
    return client


# ─── XML mínimo firmable ──────────────────────────────────────────────────────

@pytest.fixture
def xml_de_simple():
    """XML mínimo con estructura válida para pruebas de firma."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<rDE xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
    <DE>
        <gOpeDE>
            <iTipEmi>1</iTipEmi>
        </gOpeDE>
        <gTimb>
            <iTiDE>1</iTiDE>
            <dNumTim>12345678</dNumTim>
        </gTimb>
        <gDatGralOpe>
            <dFeEmiDE>2026-01-15T10:30:00</dFeEmiDE>
        </gDatGralOpe>
    </DE>
</rDE>"""
