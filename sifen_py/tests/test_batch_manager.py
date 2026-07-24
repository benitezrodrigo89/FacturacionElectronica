"""
Tests para services/batch_manager.py — BatchManager, EstadoDE, EstadoLote.
"""
import pytest
from unittest.mock import MagicMock, patch

from sifen_py.services.batch_manager import (
    BatchManager,
    DocumentoEnLote,
    Lote,
    EstadoDE,
    EstadoLote,
)
from sifen_py.services.soap_client import RespuestaSIFEN
from sifen_py.core.exceptions import BatchException


# ─── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def soap_mock():
    return MagicMock()


@pytest.fixture
def bm(soap_mock):
    return BatchManager(soap_mock, max_reintentos=3)


def _fake_cdc(n: int) -> str:
    """CDC ficticio único por número (no válido criptográficamente)."""
    return str(n).zfill(44)


# ─── EstadoDE y EstadoLote ────────────────────────────────────────────────────

class TestEnums:
    def test_estado_de_valores(self):
        assert EstadoDE.PENDIENTE == 'pendiente'
        assert EstadoDE.APROBADO  == 'aprobado'
        assert EstadoDE.RECHAZADO == 'rechazado'
        assert EstadoDE.ERROR     == 'error'

    def test_estado_lote_valores(self):
        assert EstadoLote.ARMADO    == 'armado'
        assert EstadoLote.ENVIADO   == 'enviado'
        assert EstadoLote.PROCESADO == 'procesado'
        assert EstadoLote.ERROR     == 'error'


# ─── Lote (dataclass) ────────────────────────────────────────────────────────

class TestLote:
    def test_cantidad_inicial_cero(self):
        lote = Lote(numero='001')
        assert lote.cantidad == 0

    def test_no_esta_lleno_con_49(self):
        lote = Lote(numero='001')
        lote.documentos = [MagicMock()] * 49
        assert lote.esta_lleno is False

    def test_esta_lleno_con_50(self):
        lote = Lote(numero='001')
        lote.documentos = [MagicMock()] * 50
        assert lote.esta_lleno is True

    def test_estado_inicial_armado(self):
        lote = Lote(numero='001')
        assert lote.estado == EstadoLote.ARMADO


# ─── BatchManager.agregar_de ─────────────────────────────────────────────────

class TestAgregarDe:
    def test_agrega_documento(self, bm):
        doc = bm.agregar_de(_fake_cdc(1), '<xml/>')
        assert isinstance(doc, DocumentoEnLote)
        assert doc.cdc == _fake_cdc(1)

    def test_estado_inicial_en_lote(self, bm):
        doc = bm.agregar_de(_fake_cdc(1), '<xml/>')
        assert doc.estado == EstadoDE.EN_LOTE

    def test_numero_lote_asignado(self, bm):
        doc = bm.agregar_de(_fake_cdc(1), '<xml/>')
        assert doc.numero_lote is not None

    def test_cdc_duplicado_lanza_excepcion(self, bm):
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        with pytest.raises(BatchException, match='ya fue agregado'):
            bm.agregar_de(_fake_cdc(1), '<xml/>')

    def test_mismo_lote_mientras_no_lleno(self, bm):
        doc1 = bm.agregar_de(_fake_cdc(1), '<xml/>')
        doc2 = bm.agregar_de(_fake_cdc(2), '<xml/>')
        assert doc1.numero_lote == doc2.numero_lote

    def test_nuevo_lote_al_llegar_a_50(self, bm):
        for i in range(50):
            bm.agregar_de(_fake_cdc(i), f'<xml id="{i}"/>')
        lote_primero = bm._documentos[_fake_cdc(0)].numero_lote

        bm.agregar_de(_fake_cdc(50), '<xml id="50"/>')
        lote_51 = bm._documentos[_fake_cdc(50)].numero_lote
        assert lote_primero != lote_51

    def test_agrega_multiples_documentos(self, bm):
        for i in range(10):
            bm.agregar_de(_fake_cdc(i), f'<xml id="{i}"/>')
        assert len(bm._documentos) == 10


# ─── BatchManager.enviar_lote_actual ─────────────────────────────────────────

class TestEnviarLoteActual:
    def test_retorna_none_sin_documentos(self, bm):
        resultado = bm.enviar_lote_actual()
        assert resultado is None

    def test_envia_lote_con_documentos(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        lote = bm.enviar_lote_actual()
        assert lote is not None
        assert lote.estado == EstadoLote.ENVIADO

    def test_cierra_lote_actual_despues_de_envio(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        bm.enviar_lote_actual()
        assert bm._lote_actual is None

    def test_docs_en_estado_enviado(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        bm.enviar_lote_actual()
        assert bm._documentos[_fake_cdc(1)].estado == EstadoDE.ENVIADO

    def test_respuesta_0301_no_encolado(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0301', 'No encolado')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        lote = bm.enviar_lote_actual()
        assert lote.estado == EstadoLote.NO_ENCOLADO
        assert bm._documentos[_fake_cdc(1)].estado == EstadoDE.RECHAZADO


# ─── BatchManager._enviar_lote con reintentos ────────────────────────────────

class TestReintentos:
    def test_falla_primera_reintenta(self, bm, soap_mock):
        with patch('time.sleep'):
            soap_mock.enviar_lote.side_effect = [
                Exception("timeout"),
                RespuestaSIFEN('0300', 'OK'),
            ]
            bm.agregar_de(_fake_cdc(1), '<xml/>')
            lote = bm.enviar_lote_actual()
            assert lote.estado == EstadoLote.ENVIADO
            assert soap_mock.enviar_lote.call_count == 2

    def test_agota_reintentos_estado_error(self, bm, soap_mock):
        with patch('time.sleep'):
            soap_mock.enviar_lote.side_effect = Exception("falla persistente")
            bm.agregar_de(_fake_cdc(1), '<xml/>')
            lote = bm.enviar_lote_actual()
            assert lote.estado == EstadoLote.ERROR
            assert soap_mock.enviar_lote.call_count == 3

    def test_docs_en_estado_error_tras_agotar_reintentos(self, bm, soap_mock):
        with patch('time.sleep'):
            soap_mock.enviar_lote.side_effect = Exception("falla")
            bm.agregar_de(_fake_cdc(1), '<xml/>')
            bm.enviar_lote_actual()
            assert bm._documentos[_fake_cdc(1)].estado == EstadoDE.ERROR

    def test_un_solo_reintento(self, soap_mock):
        bm_1 = BatchManager(soap_mock, max_reintentos=1)
        with patch('time.sleep'):
            soap_mock.enviar_lote.side_effect = Exception("falla")
            bm_1.agregar_de(_fake_cdc(1), '<xml/>')
            bm_1.enviar_lote_actual()
            assert soap_mock.enviar_lote.call_count == 1


# ─── BatchManager.esperar_resultado ─────────────────────────────────────────

class TestEsperarResultado:
    def test_lote_no_encontrado_lanza_excepcion(self, bm):
        with pytest.raises(BatchException, match='no encontrado'):
            bm.esperar_resultado('LOTE_INEXISTENTE')

    def test_lote_no_enviado_retorna_sin_consultar(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        lote = bm.enviar_lote_actual()
        # Forzar estado ARMADO para simular lote sin enviar
        lote.estado = EstadoLote.ARMADO
        resultado = bm.esperar_resultado(lote.numero)
        # No debe llamar a esperar_procesamiento_lote
        soap_mock.esperar_procesamiento_lote.assert_not_called()

    def test_0362_actualiza_estado_lote(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        lote = bm.enviar_lote_actual()

        soap_mock.esperar_procesamiento_lote.return_value = RespuestaSIFEN(
            '0362', 'Procesado', raw={'detalle_des': []}
        )
        resultado = bm.esperar_resultado(lote.numero)
        assert resultado.estado == EstadoLote.PROCESADO

    def test_0361_estado_procesando(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        lote = bm.enviar_lote_actual()

        soap_mock.esperar_procesamiento_lote.return_value = RespuestaSIFEN('0361', 'Procesando')
        resultado = bm.esperar_resultado(lote.numero)
        assert resultado.estado == EstadoLote.PROCESANDO


# ─── BatchManager.consultar_de ───────────────────────────────────────────────

class TestConsultarDe:
    def test_cdc_no_registrado_lanza_excepcion(self, bm):
        with pytest.raises(BatchException, match='no encontrado'):
            bm.consultar_de('9' * 44)

    def test_0422_actualiza_estado_aprobado(self, bm, soap_mock):
        soap_mock.consultar_de.return_value = RespuestaSIFEN('0422', 'Aprobado')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        doc = bm.consultar_de(_fake_cdc(1))
        assert doc.estado == EstadoDE.APROBADO

    def test_0420_actualiza_estado_rechazado(self, bm, soap_mock):
        soap_mock.consultar_de.return_value = RespuestaSIFEN('0420', 'Rechazado')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        doc = bm.consultar_de(_fake_cdc(1))
        assert doc.estado == EstadoDE.RECHAZADO


# ─── BatchManager.obtener_resultados_lote ────────────────────────────────────

class TestObtenerResultadosLote:
    def test_lote_inexistente_lanza_excepcion(self, bm):
        with pytest.raises(BatchException, match='no encontrado'):
            bm.obtener_resultados_lote('LOTE_X')

    def test_retorna_lista_de_documentos(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml1/>')
        bm.agregar_de(_fake_cdc(2), '<xml2/>')
        lote = bm.enviar_lote_actual()
        docs = bm.obtener_resultados_lote(lote.numero)
        assert len(docs) == 2


# ─── BatchManager.resumen ────────────────────────────────────────────────────

class TestResumen:
    def test_resumen_sin_documentos(self, bm):
        r = bm.resumen()
        assert r['total_documentos'] == 0
        assert r['total_lotes'] == 0

    def test_resumen_con_documentos(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        bm.agregar_de(_fake_cdc(2), '<xml/>')
        bm.enviar_lote_actual()
        r = bm.resumen()
        assert r['total_documentos'] == 2
        assert r['total_lotes'] == 1

    def test_resumen_incluye_por_estado(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        bm.enviar_lote_actual()
        r = bm.resumen()
        assert EstadoDE.ENVIADO in r['por_estado']

    def test_resumen_lotes_incluye_datos(self, bm, soap_mock):
        soap_mock.enviar_lote.return_value = RespuestaSIFEN('0300', 'OK')
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        lote = bm.enviar_lote_actual()
        r = bm.resumen()
        lote_info = r['lotes'][0]
        assert lote_info['numero'] == lote.numero
        assert lote_info['cantidad'] == 1


# ─── BatchManager._actualizar_estados_des ────────────────────────────────────

class TestActualizarEstadosDes:
    def test_actualiza_aprobado(self, bm):
        cdc = _fake_cdc(1)
        bm.agregar_de(cdc, '<xml/>')
        lote = bm._lote_actual
        detalle = [{'dCDC': cdc, 'dCodRes': '0422', 'dMsgRes': 'Aprobado'}]
        bm._actualizar_estados_des(lote, detalle)
        assert bm._documentos[cdc].estado == EstadoDE.APROBADO

    def test_actualiza_rechazado(self, bm):
        cdc = _fake_cdc(1)
        bm.agregar_de(cdc, '<xml/>')
        lote = bm._lote_actual
        detalle = [{'dCDC': cdc, 'dCodRes': '0420', 'dMsgRes': 'Rechazado'}]
        bm._actualizar_estados_des(lote, detalle)
        assert bm._documentos[cdc].estado == EstadoDE.RECHAZADO

    def test_cdc_no_registrado_se_ignora(self, bm):
        bm.agregar_de(_fake_cdc(1), '<xml/>')
        lote = bm._lote_actual
        detalle = [{'dCDC': _fake_cdc(999), 'dCodRes': '0422', 'dMsgRes': 'OK'}]
        # No debe lanzar excepción
        bm._actualizar_estados_des(lote, detalle)

    def test_detalle_vacio_no_cambia_estados(self, bm):
        cdc = _fake_cdc(1)
        bm.agregar_de(cdc, '<xml/>')
        lote = bm._lote_actual
        estado_antes = bm._documentos[cdc].estado
        bm._actualizar_estados_des(lote, [])
        assert bm._documentos[cdc].estado == estado_antes
