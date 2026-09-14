"""
Script para consultar el estado de un Documento Electrónico en SIFEN por CDC.

Uso:
    cd FacturacionElectronica
    python consultar_de_prueba.py

Podés consultar cualquier CDC que hayas enviado antes.
También podés consultar múltiples CDCs de una vez.
"""
import sys
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, 'sifen_py')

from sifen_py.core.config import SifenConfig
from sifen_py.services.soap_client import SifenSOAPClient

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
    if not CDCS_A_CONSULTAR:
        print("ERROR: Agregá al menos un CDC en la lista CDCS_A_CONSULTAR")
        print("       (Copiá el CDC que aparece en la salida del script generar_xml_prueba.py)")
        sys.exit(1)

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

    print("=" * 60)
    print("  CONSULTA DE ESTADO DE DOCUMENTOS ELECTRÓNICOS — SIFEN")
    print("=" * 60)

    for cdc in CDCS_A_CONSULTAR:
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

    print("\n" + "=" * 60)


if __name__ == '__main__':
    main()
