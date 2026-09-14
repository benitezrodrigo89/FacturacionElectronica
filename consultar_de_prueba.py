"""
Script para consultar el estado de un Documento Electrónico en SIFEN por CDC.

Uso:
    cd FacturacionElectronica
    python consultar_de_prueba.py            <- consulta el último documento enviado
    python consultar_de_prueba.py            <- con CDCS_A_CONSULTAR vacío = último de la BD

Si CDCS_A_CONSULTAR está vacío, consulta automáticamente el último documento
registrado en la base de datos. Para consultar uno específico, agregá su CDC a la lista.
"""
import sys
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, 'sifen_py')

from sifen_py.core.config import SifenConfig
from sifen_py.services.soap_client import SifenSOAPClient
from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE

# ── Configuración ─────────────────────────────────────────────────────────────
CERT_PATH     = 'certificado_sifen.pfx'
CERT_PASSWORD = 'ferreteria2026.'
RUC           = '5722781-0'

# CDC(s) a consultar — podés poner uno o varios
# Copiá el CDC que aparece en la salida de generar_xml_prueba.py
CDCS_A_CONSULTAR = [
    # Ejemplo: CDC del doc aprobado #79
    # '01057227810001001000007912026091400000001234560',
    # Pegá aquí los CDCs que quieras consultar:
]
# ─────────────────────────────────────────────────────────────────────────────


def main():
    import os
    if not os.path.exists(CERT_PATH):
        print(f"ERROR: No se encontró el certificado: {CERT_PATH}")
        sys.exit(1)

    config = SifenConfig(
        ambiente='test',
        ruc=RUC,
        razon_social='AMARILLA ORTIZ OSVALDO MATHIAS ANTONIO',
        nombre_fantasia='AMARILLA ORTIZ',
        certificado_path=CERT_PATH,
        certificado_password=CERT_PASSWORD,
        csc='ABCD0000000000000000000000000000',
        csc_id='0001',
        timbrado_numero='05722781',
        timbrado_fecha='2026-06-02',
        establecimiento='001',
        punto_expedicion='001',
        departamento=1,
        distrito=1,
        ciudad=1,
    )

    client = SifenSOAPClient(config)

    # Conectar a BD
    db = Conexion()
    repo = None
    try:
        db.conectar()
        repo = RepositorioDE(db)
    except Exception:
        pass

    # Determinar qué CDCs consultar
    cdcs = [c.strip() for c in CDCS_A_CONSULTAR if c.strip()]

    if not cdcs:
        # Lista vacía → consultar el último documento enviado desde la BD
        if repo:
            ultimo = repo.ultimo_enviado()
            if ultimo:
                fila = dict(ultimo) if hasattr(ultimo, 'keys') else {
                    'cdc': ultimo[1], 'numero_doc': ultimo[2], 'estado': ultimo[3]
                }
                cdcs = [fila['cdc']]
                print(f"  (Consultando último documento enviado: doc #{fila['numero_doc']})")
            else:
                print("ERROR: No hay documentos en la base de datos.")
                sys.exit(1)
        else:
            print("ERROR: BD no disponible y CDCS_A_CONSULTAR está vacío.")
            print("       Agregá un CDC manualmente en la lista CDCS_A_CONSULTAR.")
            sys.exit(1)

    print("=" * 60)
    print("  CONSULTA DE ESTADO DE DOCUMENTOS ELECTRÓNICOS — SIFEN")
    print("=" * 60)

    for cdc in cdcs:
        cdc = cdc.strip()
        if not cdc:
            continue

        print(f"\n  CDC: {cdc}")
        print(f"  {'-' * 56}")

        respuesta = client.consultar_de_directo(cdc)

        print(f"  Código:    {respuesta.codigo}")
        print(f"  Estado:    {respuesta.descripcion}")

        if respuesta.raw.get('estado'):
            print(f"  Estado DE: {respuesta.raw['estado']}")

        if respuesta.raw.get('protocolo'):
            print(f"  Protocolo: {respuesta.raw['protocolo']}")

        if respuesta.raw.get('fecha'):
            print(f"  Fecha:     {respuesta.raw['fecha']}")

        if respuesta.codigo == '0422':
            print("  *** APROBADO ***")
        elif respuesta.codigo == '0420':
            print("  *** NO ENCONTRADO / RECHAZADO ***")
        else:
            raw_xml = respuesta.raw.get('xml', '')
            if raw_xml:
                print(f"\n  Respuesta SIFEN completa:\n{raw_xml}")

        # Actualizar estado en BD si está disponible
        if repo and respuesta.codigo in ('0422', '0420'):
            try:
                repo.actualizar_estado_consulta(
                    cdc=cdc,
                    codigo=respuesta.codigo,
                    descripcion=respuesta.descripcion,
                    protocolo=respuesta.raw.get('protocolo'),
                    respuesta_xml=respuesta.raw.get('xml'),
                )
                print("  BD actualizada")
            except Exception:
                pass

    print("\n" + "=" * 60)

    if db:
        db.cerrar()


if __name__ == '__main__':
    main()
