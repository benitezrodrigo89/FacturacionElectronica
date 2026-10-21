"""
Migraciones de base de datos — ejecutar cuando haya cambios de schema.

    cd FacturacionElectronica
    python migrar_bd.py
"""
import sys
sys.path.insert(0, 'sifen_py')
from sifen_py.db.conexion import Conexion

MIGRACIONES = [
    # v1: agregar data_json para el KuDE
    """
    ALTER TABLE documentos_electronicos
    ADD COLUMN IF NOT EXISTS data_json TEXT;
    """,
    # v2: agregar protocolo_lote para envío asíncrono por lote
    """
    ALTER TABLE documentos_electronicos
    ADD COLUMN IF NOT EXISTS protocolo_lote VARCHAR(50);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_de_protocolo_lote
    ON documentos_electronicos (protocolo_lote);
    """,
]

def main():
    db = Conexion()
    conn = db.conectar()
    print("Aplicando migraciones...")
    for i, sql in enumerate(MIGRACIONES, 1):
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
        print(f"  [{i}] OK")
    db.cerrar()
    print("Listo.")

if __name__ == '__main__':
    main()
