"""
Tests para db/repositorio.py — RepositorioDE.
Todos los tests corren sin PostgreSQL real: se mockea la conexión.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

from sifen_py.db.repositorio import RepositorioDE, _codigo_a_estado, _codigo_consulta_a_estado
from sifen_py.db.conexion import Conexion


# ─── Fixture: mock de conexión ────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """
    Devuelve (db, conn, cur) donde db es un mock de Conexion.
    - db.conectar() → conn
    - conn.cursor() es context manager que retorna cur
    """
    db   = MagicMock(spec=Conexion)
    conn = MagicMock()
    cur  = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__  = MagicMock(return_value=False)
    conn.cursor.return_value = cur
    db.conectar.return_value = conn
    return db, conn, cur


# ─── Helpers: _codigo_a_estado / _codigo_consulta_a_estado ───────────────────

class TestCodigoAEstado:
    def test_0260_es_aprobado(self):
        assert _codigo_a_estado('0260') == 'aprobado'

    def test_1001_es_aprobado(self):
        assert _codigo_a_estado('1001') == 'aprobado'

    def test_0160_es_rechazado(self):
        assert _codigo_a_estado('0160') == 'rechazado'

    def test_codigo_desconocido_es_rechazado(self):
        assert _codigo_a_estado('9999') == 'rechazado'

    def test_err_es_rechazado(self):
        assert _codigo_a_estado('ERR') == 'rechazado'


class TestCodigoConsultaAEstado:
    def test_0422_es_aprobado(self):
        assert _codigo_consulta_a_estado('0422') == 'aprobado'

    def test_0420_es_rechazado(self):
        assert _codigo_consulta_a_estado('0420') == 'rechazado'

    def test_otro_codigo_es_rechazado(self):
        assert _codigo_consulta_a_estado('0160') == 'rechazado'


# ─── guardar_pendiente ────────────────────────────────────────────────────────

class TestGuardarPendiente:
    def test_ejecuta_insert(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = (1,)
        repo = RepositorioDE(db)
        repo.guardar_pendiente(
            cdc='A' * 44,
            numero_doc=1,
            xml_firmado='<xml/>',
        )
        cur.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_retorna_id_generado(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = (42,)
        repo = RepositorioDE(db)
        id_ = repo.guardar_pendiente(cdc='B' * 44, numero_doc=2, xml_firmado='<x/>')
        assert id_ == 42

    def test_retorna_id_de_dict(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = {'id': 7}
        repo = RepositorioDE(db)
        id_ = repo.guardar_pendiente(cdc='C' * 44, numero_doc=3, xml_firmado='<x/>')
        assert id_ == 7

    def test_data_documento_se_serializa_a_json(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = (1,)
        repo = RepositorioDE(db)
        repo.guardar_pendiente(
            cdc='D' * 44,
            numero_doc=4,
            xml_firmado='<x/>',
            data_documento={'tipoDocumento': 1, 'items': []},
        )
        # El execute debe haberse llamado con algún argumento que incluye JSON
        args = cur.execute.call_args[0]
        params = args[1]
        assert params['data_json'] is not None
        assert 'tipoDocumento' in params['data_json']


# ─── actualizar_respuesta ─────────────────────────────────────────────────────

class TestActualizarRespuesta:
    def test_ejecuta_update(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.actualizar_respuesta(cdc='A' * 44, codigo='0260', descripcion='Aprobado')
        cur.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_pasa_estado_aprobado_para_0260(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.actualizar_respuesta(cdc='A' * 44, codigo='0260', descripcion='OK')
        params = cur.execute.call_args[0][1]
        assert params['estado'] == 'aprobado'

    def test_pasa_estado_rechazado_para_0160(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.actualizar_respuesta(cdc='A' * 44, codigo='0160', descripcion='Rechazado')
        params = cur.execute.call_args[0][1]
        assert params['estado'] == 'rechazado'

    def test_pasa_protocolo(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.actualizar_respuesta(cdc='A' * 44, codigo='0260', descripcion='OK', protocolo='50017901')
        params = cur.execute.call_args[0][1]
        assert params['protocolo'] == '50017901'


# ─── actualizar_estado_consulta ───────────────────────────────────────────────

class TestActualizarEstadoConsulta:
    def test_0422_asigna_aprobado(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.actualizar_estado_consulta(cdc='A' * 44, codigo='0422', descripcion='Aprobado')
        params = cur.execute.call_args[0][1]
        assert params['estado'] == 'aprobado'

    def test_0420_asigna_rechazado(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.actualizar_estado_consulta(cdc='A' * 44, codigo='0420', descripcion='No existe')
        params = cur.execute.call_args[0][1]
        assert params['estado'] == 'rechazado'

    def test_ejecuta_commit(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.actualizar_estado_consulta(cdc='A' * 44, codigo='0422', descripcion='OK')
        conn.commit.assert_called_once()


# ─── marcar_inutilizados ──────────────────────────────────────────────────────

class TestMarcarInutilizados:
    def test_retorna_rowcount(self, mock_db):
        db, conn, cur = mock_db
        cur.rowcount = 3
        repo = RepositorioDE(db)
        n = repo.marcar_inutilizados(tipo_documento=1, numero_desde=10, numero_hasta=12)
        assert n == 3

    def test_ejecuta_update(self, mock_db):
        db, conn, cur = mock_db
        cur.rowcount = 0
        repo = RepositorioDE(db)
        repo.marcar_inutilizados(tipo_documento=1, numero_desde=1, numero_hasta=5)
        cur.execute.assert_called_once()
        conn.commit.assert_called_once()


# ─── marcar_cancelado ─────────────────────────────────────────────────────────

class TestMarcarCancelado:
    def test_ejecuta_update(self, mock_db):
        db, conn, cur = mock_db
        repo = RepositorioDE(db)
        repo.marcar_cancelado(cdc='A' * 44, codigo='0422', descripcion='Cancelado')
        cur.execute.assert_called_once()
        conn.commit.assert_called_once()

    def test_pasa_cdc_al_update(self, mock_db):
        db, conn, cur = mock_db
        cdc = 'E' * 44
        repo = RepositorioDE(db)
        repo.marcar_cancelado(cdc=cdc, codigo='0422', descripcion='OK')
        params = cur.execute.call_args[0][1]
        assert params['cdc'] == cdc


# ─── obtener_por_cdc ──────────────────────────────────────────────────────────

class TestObtenerPorCdc:
    def test_retorna_fetchone(self, mock_db):
        db, conn, cur = mock_db
        fila = {'id': 1, 'cdc': 'A' * 44, 'estado': 'aprobado'}
        cur.fetchone.return_value = fila
        repo = RepositorioDE(db)
        result = repo.obtener_por_cdc('A' * 44)
        assert result == fila

    def test_retorna_none_si_no_existe(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = None
        repo = RepositorioDE(db)
        result = repo.obtener_por_cdc('Z' * 44)
        assert result is None


# ─── listar_por_estado ────────────────────────────────────────────────────────

class TestListarPorEstado:
    def test_retorna_lista(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchall.return_value = [
            {'id': 1, 'estado': 'aprobado'},
            {'id': 2, 'estado': 'aprobado'},
        ]
        repo = RepositorioDE(db)
        result = repo.listar_por_estado('aprobado')
        assert len(result) == 2

    def test_lista_vacia_si_no_hay(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchall.return_value = []
        repo = RepositorioDE(db)
        result = repo.listar_por_estado('pendiente')
        assert result == []


# ─── listar_recientes ─────────────────────────────────────────────────────────

class TestListarRecientes:
    def test_retorna_lista_de_docs(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchall.return_value = [{'id': 5}]
        repo = RepositorioDE(db)
        result = repo.listar_recientes()
        assert len(result) == 1
        cur.execute.assert_called_once()


# ─── proximo_numero_doc ───────────────────────────────────────────────────────

class TestProximoNumeroDoc:
    def test_retorna_siguiente_numero_desde_tupla(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = (6,)
        repo = RepositorioDE(db)
        n = repo.proximo_numero_doc()
        assert n == 6

    def test_retorna_siguiente_numero_desde_dict(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = {'coalesce': 10}
        repo = RepositorioDE(db)
        n = repo.proximo_numero_doc()
        assert n == 10


# ─── ultimo_enviado ───────────────────────────────────────────────────────────

class TestUltimoEnviado:
    def test_retorna_fetchone(self, mock_db):
        db, conn, cur = mock_db
        doc = {'id': 99, 'cdc': 'X' * 44}
        cur.fetchone.return_value = doc
        repo = RepositorioDE(db)
        result = repo.ultimo_enviado()
        assert result == doc

    def test_retorna_none_si_sin_registros(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchone.return_value = None
        repo = RepositorioDE(db)
        result = repo.ultimo_enviado()
        assert result is None


# ─── resumen_estados ──────────────────────────────────────────────────────────

class TestResumenEstados:
    def test_retorna_dict_por_estado(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchall.return_value = [
            {'estado': 'aprobado',  'total': 5},
            {'estado': 'pendiente', 'total': 2},
            {'estado': 'rechazado', 'total': 1},
        ]
        repo = RepositorioDE(db)
        resumen = repo.resumen_estados()
        assert resumen['aprobado']  == 5
        assert resumen['pendiente'] == 2
        assert resumen['rechazado'] == 1

    def test_retorna_dict_vacio_si_no_hay(self, mock_db):
        db, conn, cur = mock_db
        cur.fetchall.return_value = []
        repo = RepositorioDE(db)
        resumen = repo.resumen_estados()
        assert resumen == {}
