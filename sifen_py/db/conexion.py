"""
Gestión de conexión a PostgreSQL para sifen_py.
Parámetros leídos de variables de entorno o valores por defecto.

Variables de entorno soportadas:
    SIFEN_DB_HOST     (default: localhost)
    SIFEN_DB_PORT     (default: 5433)
    SIFEN_DB_NAME     (default: sifen_py)
    SIFEN_DB_USER     (default: postgres)
    SIFEN_DB_PASSWORD (default: '')
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor
from loguru import logger


class Conexion:
    """Maneja la conexión y el pool simple a PostgreSQL."""

    def __init__(
        self,
        host:     str = None,
        port:     int = None,
        dbname:   str = None,
        user:     str = None,
        password: str = None,
    ):
        self.host     = host     or os.getenv('SIFEN_DB_HOST',     'localhost')
        self.port     = port     or int(os.getenv('SIFEN_DB_PORT', '5433'))
        self.dbname   = dbname   or os.getenv('SIFEN_DB_NAME',     'sifen_py')
        self.user     = user     or os.getenv('SIFEN_DB_USER',     'postgres')
        self.password = password or os.getenv('SIFEN_DB_PASSWORD', '')
        self._conn    = None

    def conectar(self):
        """Abre la conexión si no está abierta."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                dbname=self.dbname,
                user=self.user,
                password=self.password,
                cursor_factory=RealDictCursor,
            )
            logger.debug(f"Conectado a PostgreSQL: {self.dbname}@{self.host}:{self.port}")
        return self._conn

    def cerrar(self):
        if self._conn and not self._conn.closed:
            self._conn.close()
            logger.debug("Conexión PostgreSQL cerrada")

    def cursor(self, dict_cursor: bool = True):
        """Devuelve un cursor. Si dict_cursor=True, las filas son dicts."""
        conn = self.conectar()
        factory = RealDictCursor if dict_cursor else None
        return conn.cursor(cursor_factory=factory)

    def ejecutar_schema(self, schema_path: str = None):
        """Crea/migra tablas ejecutando schema.sql sentencia por sentencia."""
        if schema_path is None:
            schema_path = os.path.join(os.path.dirname(__file__), 'schema.sql')
        with open(schema_path, 'r', encoding='utf-8') as f:
            sql = f.read()

        # Dividir en sentencias individuales respetando bloques DO $$...$$
        import re
        # Extraer bloques DO $$ ... $$ como una sola sentencia
        bloques = re.split(r'(DO\s+\$\$.*?\$\$\s*;)', sql, flags=re.DOTALL | re.IGNORECASE)
        sentencias = []
        for bloque in bloques:
            if re.match(r'DO\s+\$\$', bloque, re.IGNORECASE):
                sentencias.append(bloque.strip())
            else:
                for s in bloque.split(';'):
                    s = s.strip()
                    if s:
                        sentencias.append(s + ';')

        conn = self.conectar()
        with conn.cursor() as cur:
            for sentencia in sentencias:
                if sentencia.strip(';').strip():
                    cur.execute(sentencia)
        conn.commit()
        logger.info("Schema aplicado correctamente")

    def crear_base_si_no_existe(self):
        """Crea la base de datos sifen_py si no existe (conecta a 'postgres' primero)."""
        try:
            conn = psycopg2.connect(
                host=self.host, port=self.port,
                dbname='postgres', user=self.user, password=self.password,
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s", (self.dbname,)
                )
                if not cur.fetchone():
                    cur.execute(f'CREATE DATABASE {self.dbname}')
                    logger.info(f"Base de datos '{self.dbname}' creada")
                else:
                    logger.debug(f"Base de datos '{self.dbname}' ya existe")
            conn.close()
        except Exception as e:
            logger.warning(f"No se pudo verificar/crear la base de datos: {e}")

    def __enter__(self):
        self.conectar()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self.cerrar()
