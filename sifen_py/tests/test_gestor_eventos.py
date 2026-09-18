"""
Tests para events/gestor_eventos.py — GestorEventos.
Mockea los tres servicios (wrapper, signer, client) para no requerir
Node.js, certificado real ni conectividad SIFEN.
"""
import pytest
from unittest.mock import MagicMock

from sifen_py.events.gestor_eventos import GestorEventos
from sifen_py.services.soap_client import RespuestaSIFEN


# ─── Fixture: GestorEventos con servicios mockeados ──────────────────────────

@pytest.fixture
def gestor(config_test):
    mock_wrapper = MagicMock()
    mock_signer  = MagicMock()
    mock_client  = MagicMock()

    mock_wrapper.generar_xml_evento_cancelacion.return_value  = '<evento_cancelacion/>'
    mock_wrapper.generar_xml_evento_inutilizacion.return_value = '<evento_inutilizacion/>'
    mock_wrapper.generar_xml_evento_conformidad.return_value  = '<evento_conformidad/>'
    mock_signer.firmar_xml.return_value = '<evento_firmado/>'

    g = GestorEventos(
        config=config_test,
        wrapper=mock_wrapper,
        signer=mock_signer,
        client=mock_client,
    )
    return g, mock_wrapper, mock_signer, mock_client


# ─── cancelar ─────────────────────────────────────────────────────────────────

class TestCancelar:
    def test_llama_generar_xml_cancelacion(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.cancelar(cdc='A' * 44, motivo='Error de emisión')
        wrapper.generar_xml_evento_cancelacion.assert_called_once_with('A' * 44, 'Error de emisión')

    def test_firma_el_xml_generado(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.cancelar(cdc='A' * 44, motivo='Motivo')
        signer.firmar_xml.assert_called_once_with('<evento_cancelacion/>')

    def test_envia_el_xml_firmado(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.cancelar(cdc='A' * 44, motivo='Motivo')
        client.enviar_evento_directo.assert_called_once_with('<evento_firmado/>')

    def test_retorna_respuesta_sifen(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'Evento recibido')
        resp = g.cancelar(cdc='A' * 44, motivo='Motivo')
        assert isinstance(resp, RespuestaSIFEN)
        assert resp.codigo == '0300'

    def test_propaga_excepcion_del_signer(self, gestor):
        g, wrapper, signer, client = gestor
        signer.firmar_xml.side_effect = Exception('certificado inválido')
        with pytest.raises(Exception, match='certificado inválido'):
            g.cancelar(cdc='A' * 44, motivo='Motivo')


# ─── inutilizar ───────────────────────────────────────────────────────────────

class TestInutilizar:
    def test_llama_generar_xml_inutilizacion(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.inutilizar(
            tipo_documento=1,
            establecimiento='001',
            punto='001',
            numero_desde=10,
            numero_hasta=15,
            motivo='Documentos generados por error',
        )
        wrapper.generar_xml_evento_inutilizacion.assert_called_once_with(
            tipo_documento=1,
            establecimiento='001',
            punto='001',
            numero_desde=10,
            numero_hasta=15,
            motivo='Documentos generados por error',
        )

    def test_firma_y_envia(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.inutilizar(1, '001', '001', 1, 3, 'Error')
        signer.firmar_xml.assert_called_once()
        client.enviar_evento_directo.assert_called_once()

    def test_retorna_respuesta_sifen(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'Recibido')
        resp = g.inutilizar(1, '001', '001', 1, 1, 'Error')
        assert resp.codigo == '0300'


# ─── conformidad ──────────────────────────────────────────────────────────────

class TestConformidad:
    def test_llama_generar_xml_conformidad(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.conformidad(
            cdc='A' * 44,
            tipo_conformidad=1,
            fecha_recepcion='2026-09-18T10:00:00',
        )
        wrapper.generar_xml_evento_conformidad.assert_called_once_with(
            cdc='A' * 44,
            tipo_conformidad=1,
            fecha_recepcion='2026-09-18T10:00:00',
        )

    def test_firma_y_envia(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.conformidad('A' * 44, 1, '2026-09-18T10:00:00')
        signer.firmar_xml.assert_called_once()
        client.enviar_evento_directo.assert_called_once_with('<evento_firmado/>')

    def test_retorna_respuesta_sifen(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'Conformidad recibida')
        resp = g.conformidad('A' * 44, 2, '2026-09-18T10:00:00')
        assert isinstance(resp, RespuestaSIFEN)
        assert resp.codigo == '0300'

    def test_conformidad_parcial(self, gestor):
        g, wrapper, signer, client = gestor
        client.enviar_evento_directo.return_value = RespuestaSIFEN('0300', 'OK')
        g.conformidad('B' * 44, tipo_conformidad=2, fecha_recepcion='2026-09-18T08:00:00')
        wrapper.generar_xml_evento_conformidad.assert_called_once_with(
            cdc='B' * 44,
            tipo_conformidad=2,
            fecha_recepcion='2026-09-18T08:00:00',
        )


# ─── Inyección de dependencias ────────────────────────────────────────────────

class TestInyeccionDependencias:
    def test_acepta_servicios_externos(self, config_test):
        mock_wrapper = MagicMock()
        mock_signer  = MagicMock()
        mock_client  = MagicMock()
        g = GestorEventos(config_test, wrapper=mock_wrapper, signer=mock_signer, client=mock_client)
        assert g.wrapper is mock_wrapper
        assert g.signer  is mock_signer
        assert g.client  is mock_client
