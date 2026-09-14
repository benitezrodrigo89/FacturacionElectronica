"""
Script para crear la base de datos y las tablas de sifen_py.

Ejecutar UNA SOLA VEZ antes de usar el sistema:

    cd FacturacionElectronica
    python inicializar_bd.py

Requiere que PostgreSQL esté corriendo.
"""
import sys
sys.path.insert(0, 'sifen_py')

from sifen_py.db.conexion import Conexion

def main():
    print("=" * 50)
    print("  INICIALIZACIÓN DE BASE DE DATOS SIFEN")
    print("=" * 50)

    db = Conexion()

    print(f"\n  Host:     {db.host}:{db.port}")
    print(f"  Base:     {db.dbname}")
    print(f"  Usuario:  {db.user}")

    print("\n[1] Verificando/creando base de datos...")
    db.crear_base_si_no_existe()
    print("    OK")

    print("[2] Aplicando schema (tablas e índices)...")
    db.ejecutar_schema()
    print("    OK")

    print("[3] Verificando tabla...")
    conn = db.conectar()
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) FROM documentos_electronicos
        """)
        row = cur.fetchone()
        total = row[0] if isinstance(row, tuple) else list(row.values())[0]
    print(f"    Registros actuales: {total}")

    db.cerrar()

    print("\n" + "=" * 50)
    print("  Base de datos lista.")
    print("=" * 50)

if __name__ == '__main__':
    main()
