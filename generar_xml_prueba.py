"""
Script para generar el XML de prueba firmado y enviarlo a SIFEN.

Uso:
    cd FacturacionElectronica
    python generar_xml_prueba.py

El número de documento se obtiene automáticamente de la base de datos
(último número + 1). Si la BD no está disponible usa NUMERO_DOC_FALLBACK.

El archivo soap_prueba.xml también se guarda para cargarlo en SoapUI si
se necesita: File -> Load Request from File (NO copiar y pegar).
"""
import sys
import json
import random
import subprocess
import re
import warnings
from datetime import datetime
warnings.filterwarnings('ignore')

sys.path.insert(0, 'sifen_py')

from sifen_py.core.config import SifenConfig
from sifen_py.services.signer import XMLSigner
from sifen_py.db.conexion import Conexion
from sifen_py.db.repositorio import RepositorioDE

# ── Configuración ─────────────────────────────────────────────────────────────
CERT_PATH       = 'certificado_sifen.pfx'
CERT_PASSWORD   = 'ferreteria2026.'
RUC             = '5722781-0'
RAZON_SOCIAL    = 'AMARILLA ORTIZ OSVALDO MATHIAS ANTONIO'
NOMBRE_FANTASIA = 'AMARILLA ORTIZ'
TIMBRADO        = '05722781'
TIMBRADO_FECHA  = '2026-06-02'
CSC             = 'ABCD0000000000000000000000000000'
CSC_ID          = '0001'

# Número de documento de respaldo — solo se usa si la BD no está disponible
NUMERO_DOC_FALLBACK = 82

NODE_PATH   = 'facturacionelectronicapy-xmlgen-main'
OUTPUT_FILE = 'soap_prueba.xml'
# ─────────────────────────────────────────────────────────────────────────────


def main():
    import os
    print("=" * 55)
    print("  GENERADOR DE XML PRUEBA SIFEN")
    print("=" * 55)

    # 1. Verificar certificado
    if not os.path.exists(CERT_PATH):
        print(f"\nERROR: No se encontró el certificado: {CERT_PATH}")
        print("Colocá el archivo certificado_sifen.pfx en esta carpeta.")
        sys.exit(1)

    # 2. Conectar a BD y obtener próximo número de documento
    print("\n[1] Conectando a base de datos...")
    db = Conexion()
    repo = None
    try:
        db.crear_base_si_no_existe()
        db.ejecutar_schema()
        repo = RepositorioDE(db)
        numero_doc = repo.proximo_numero_doc()
        print(f"    OK — próximo número: {numero_doc}")
    except Exception as e:
        numero_doc = NUMERO_DOC_FALLBACK
        print(f"    ADVERTENCIA: BD no disponible ({e})")
        print(f"    Usando número de respaldo: {numero_doc}")

    # Código de seguridad aleatorio de 9 dígitos (distinto en cada ejecución)
    codigo_seguridad = str(random.randint(100_000_000, 999_999_999))

    # 3. Crear config
    config = SifenConfig(
        ambiente='test',
        ruc=RUC,
        razon_social=RAZON_SOCIAL,
        nombre_fantasia=NOMBRE_FANTASIA,
        certificado_path=CERT_PATH,
        certificado_password=CERT_PASSWORD,
        csc=CSC,
        csc_id=CSC_ID,
        timbrado_numero=TIMBRADO,
        timbrado_fecha=TIMBRADO_FECHA,
        establecimiento='001',
        punto_expedicion='001',
        departamento=1,
        distrito=1,
        ciudad=1,
    )

    # 4. Parámetros para Node.js xmlgen
    params = {
        "version": 150,
        "ruc": RUC,
        "razonSocial": RAZON_SOCIAL,
        "nombreFantasia": NOMBRE_FANTASIA,
        "timbradoNumero": TIMBRADO,
        "timbradoFecha": TIMBRADO_FECHA,
        "actividadesEconomicas": [
            {"codigo": "47521", "descripcion": "COMERCIO AL POR MENOR DE ARTÍCULOS DE FERRETERÍA"}
        ],
        "tipoContribuyente": 2,
        "tipoRegimen": 8,
        "establecimientos": [{
            "codigo": "001",
            "direccion": "Asuncion",
            "numeroCasa": "1",
            "departamento": 1,
            "departamentoDescripcion": "ASUNCION",
            "distrito": 1,
            "distritoDescripcion": "ASUNCION (DISTRITO)",
            "ciudad": 1,
            "ciudadDescripcion": "ASUNCION (DISTRITO)",
            "telefono": "0981000000",
            "email": "empresa@empresa.com",
            "denominacion": "Casa Central"
        }]
    }

    # 5. Datos del documento
    data = {
        "tipoDocumento": 1,
        "establecimiento": "001",
        "punto": "001",
        "numero": numero_doc,
        "codigoSeguridadAleatorio": codigo_seguridad,
        "descripcion": "Factura de prueba",
        "observacion": "Prueba de envio SIFEN",
        "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "tipoEmision": 1,
        "tipoTransaccion": 1,
        "tipoImpuesto": 1,
        "moneda": "PYG",
        "cliente": {
            "contribuyente": True,
            "ruc": "5722781-0",
            "razonSocial": "AMARILLA ORTIZ OSVALDO MATHIAS ANTONIO",
            "nombreFantasia": "AMARILLA ORTIZ",
            "tipoOperacion": 1,
            "direccion": "Asuncion",
            "numeroCasa": "1",
            "departamento": 1,
            "departamentoDescripcion": "ASUNCION",
            "distrito": 1,
            "distritoDescripcion": "ASUNCION (DISTRITO)",
            "ciudad": 1,
            "ciudadDescripcion": "ASUNCION (DISTRITO)",
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
            "tipoContribuyente": 2,
            "documentoTipo": 1,
            "documentoNumero": "5722781",
            "telefono": "0981000000",
            "email": "empresa@empresa.com"
        },
        "usuario": {
            "documentoTipo": 1,
            "documentoNumero": "1234567",
            "nombre": RAZON_SOCIAL,
            "cargo": "Vendedor"
        },
        "factura": {"presencia": 1},
        "condicion": {
            "tipo": 1,
            "entregas": [{
                "tipo": 1,
                "monto": "150000",
                "moneda": "PYG",
                "monedaDescripcion": "Guarani",
                "cambio": 0.0
            }]
        },
        "items": [{
            "codigo": "001",
            # Descripción obligatoria para ambiente de prueba (Guía de Pruebas DNIT sección 2)
            "descripcion": "DOCUMENTO ELECTRONICO SIN VALOR COMERCIAL NI FISCAL - GENERADO EN AMBIENTE DE PRUEBA",
            "observacion": "Prueba",
            "unidadMedida": 77,
            "cantidad": 1,
            "precioUnitario": 150000,
            "cambio": 0.0,
            "ivaTipo": 1,
            "ivaBase": 100,
            "iva": 10
        }]
    }

    # 6. Generar XML via Node.js
    print(f"\n[2] Generando XML con Node.js (doc #{numero_doc})...")
    script = (
        f'const x=require("./dist/index.js");'
        f'const p={json.dumps(params, ensure_ascii=False)};'
        f'const d={json.dumps(data, ensure_ascii=False)};'
        f'x.default.generateXMLDE(p,d)'
        f'.then(xml=>{{console.log(xml)}})'
        f'.catch(e=>{{console.error(e.message);process.exit(1)}});'
    )
    r = subprocess.run(
        ['node', '-'], input=script.encode('utf-8'),
        capture_output=True,
        cwd=NODE_PATH, timeout=30
    )
    if r.returncode != 0:
        print(f"    ERROR Node.js: {r.stderr.decode('utf-8', errors='replace')[:500]}")
        sys.exit(1)

    xml_generado = r.stdout.decode('utf-8').strip()
    print(f"    OK — {len(xml_generado)} caracteres")

    # 7. Firmar XML
    print("\n[3] Firmando XML con certificado digital...")
    signer = XMLSigner(config)
    xml_firmado = signer.firmar_xml(xml_generado)
    print(f"    OK — {len(xml_firmado)} caracteres")

    m_cdc = re.search(r'DE Id="([^"]+)"', xml_firmado)
    cdc = m_cdc.group(1) if m_cdc else 'NO ENCONTRADO'
    print(f"    CDC: {cdc}")

    # 8. Guardar envelope para SoapUI
    print("\n[4] Construyendo envelope SOAP...")
    soap = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<env:Envelope xmlns:env="http://www.w3.org/2003/05/soap-envelope">'
        '<env:Header/>'
        '<env:Body>'
        '<rEnviDe xmlns="http://ekuatia.set.gov.py/sifen/xsd">'
        '<dId>1</dId>'
        f'<xDE>{xml_firmado}</xDE>'
        '</rEnviDe>'
        '</env:Body>'
        '</env:Envelope>'
    )
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(soap)
    print(f"    OK — guardado en: {OUTPUT_FILE}")

    # 9. Guardar como pendiente ANTES de enviar
    if repo:
        # Agregar timbrado al data para que el KuDE lo pueda mostrar
        data_para_bd = {**data, 'timbrado': TIMBRADO}
        repo.guardar_pendiente(
            cdc=cdc,
            numero_doc=numero_doc,
            xml_firmado=xml_firmado,
            soap_envelope=soap,
            ruc_receptor=data['cliente']['ruc'],
            razon_social_receptor=data['cliente']['razonSocial'],
            monto_total=int(data['condicion']['entregas'][0]['monto']),
            data_documento=data_para_bd,
        )

    # 10. Enviar a SIFEN
    print("\n[5] Enviando a SIFEN...")
    from sifen_py.services.soap_client import SifenSOAPClient
    client = SifenSOAPClient(config)
    respuesta = client.enviar_de_directo(xml_firmado)

    # 11. Actualizar estado en BD con la respuesta
    if repo:
        repo.actualizar_respuesta(
            cdc=cdc,
            codigo=respuesta.codigo,
            descripcion=respuesta.descripcion,
            respuesta_xml=respuesta.raw.get('xml', ''),
            protocolo=respuesta.raw.get('protocolo'),
        )

    print("\n" + "=" * 55)
    print(f"  Doc #:    {numero_doc}")
    print(f"  CDC:      {cdc}")
    print(f"  Código:   {respuesta.codigo}")
    print(f"  Estado:   {respuesta.descripcion}")
    if respuesta.codigo == '0260':
        print("  *** APROBADO ***")
    elif respuesta.codigo not in ('0260',):
        raw_xml = respuesta.raw.get('xml', '')
        if raw_xml:
            print(f"\n  Respuesta SIFEN completa:\n{raw_xml}")
    print("=" * 55)

    if db:
        db.cerrar()


if __name__ == '__main__':
    main()
