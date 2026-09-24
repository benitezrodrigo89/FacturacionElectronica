"""CRUD de clientes y productos en la BD local (uso exclusivo de la webapp)."""
from __future__ import annotations
from typing import Optional
from sifen_py.db.conexion import Conexion


class RepositorioClientes:

    def __init__(self, db: Conexion):
        self.db = db

    def listar(self, busqueda: str = '', solo_activos: bool = True) -> list:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            filtro_activo = "AND activo = TRUE" if solo_activos else ""
            if busqueda:
                cur.execute(f"""
                    SELECT id, ruc, razon_social, direccion, telefono, email, activo
                    FROM clientes_sifen
                    WHERE (razon_social ILIKE %s OR ruc ILIKE %s) {filtro_activo}
                    ORDER BY razon_social LIMIT 50
                """, (f'%{busqueda}%', f'%{busqueda}%'))
            else:
                cur.execute(f"""
                    SELECT id, ruc, razon_social, direccion, telefono, email, activo
                    FROM clientes_sifen
                    WHERE 1=1 {filtro_activo}
                    ORDER BY razon_social LIMIT 200
                """)
            return cur.fetchall()

    def obtener(self, cliente_id: int) -> Optional[dict]:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ruc, razon_social, direccion, telefono, email, activo "
                "FROM clientes_sifen WHERE id = %s", (cliente_id,)
            )
            return cur.fetchone()

    def obtener_por_ruc(self, ruc: str) -> Optional[dict]:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, ruc, razon_social, direccion, telefono, email, activo "
                "FROM clientes_sifen WHERE ruc = %s AND activo = TRUE LIMIT 1", (ruc,)
            )
            return cur.fetchone()

    def crear(self, ruc: str, razon_social: str, direccion: str = '',
              telefono: str = '', email: str = '') -> int:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO clientes_sifen (ruc, razon_social, direccion, telefono, email)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (ruc.strip(), razon_social.strip(), direccion, telefono, email))
            conn.commit()
            return cur.fetchone()[0]

    def actualizar(self, cliente_id: int, ruc: str, razon_social: str,
                   direccion: str = '', telefono: str = '', email: str = '') -> bool:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE clientes_sifen SET ruc=%s, razon_social=%s, direccion=%s,
                                    telefono=%s, email=%s
                WHERE id=%s
            """, (ruc.strip(), razon_social.strip(), direccion, telefono, email, cliente_id))
            conn.commit()
            return cur.rowcount > 0

    def cambiar_estado(self, cliente_id: int, activo: bool) -> bool:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("UPDATE clientes_sifen SET activo=%s WHERE id=%s", (activo, cliente_id))
            conn.commit()
            return cur.rowcount > 0


class RepositorioProductos:

    def __init__(self, db: Conexion):
        self.db = db

    def listar(self, busqueda: str = '', solo_activos: bool = True) -> list:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            filtro_activo = "AND activo = TRUE" if solo_activos else ""
            if busqueda:
                cur.execute(f"""
                    SELECT id, codigo, descripcion, precio_unitario, unidad_medida, iva, activo
                    FROM productos_sifen
                    WHERE (descripcion ILIKE %s OR codigo ILIKE %s) {filtro_activo}
                    ORDER BY descripcion LIMIT 50
                """, (f'%{busqueda}%', f'%{busqueda}%'))
            else:
                cur.execute(f"""
                    SELECT id, codigo, descripcion, precio_unitario, unidad_medida, iva, activo
                    FROM productos_sifen
                    WHERE 1=1 {filtro_activo}
                    ORDER BY descripcion LIMIT 200
                """)
            return cur.fetchall()

    def obtener(self, producto_id: int) -> Optional[dict]:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, codigo, descripcion, precio_unitario, unidad_medida, iva, activo "
                "FROM productos_sifen WHERE id = %s", (producto_id,)
            )
            return cur.fetchone()

    def crear(self, descripcion: str, precio_unitario: int, iva: int,
              unidad_medida: int = 77, codigo: str = '') -> int:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO productos_sifen (codigo, descripcion, precio_unitario, unidad_medida, iva)
                VALUES (%s, %s, %s, %s, %s) RETURNING id
            """, (codigo.strip() or None, descripcion.strip(), precio_unitario, unidad_medida, iva))
            conn.commit()
            return cur.fetchone()[0]

    def actualizar(self, producto_id: int, descripcion: str, precio_unitario: int,
                   iva: int, unidad_medida: int = 77, codigo: str = '') -> bool:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE productos_sifen SET codigo=%s, descripcion=%s, precio_unitario=%s,
                                     unidad_medida=%s, iva=%s
                WHERE id=%s
            """, (codigo.strip() or None, descripcion.strip(), precio_unitario,
                  unidad_medida, iva, producto_id))
            conn.commit()
            return cur.rowcount > 0

    def cambiar_estado(self, producto_id: int, activo: bool) -> bool:
        conn = self.db.conectar()
        with conn.cursor() as cur:
            cur.execute("UPDATE productos_sifen SET activo=%s WHERE id=%s", (activo, producto_id))
            conn.commit()
            return cur.rowcount > 0
