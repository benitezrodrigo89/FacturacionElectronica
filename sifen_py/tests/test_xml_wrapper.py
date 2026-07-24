"""
Tests para services/xml_wrapper.py — XMLGeneratorWrapper.
Todos los tests mockean subprocess.run para no requerir Node.js
(aunque sí está disponible en el entorno).
"""
import json
import pytest
from unittest.mock import MagicMock, patch

from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.core.exceptions import XMLGenerationException


# ─── Helpers ──────────────────────────────────────────────────────────────────

XML_VALIDO = '<?xml version="1.0" encoding="UTF-8"?><rDE><DE></DE></rDE>'
XML_INVALIDO = 'no es xml'


def _build_wrapper(config_test):
    """Construye XMLGeneratorWrapper saltando la verificación de Node.js y ruta."""
    with patch.object(XMLGeneratorWrapper, '_find_node_project', return_value=MagicMock()), \
         patch.object(XMLGeneratorWrapper, '_verify_node_installation', return_value=None):
        return XMLGeneratorWrapper(config_test)


def _run_ok(stdout=XML_VALIDO):
    """Mock de subprocess.run con returncode=0 y stdout válido."""
    result = MagicMock()
    result.returncode = 0
    result.stdout = stdout
    result.stderr = ''
    return result


def _run_error(stderr='Error en generación'):
    """Mock de subprocess.run con returncode=1."""
    result = MagicMock()
    result.returncode = 1
    result.stdout = ''
    result.stderr = stderr
    return result


# ─── Inicialización ───────────────────────────────────────────────────────────

class TestXMLGeneratorWrapperInit:
    def test_node_no_instalado_lanza_excepcion(self, config_test):
        import subprocess
        with patch.object(XMLGeneratorWrapper, '_find_node_project', return_value=MagicMock()):
            with patch('subprocess.run', side_effect=FileNotFoundError):
                with pytest.raises(XMLGenerationException, match='Node.js'):
                    XMLGeneratorWrapper(config_test)

    def test_node_falla_lanza_excepcion(self, config_test):
        import subprocess
        with patch.object(XMLGeneratorWrapper, '_find_node_project', return_value=MagicMock()):
            with patch('subprocess.run',
                       side_effect=subprocess.CalledProcessError(1, 'node')):
                with pytest.raises(XMLGenerationException, match='Node.js'):
                    XMLGeneratorWrapper(config_test)


# ─── _prepare_params ─────────────────────────────────────────────────────────

class TestPrepareParams:
    def test_contiene_ruc(self, config_test):
        wrapper = _build_wrapper(config_test)
        params = wrapper._prepare_params()
        assert params['ruc'] == config_test.ruc

    def test_contiene_razon_social(self, config_test):
        wrapper = _build_wrapper(config_test)
        params = wrapper._prepare_params()
        assert params['razonSocial'] == config_test.razon_social

    def test_version_150(self, config_test):
        wrapper = _build_wrapper(config_test)
        params = wrapper._prepare_params()
        assert params['version'] == 150

    def test_timbrado_numero(self, config_test):
        wrapper = _build_wrapper(config_test)
        params = wrapper._prepare_params()
        assert params['timbradoNumero'] == config_test.timbrado_numero

    def test_establecimientos_no_vacio(self, config_test):
        wrapper = _build_wrapper(config_test)
        params = wrapper._prepare_params()
        assert len(params['establecimientos']) == 1
        assert params['establecimientos'][0]['codigo'] == config_test.establecimiento


# ─── generar_xml_de ───────────────────────────────────────────────────────────

class TestGenerarXmlDe:
    @pytest.fixture
    def wrapper(self, config_test):
        return _build_wrapper(config_test)

    @pytest.fixture
    def factura_data(self):
        return {
            "tipoDocumento": 1,
            "establecimiento": "001",
            "punto": "001",
            "numero": "0000001",
            "fecha": "2026-01-15T10:30:00",
        }

    def test_retorna_string_xml(self, wrapper, factura_data):
        with patch('subprocess.run', return_value=_run_ok()):
            result = wrapper.generar_xml_de(factura_data)
        assert isinstance(result, str)
        assert result.startswith('<?xml')

    def test_tipo_documento_1_inyecta_factura(self, wrapper, factura_data):
        with patch('subprocess.run', return_value=_run_ok()) as mock_run:
            wrapper.generar_xml_de(factura_data)
            script = mock_run.call_args[1]['input']
            data_json = json.loads(script.split('const data = ')[1].split(';')[0].strip())
            assert 'factura' in data_json

    def test_tipo_documento_en_data_si_se_pasa(self, wrapper):
        data = {"establecimiento": "001", "punto": "001"}
        with patch('subprocess.run', return_value=_run_ok()):
            wrapper.generar_xml_de(data, tipo_documento=5)
        assert data.get('tipoDocumento') == 5

    def test_error_en_node_lanza_excepcion(self, wrapper, factura_data):
        with patch('subprocess.run', return_value=_run_error('Fallo en Node')):
            with pytest.raises(XMLGenerationException, match='Error al generar XML'):
                wrapper.generar_xml_de(factura_data)

    def test_output_no_xml_lanza_excepcion(self, wrapper, factura_data):
        with patch('subprocess.run', return_value=_run_ok(stdout='no es xml')):
            with pytest.raises(XMLGenerationException, match='XML válido'):
                wrapper.generar_xml_de(factura_data)

    def test_output_vacio_lanza_excepcion(self, wrapper, factura_data):
        with patch('subprocess.run', return_value=_run_ok(stdout='')):
            with pytest.raises(XMLGenerationException):
                wrapper.generar_xml_de(factura_data)

    def test_timeout_lanza_excepcion(self, wrapper, factura_data):
        import subprocess
        with patch('subprocess.run', side_effect=subprocess.TimeoutExpired('node', 30)):
            with pytest.raises(XMLGenerationException, match='Timeout'):
                wrapper.generar_xml_de(factura_data)

    def test_csc_inyectado_si_no_viene_en_data(self, wrapper):
        data = {"tipoDocumento": 1, "establecimiento": "001", "punto": "001"}
        with patch('subprocess.run', return_value=_run_ok()):
            wrapper.generar_xml_de(data)
        assert data.get('codigoSeguridadAleatorio') == wrapper.config.csc

    def test_timbrado_en_data_sobreescribe_params(self, wrapper):
        data = {
            "tipoDocumento": 1,
            "timbradoNumero": "99999999",
            "establecimiento": "001",
            "punto": "001",
        }
        with patch('subprocess.run', return_value=_run_ok()) as mock_run:
            wrapper.generar_xml_de(data)
            script = mock_run.call_args[1]['input']
            params_json = json.loads(script.split('const params = ')[1].split(';')[0].strip())
            assert params_json['timbradoNumero'] == '99999999'


# ─── generar_xml_evento_cancelacion ──────────────────────────────────────────

class TestGenerarXmlEventoCancelacion:
    def test_retorna_xml(self, config_test, cdc_valido):
        wrapper = _build_wrapper(config_test)
        with patch('subprocess.run', return_value=_run_ok()):
            result = wrapper.generar_xml_evento_cancelacion(cdc_valido, 'Error en emisión')
        assert result.startswith('<?xml')

    def test_metodo_llamado_es_cancelacion(self, config_test, cdc_valido):
        wrapper = _build_wrapper(config_test)
        with patch('subprocess.run', return_value=_run_ok()) as mock_run:
            wrapper.generar_xml_evento_cancelacion(cdc_valido, 'Motivo')
            script = mock_run.call_args[1]['input']
            assert 'generateXMLEventoCancelacion' in script

    def test_error_lanza_excepcion(self, config_test, cdc_valido):
        wrapper = _build_wrapper(config_test)
        with patch('subprocess.run', return_value=_run_error()):
            with pytest.raises(XMLGenerationException):
                wrapper.generar_xml_evento_cancelacion(cdc_valido, 'motivo')


# ─── generar_xml_evento_inutilizacion ────────────────────────────────────────

class TestGenerarXmlEventoInutilizacion:
    def test_retorna_xml(self, config_test):
        wrapper = _build_wrapper(config_test)
        with patch('subprocess.run', return_value=_run_ok()):
            result = wrapper.generar_xml_evento_inutilizacion(1, '001', '001', 1, 5, 'Motivo')
        assert result.startswith('<?xml')

    def test_metodo_llamado_es_inutilizacion(self, config_test):
        wrapper = _build_wrapper(config_test)
        with patch('subprocess.run', return_value=_run_ok()) as mock_run:
            wrapper.generar_xml_evento_inutilizacion(1, '001', '001', 1, 5, 'Motivo')
            script = mock_run.call_args[1]['input']
            assert 'generateXMLEventoInutilizacion' in script


# ─── generar_xml_evento_conformidad ──────────────────────────────────────────

class TestGenerarXmlEventoConformidad:
    def test_retorna_xml(self, config_test, cdc_valido):
        wrapper = _build_wrapper(config_test)
        with patch('subprocess.run', return_value=_run_ok()):
            result = wrapper.generar_xml_evento_conformidad(cdc_valido, 1, '2026-01-15')
        assert result.startswith('<?xml')

    def test_metodo_llamado_es_conformidad(self, config_test, cdc_valido):
        wrapper = _build_wrapper(config_test)
        with patch('subprocess.run', return_value=_run_ok()) as mock_run:
            wrapper.generar_xml_evento_conformidad(cdc_valido, 1, '2026-01-15')
            script = mock_run.call_args[1]['input']
            assert 'generateXMLEventoConformidad' in script


# ─── _create_event_script — evento no soportado ──────────────────────────────

class TestCreateEventScript:
    def test_evento_no_soportado_lanza_excepcion(self, config_test):
        wrapper = _build_wrapper(config_test)
        with pytest.raises(XMLGenerationException, match='no soportado'):
            wrapper._create_event_script('evento_inexistente', {}, {})

    def test_script_contiene_require_dist(self, config_test):
        wrapper = _build_wrapper(config_test)
        script = wrapper._create_event_script('cancelacion', {'ruc': '80069563-1'}, {'cdc': '1' * 44})
        assert "require('./dist/index.js')" in script

    def test_script_contiene_datos(self, config_test):
        wrapper = _build_wrapper(config_test)
        data = {'cdc': '1' * 44, 'motivo': 'Error'}
        script = wrapper._create_event_script('cancelacion', {}, data)
        assert 'Error' in script
