"""
Tests para db/conexion.py — Conexion.
Todos los tests corren sin PostgreSQL real: se mockea psycopg2.connect.
"""
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch, call

from sifen_py.db.conexion import Conexion


# ─── Constructor ──────────────────────────────────────────────────────────────

class TestConexionConstructor:
    def test_defaults_host_localhost(self):
        c = Conexion()
        assert c.host == 'localhost'

    def test_defaults_port_5433(self):
        c = Conexion()
        assert c.port == 5433

    def test_defaults_dbname_sifen_py(self):
        c = Conexion()
        assert c.dbname == 'sifen_py'

    def test_defaults_user_postgres(self):
        c = Conexion()
        assert c.user == 'postgres'

    def test_params_sobrescriben_defaults(self):
        c = Conexion(host='dbserver', port=5432, dbname='mi_db', user='admin', password='s3cr3t')
        assert c.host == 'dbserver'
        assert c.port == 5432
        assert c.dbname == 'mi_db'
        assert c.user == 'admin'
        assert c.password == 's3cr3t'

    def test_env_vars_sobrescriben_defaults(self, monkeypatch):
        monkeypatch.setenv('SIFEN_DB_HOST',     'envhost')
        monkeypatch.setenv('SIFEN_DB_PORT',     '5432')
        monkeypatch.setenv('SIFEN_DB_NAME',     'envdb')
        monkeypatch.setenv('SIFEN_DB_USER',     'envuser')
        monkeypatch.setenv('SIFEN_DB_PASSWORD', 'envpass')
        c = Conexion()
        assert c.host == 'envhost'
        assert c.port == 5432
        assert c.dbname == 'envdb'
        assert c.user == 'envuser'
        assert c.password == 'envpass'

    def test_conn_inicial_es_none(self):
        c = Conexion()
        assert c._conn is None


# ─── conectar() ───────────────────────────────────────────────────────────────

class TestConectar:
    @pytest.fixture
    def mock_psycopg2_connect(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_conn.closed = False
            mock_connect.return_value = mock_conn
            yield mock_connect, mock_conn

    def test_llama_psycopg2_connect(self, mock_psycopg2_connect):
        mock_connect, _ = mock_psycopg2_connect
        c = Conexion()
        c.conectar()
        mock_connect.assert_called_once()

    def test_retorna_conexion(self, mock_psycopg2_connect):
        _, mock_conn = mock_psycopg2_connect
        c = Conexion()
        result = c.conectar()
        assert result is mock_conn

    def test_segunda_llamada_no_reconecta(self, mock_psycopg2_connect):
        mock_connect, mock_conn = mock_psycopg2_connect
        c = Conexion()
        c.conectar()
        c.conectar()
        mock_connect.assert_called_once()

    def test_reconecta_si_conn_cerrada(self, mock_psycopg2_connect):
        mock_connect, mock_conn = mock_psycopg2_connect
        c = Conexion()
        c.conectar()
        mock_conn.closed = True
        c.conectar()
        assert mock_connect.call_count == 2


# ─── cerrar() ─────────────────────────────────────────────────────────────────

class TestCerrar:
    def test_cierra_conexion_abierta(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_conn.closed = False
            mock_connect.return_value = mock_conn
            c = Conexion()
            c.conectar()
            c.cerrar()
            mock_conn.close.assert_called_once()

    def test_cerrar_sin_conectar_no_falla(self):
        c = Conexion()
        c.cerrar()  # no debe lanzar excepción


# ─── cursor() ─────────────────────────────────────────────────────────────────

class TestCursor:
    def test_retorna_cursor(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_conn.closed = False
            mock_connect.return_value = mock_conn
            c = Conexion()
            c.cursor()
            mock_conn.cursor.assert_called_once()


# ─── ejecutar_schema() ────────────────────────────────────────────────────────

class TestEjecutarSchema:
    def test_ejecuta_sql_del_archivo(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn  = MagicMock()
            mock_conn.closed = False
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__  = MagicMock(return_value=False)
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            sql = "CREATE TABLE IF NOT EXISTS test (id serial);"
            with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
                f.write(sql)
                schema_path = f.name

            try:
                c = Conexion()
                c.ejecutar_schema(schema_path)
                mock_cursor.execute.assert_called_once_with(sql)
                mock_conn.commit.assert_called_once()
            finally:
                os.unlink(schema_path)


# ─── Gestor de contexto ───────────────────────────────────────────────────────

class TestContextManager:
    def test_enter_retorna_conexion(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_conn.closed = False
            mock_connect.return_value = mock_conn
            c = Conexion()
            result = c.__enter__()
            assert result is c

    def test_exit_sin_excepcion_hace_commit(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_conn.closed = False
            mock_connect.return_value = mock_conn
            c = Conexion()
            c.conectar()
            c.__exit__(None, None, None)
            mock_conn.commit.assert_called_once()

    def test_exit_con_excepcion_hace_rollback(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn = MagicMock()
            mock_conn.closed = False
            mock_connect.return_value = mock_conn
            c = Conexion()
            c.conectar()
            c.__exit__(ValueError, ValueError("err"), None)
            mock_conn.rollback.assert_called_once()


# ─── crear_base_si_no_existe() ────────────────────────────────────────────────

class TestCrearBaseNoExiste:
    def test_crea_db_si_no_existe(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn  = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__  = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = None  # DB no existe
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            c = Conexion(dbname='nueva_db')
            c.crear_base_si_no_existe()

            # Verifica que se hizo CREATE DATABASE
            calls = [str(ca) for ca in mock_cursor.execute.call_args_list]
            assert any('CREATE DATABASE' in s for s in calls)

    def test_no_crea_db_si_ya_existe(self):
        with patch('sifen_py.db.conexion.psycopg2.connect') as mock_connect:
            mock_conn  = MagicMock()
            mock_cursor = MagicMock()
            mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
            mock_cursor.__exit__  = MagicMock(return_value=False)
            mock_cursor.fetchone.return_value = (1,)  # DB ya existe
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            c = Conexion(dbname='sifen_py')
            c.crear_base_si_no_existe()

            calls = [str(ca) for ca in mock_cursor.execute.call_args_list]
            assert not any('CREATE DATABASE' in s for s in calls)

    def test_no_lanza_excepcion_si_falla_conexion(self):
        with patch('sifen_py.db.conexion.psycopg2.connect', side_effect=Exception("timeout")):
            c = Conexion()
            c.crear_base_si_no_existe()  # debe manejar el error silenciosamente
