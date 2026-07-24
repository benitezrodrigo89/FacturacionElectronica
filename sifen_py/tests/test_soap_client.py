"""
Tests para services/soap_client.py — SifenSOAPClient y RespuestaSIFEN.
Todos los tests corren sin conexión real: se mockea zeep.Client.
"""
import io
import zipfile
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from sifen_py.services.soap_client import SifenSOAPClient, RespuestaSIFEN
from sifen_py.core.exceptions import SOAPException, BatchException


# ─── RespuestaSIFEN ───────────────────────────────────────────────────────────

class TestRespuestaSIFEN:
    def test_exitoso_con_codigo_0300(self):
        r = RespuestaSIFEN('0300', 'Lote recibido')
        assert r.exitoso is True

    def test_exitoso_con_codigo_0360(self):
        # 0360 está incluido en el set exitoso del código actual
        r = RespuestaSIFEN('0360', 'No existe lote')
        assert r.exitoso is True

    def test_exitoso_con_codigo_0362(self):
        r = RespuestaSIFEN('0362', 'Procesado')
        assert r.exitoso is True

    def test_exitoso_con_codigo_0420(self):
        # 0420 está incluido en el set exitoso del código actual
        r = RespuestaSIFEN('0420', 'DE no existe')
        assert r.exitoso is True

    def test_exitoso_con_codigo_0422(self):
        r = RespuestaSIFEN('0422', 'DE aprobado')
        assert r.exitoso is True

    def test_exitoso_con_codigo_OK(self):
        r = RespuestaSIFEN('OK', 'Ok')
        assert r.exitoso is True

    def test_exitoso_con_codigo_desconocido(self):
        r = RespuestaSIFEN('9999', 'Error desconocido')
        assert r.exitoso is False

    def test_raw_default_dict_vacio(self):
        r = RespuestaSIFEN('0300', 'OK')
        assert r.raw == {}

    def test_raw_personalizado(self):
        r = RespuestaSIFEN('0300', 'OK', raw={'key': 'val'})
        assert r.raw['key'] == 'val'

    def test_repr_contiene_codigo(self):
        r = RespuestaSIFEN('0300', 'Recibido')
        assert '0300' in repr(r)

    def test_repr_contiene_exitoso(self):
        r = RespuestaSIFEN('0300', 'Recibido')
        assert 'True' in repr(r)


# ─── SifenSOAPClient — sin zeep disponible ───────────────────────────────────

class TestSifenSOAPClientSinZeep:
    def test_lanza_excepcion_si_zeep_no_disponible(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', False):
            with pytest.raises(SOAPException, match='zeep'):
                SifenSOAPClient(config_test)


# ─── SifenSOAPClient — helper _comprimir_xmls ────────────────────────────────

class TestComprimirXmls:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_retorna_bytes(self, client):
        result = client._comprimir_xmls(['<xml/>'], '001')
        assert isinstance(result, bytes)

    def test_zip_valido(self, client):
        result = client._comprimir_xmls(['<xml1/>', '<xml2/>'], 'lote01')
        buf = io.BytesIO(result)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
        assert len(names) == 2

    def test_nombres_archivos_incluyen_numero_lote(self, client):
        result = client._comprimir_xmls(['<xml/>'], 'LOTE99')
        buf = io.BytesIO(result)
        with zipfile.ZipFile(buf) as zf:
            names = zf.namelist()
        assert all('LOTE99' in n for n in names)

    def test_contenido_xml_preservado(self, client):
        xml = '<factura><monto>100000</monto></factura>'
        result = client._comprimir_xmls([xml], '001')
        buf = io.BytesIO(result)
        with zipfile.ZipFile(buf) as zf:
            content = zf.read(zf.namelist()[0]).decode('utf-8')
        assert content == xml

    def test_numeracion_secuencial(self, client):
        xmls = ['<x1/>', '<x2/>', '<x3/>']
        result = client._comprimir_xmls(xmls, '001')
        buf = io.BytesIO(result)
        with zipfile.ZipFile(buf) as zf:
            names = sorted(zf.namelist())
        assert '001' in names[0]
        assert '002' in names[1]
        assert '003' in names[2]

    def test_un_xml_produce_un_archivo(self, client):
        result = client._comprimir_xmls(['<xml/>'], 'LOTE1')
        buf = io.BytesIO(result)
        with zipfile.ZipFile(buf) as zf:
            assert len(zf.namelist()) == 1

    def test_50_xmls_produce_50_archivos(self, client):
        xmls = [f'<doc id="{i}"/>' for i in range(50)]
        result = client._comprimir_xmls(xmls, 'LOTE50')
        buf = io.BytesIO(result)
        with zipfile.ZipFile(buf) as zf:
            assert len(zf.namelist()) == 50


# ─── SifenSOAPClient — _parsear_respuesta_de ─────────────────────────────────

class TestParsearRespuestaDE:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_parsea_codigo_dCodRes(self, client):
        mock_result = {'dCodRes': '0422', 'dMsgRes': 'DE aprobado'}
        r = client._parsear_respuesta_de(mock_result)
        assert r.codigo == '0422'
        assert r.exitoso is True

    def test_parsea_codigo_xRetCodRes(self, client):
        mock_result = {'xRetCodRes': '0420', 'xRetMsgRes': 'DE rechazado'}
        r = client._parsear_respuesta_de(mock_result)
        assert r.codigo == '0420'

    def test_result_none_devuelve_err(self, client):
        r = client._parsear_respuesta_de(None)
        assert r.codigo == 'ERR'
        assert r.exitoso is False

    def test_result_vacio_devuelve_err(self, client):
        r = client._parsear_respuesta_de({})
        assert r.codigo == 'ERR'

    def test_descripcion_desde_dMsgRes(self, client):
        mock_result = {'dCodRes': '0422', 'dMsgRes': 'Documento aprobado'}
        r = client._parsear_respuesta_de(mock_result)
        assert 'aprobado' in r.descripcion.lower()

    def test_raw_se_almacena(self, client):
        mock_result = {'dCodRes': '0422', 'dMsgRes': 'OK', 'extra': 'dato'}
        r = client._parsear_respuesta_de(mock_result)
        assert r.raw.get('extra') == 'dato'


# ─── SifenSOAPClient — _parsear_respuesta_lote ───────────────────────────────

class TestParsearRespuestaLote:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_parsea_codigo_0300(self, client):
        mock_result = {'dCodRes': '0300', 'dMsgRes': 'Lote recibido'}
        r = client._parsear_respuesta_lote(mock_result, 'LOTE001')
        assert r.codigo == '0300'
        assert r.exitoso is True

    def test_numero_lote_en_raw(self, client):
        mock_result = {'dCodRes': '0300', 'dMsgRes': 'OK'}
        r = client._parsear_respuesta_lote(mock_result, 'LOTE123')
        assert r.raw['numero_lote'] == 'LOTE123'

    def test_result_none(self, client):
        r = client._parsear_respuesta_lote(None, 'LOTE0')
        assert r.codigo == 'ERR'

    def test_descripcion_fallback_desde_constantes(self, client):
        mock_result = {'dCodRes': '0301'}
        r = client._parsear_respuesta_lote(mock_result, 'X')
        assert r.descripcion  # no vacía


# ─── SifenSOAPClient — _parsear_respuesta_consulta_lote ──────────────────────

class TestParsearRespuestaConsultaLote:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_0362_extrae_detalle_des(self, client):
        detalle = [{'dCDC': 'A' * 44, 'dCodRes': '0422', 'dMsgRes': 'Aprobado'}]
        mock_result = {'dCodRes': '0362', 'dMsgRes': 'Procesado', 'xDetalle': detalle}
        r = client._parsear_respuesta_consulta_lote(mock_result, 'L01')
        assert 'detalle_des' in r.raw
        assert len(r.raw['detalle_des']) == 1

    def test_0361_no_incluye_detalle(self, client):
        mock_result = {'dCodRes': '0361', 'dMsgRes': 'Procesando'}
        r = client._parsear_respuesta_consulta_lote(mock_result, 'L01')
        assert 'detalle_des' not in r.raw

    def test_none_devuelve_err(self, client):
        r = client._parsear_respuesta_consulta_lote(None, 'L0')
        assert r.codigo == 'ERR'


# ─── SifenSOAPClient — _parsear_respuesta_ruc ────────────────────────────────

class TestParsearRespuestaRuc:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_parsea_ruc_existente(self, client):
        mock_result = {'dCodRes': '0422', 'dMsgRes': 'RUC encontrado'}
        r = client._parsear_respuesta_ruc(mock_result)
        assert r.codigo == '0422'

    def test_none_devuelve_err(self, client):
        r = client._parsear_respuesta_ruc(None)
        assert r.codigo == 'ERR'


# ─── SifenSOAPClient — _parsear_respuesta_evento ─────────────────────────────

class TestParsearRespuestaEvento:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_parsea_evento_exitoso(self, client):
        mock_result = {'dCodRes': '0300', 'dMsgRes': 'Evento recibido'}
        r = client._parsear_respuesta_evento(mock_result)
        assert r.codigo == '0300'

    def test_none_devuelve_err(self, client):
        r = client._parsear_respuesta_evento(None)
        assert r.codigo == 'ERR'


# ─── SifenSOAPClient — validaciones de enviar_lote ───────────────────────────

class TestEnviarLoteValidaciones:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_lista_vacia_lanza_batch_exception(self, client):
        with pytest.raises(BatchException, match='vacía'):
            client.enviar_lote([])

    def test_mas_de_50_lanza_batch_exception(self, client):
        xmls = ['<xml/>'] * 51
        with pytest.raises(BatchException, match='50'):
            client.enviar_lote(xmls)

    def test_exactamente_50_no_lanza_por_cantidad(self, client):
        xmls = ['<xml/>'] * 50
        # Puede fallar por otras razones (ZIP grande, WSDL), pero no por límite de cantidad
        with patch.object(client, '_get_client') as mock_get:
            mock_service = MagicMock()
            mock_service.service.rRecepcionLote.return_value = {'dCodRes': '0300', 'dMsgRes': 'OK'}
            mock_get.return_value = mock_service
            r = client.enviar_lote(xmls, '99999')
            assert r.codigo == '0300'


# ─── SifenSOAPClient — consultar_de validación de CDC ────────────────────────

class TestConsultarDeValidacion:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_cdc_de_43_digitos_lanza_excepcion(self, client):
        with pytest.raises(SOAPException, match='CDC inválido'):
            client.consultar_de('1' * 43)

    def test_cdc_de_45_digitos_lanza_excepcion(self, client):
        with pytest.raises(SOAPException, match='CDC inválido'):
            client.consultar_de('1' * 45)

    def test_cdc_vacio_lanza_excepcion(self, client):
        with pytest.raises(SOAPException, match='CDC inválido'):
            client.consultar_de('')

    def test_cdc_valido_llama_al_servicio(self, client, cdc_valido):
        with patch.object(client, '_get_client') as mock_get:
            mock_service = MagicMock()
            mock_service.service.rConsultaDE.return_value = {'dCodRes': '0422', 'dMsgRes': 'OK'}
            mock_get.return_value = mock_service
            r = client.consultar_de(cdc_valido)
            assert r.codigo == '0422'


# ─── SifenSOAPClient — recibir_de ────────────────────────────────────────────

class TestRecibirDe:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_llama_rRecepcionar(self, client):
        with patch.object(client, '_get_client') as mock_get:
            mock_service = MagicMock()
            mock_service.service.rRecepcionar.return_value = {'dCodRes': '0422', 'dMsgRes': 'OK'}
            mock_get.return_value = mock_service
            r = client.recibir_de('<xml firmado/>')
            mock_service.service.rRecepcionar.assert_called_once()
            assert r.codigo == '0422'

    def test_soap_fault_lanza_soap_exception(self, client):
        from zeep.exceptions import Fault as ZeepFault
        with patch.object(client, '_get_client') as mock_get:
            mock_service = MagicMock()
            mock_service.service.rRecepcionar.side_effect = ZeepFault('SOAP error', 500, None, None, None)
            mock_get.return_value = mock_service
            with pytest.raises(SOAPException, match='SOAP Fault'):
                client.recibir_de('<xml/>')


# ─── SifenSOAPClient — enviar_evento ─────────────────────────────────────────

class TestEnviarEvento:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_llama_rRecepcionEvento(self, client):
        with patch.object(client, '_get_client') as mock_get:
            mock_service = MagicMock()
            mock_service.service.rRecepcionEvento.return_value = {'dCodRes': '0300', 'dMsgRes': 'OK'}
            mock_get.return_value = mock_service
            r = client.enviar_evento('<evento firmado/>')
            mock_service.service.rRecepcionEvento.assert_called_once()
            assert r.codigo == '0300'


# ─── SifenSOAPClient — esperar_procesamiento_lote ────────────────────────────

class TestEsperarProcesamientoLote:
    @pytest.fixture
    def client(self, config_test):
        with patch('sifen_py.services.soap_client.ZEEP_AVAILABLE', True):
            return SifenSOAPClient(config_test)

    def test_retorna_cuando_codigo_0362(self, client):
        with patch.object(client, 'consultar_lote') as mock_consultar:
            mock_consultar.return_value = RespuestaSIFEN('0362', 'Procesado')
            r = client.esperar_procesamiento_lote('LOTE1', intentos=3, espera_seg=0)
            assert r.codigo == '0362'
            assert mock_consultar.call_count == 1

    def test_retorna_inmediatamente_con_0360(self, client):
        with patch.object(client, 'consultar_lote') as mock_consultar:
            mock_consultar.return_value = RespuestaSIFEN('0360', 'No existe')
            r = client.esperar_procesamiento_lote('LOTE1', intentos=5, espera_seg=0)
            assert r.codigo == '0360'
            assert mock_consultar.call_count == 1

    def test_agota_intentos_lanza_excepcion(self, client):
        with patch.object(client, 'consultar_lote') as mock_consultar:
            with patch('time.sleep'):
                mock_consultar.return_value = RespuestaSIFEN('0361', 'Procesando')
                with pytest.raises(SOAPException, match='no fue procesado'):
                    client.esperar_procesamiento_lote('LOTE1', intentos=3, espera_seg=0)
                assert mock_consultar.call_count == 3

    def test_segundo_intento_devuelve_0362(self, client):
        respuestas = [
            RespuestaSIFEN('0361', 'Procesando'),
            RespuestaSIFEN('0362', 'Procesado'),
        ]
        with patch.object(client, 'consultar_lote', side_effect=respuestas):
            with patch('time.sleep'):
                r = client.esperar_procesamiento_lote('LOTE1', intentos=5, espera_seg=0)
                assert r.codigo == '0362'
