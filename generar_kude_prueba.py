"""
Genera el KuDE (PDF del comprobante) para el último documento aprobado en la BD.

Uso:
    cd FacturacionElectronica
    python generar_kude_prueba.py

El PDF se guarda como kude_<numero_doc>.pdf en la carpeta actual.
Podés pasar un CDC específico como argumento:
    python generar_kude_prueba.py 01057227810001001000008220260914...
"""
import sys
import json
import os
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, 'sifen_py')

from sifen_py.core.config import SifenConfig
from sifen_py.generators.kude import KuDEGenerator
from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE

# ── Configuración ─────────────────────────────────────────────────────────────
CERT_PATH     = 'certificado_sifen.pfx'
CERT_PASSWORD = 'ferreteria2026.'
RUC           = '5722781-0'
# ─────────────────────────────────────────────────────────────────────────────


def main():
    # CDC por argumento o último de la BD
    cdc_arg = sys.argv[1].strip() if len(sys.argv) > 1 else None

    db = Conexion()
    repo = RepositorioDE(db)

    if cdc_arg:
        fila = repo.obtener_por_cdc(cdc_arg)
        if not fila:
            print(f"ERROR: No se encontró el CDC en la BD: {cdc_arg}")
            sys.exit(1)
    else:
        # Buscar el último documento aprobado
        aprobados = repo.listar_por_estado('aprobado', limite=1)
        if not aprobados:
            print("ERROR: No hay documentos aprobados en la base de datos.")
            print("       Enviá un documento primero con: python generar_xml_prueba.py")
            sys.exit(1)
        cdc_arg = dict(aprobados[0])['cdc']
        fila = repo.obtener_por_cdc(cdc_arg)

    fila = dict(fila)
    cdc       = fila['cdc']
    numero    = fila['numero_doc']
    protocolo = fila.get('protocolo_autorizacion')
    estado_bd = fila.get('estado', 'pendiente')
    fecha_resp = str(fila.get('fecha_respuesta') or '')

    print("=" * 55)
    print("  GENERADOR DE KuDE")
    print("=" * 55)
    print(f"\n  Doc #:     {numero}")
    print(f"  CDC:       {cdc[:30]}…")
    print(f"  Estado BD: {estado_bd}")
    if protocolo:
        print(f"  Protocolo: {protocolo}")

    # Recuperar data_json
    data_json_str = fila.get('data_json')
    if not data_json_str:
        print("\nERROR: Este documento no tiene data_json guardado en la BD.")
        print("       Solo los documentos enviados DESPUÉS de esta actualización lo tienen.")
        print("       Enviá un nuevo documento con generar_xml_prueba.py y volvé a intentar.")
        db.cerrar()
        sys.exit(1)

    data = json.loads(data_json_str)

    # Configurar emisor
    config = SifenConfig(
        ambiente='test',
        ruc=RUC,
        razon_social='AMARILLA ORTIZ OSVALDO MATHIAS ANTONIO',
        nombre_fantasia='AMARILLA ORTIZ',
        certificado_path=CERT_PATH if os.path.exists(CERT_PATH) else 'dummy.pfx',
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
        actividad_economica='COMERCIO AL POR MENOR DE ARTÍCULOS DE FERRETERÍA',
        direccion='Asuncion',
        telefono='0981000000',
        email='empresa@empresa.com',
    )

    estado_kude = 'A' if estado_bd == 'aprobado' else ('R' if estado_bd == 'rechazado' else 'P')

    print("\n[1] Generando PDF KuDE...")
    gen = KuDEGenerator(config)
    pdf = gen.generar(
        data=data,
        cdc=cdc,
        estado=estado_kude,
        numero_protocolo=protocolo,
        fecha_procesamiento=fecha_resp,
    )

    nombre_pdf = f"kude_{numero}.pdf"
    with open(nombre_pdf, 'wb') as f:
        f.write(pdf)

    print(f"    OK — {len(pdf):,} bytes")
    print(f"\n  PDF guardado en: {nombre_pdf}")
    print("=" * 55)

    db.cerrar()


if __name__ == '__main__':
    main()
