"""
Corrige registros que quedaron con estado 'duplicado' en lugar de 'aprobado'.

CDC duplicado (código 1001) significa que SIFEN ya tenía ese documento —
es decir, estaba aprobado. Este script los actualiza a estado 'aprobado'.

Ejecutar una sola vez:
    python corregir_estados_bd.py
"""
import sys
sys.path.insert(0, 'sifen_py')

from sifen_py.db.conexion import Conexion

def main():
    db = Conexion()
    conn = db.conectar()

    with conn.cursor() as cur:
        cur.execute("""
            UPDATE documentos_electronicos
            SET estado = 'aprobado'
            WHERE codigo_sifen = '1001'
              AND estado != 'aprobado'
            RETURNING cdc, numero_doc
        """)
        filas = cur.fetchall()

    conn.commit()

    if filas:
        print(f"Corregidos {len(filas)} registros:")
        for f in filas:
            fila = dict(f) if hasattr(f, 'keys') else {'cdc': f[0], 'numero_doc': f[1]}
            print(f"  doc #{fila['numero_doc']} — CDC: {fila['cdc'][:30]}…")
    else:
        print("No había registros para corregir.")

    db.cerrar()

if __name__ == '__main__':
    main()
