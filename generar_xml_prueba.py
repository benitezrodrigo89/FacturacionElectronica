"""
Script para generar el XML de prueba firmado para enviar a SIFEN via SoapUI.

Uso:
    cd FacturacionElectronica
    python3 generar_xml_prueba.py

El archivo generado se llama: soap_prueba.xml
Cargarlo en SoapUI via File -> Load Request from File (NO copiar y pegar).
"""
import sys
import json
import subprocess
import re
import warnings
warnings.filterwarnings('ignore')

sys.path.insert(0, 'sifen_py')

from sifen_py.core.config import SifenConfig
from sifen_py.services.signer import XMLSigner

# ── Configuración ─────────────────────────────────────────────────────────────
CERT_PATH      = 'certificado_sifen.pfx'
CERT_PASSWORD  = 'ferreteria2026.'
RUC            = '5722781-0'
RAZON_SOCIAL   = 'AMARILLA ORTIZ OSVALDO MATHIAS ANTONIO'
NOMBRE_FANTASIA = 'AMARILLA ORTIZ'
TIMBRADO       = '05722781'
TIMBRADO_FECHA = '2026-06-02'   # Fecha de inicio de vigencia en Marangatu
CSC            = 'ABCD00000000000000000000000000000'
CSC_ID         = '0001'

# Número de documento — incrementar manualmente en cada prueba
NUMERO_DOC = 56

# Código de seguridad aleatorio de 9 dígitos — cambiar en cada envío
CODIGO_SEGURIDAD = '123456789'

NODE_PATH = 'facturacionelectronicapy-xmlgen-main'
OUTPUT_FILE = 'soap_prueba.xml'
# ─────────────────────────────────────────────────────────────────────────────


def main():
    print("=" * 55)
    print("  GENERADOR DE XML PRUEBA SIFEN")
    print("=" * 55)

    # 1. Verificar certificado
    import os
    if not os.path.exists(CERT_PATH):
        print(f"\nERROR: No se encontró el certificado: {CERT_PATH}")
        print("Colocá el archivo certificado_sifen.pfx en esta carpeta.")
        sys.exit(1)

    # 2. Crear config
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

    # 3. Parámetros para Node.js xmlgen
    params = {
        "version": 150,
        "ruc": RUC,
        "razonSocial": RAZON_SOCIAL,
        "nombreFantasia": NOMBRE_FANTASIA,
        "timbradoNumero": TIMBRADO,
        "timbradoFecha": TIMBRADO_FECHA,
        "actividadesEconomicas": [
            {"codigo": "47521", "descripcion": "Comercio al por menor de articulos de ferreteria"}
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

    # 4. Datos del documento
    # Nota: descripcion del ítem es obligatoria para ambiente de prueba
    data = {
        "tipoDocumento": 1,
        "establecimiento": "001",
        "punto": "001",
        "numero": NUMERO_DOC,
        "codigoSeguridadAleatorio": CODIGO_SEGURIDAD,
        "descripcion": "Factura de prueba",
        "observacion": "Prueba de envio SIFEN",
        "fecha": "2026-07-24T10:00:00",
        "tipoEmision": 1,
        "tipoTransaccion": 1,
        "tipoImpuesto": 1,
        "moneda": "PYG",
        "cliente": {
            "contribuyente": True,
            "ruc": "2005001-1",
            "razonSocial": "CLIENTE SA",
            "nombreFantasia": "CLIENTE SA",
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
            "tipoContribuyente": 1,
            "documentoTipo": 1,
            "documentoNumero": "2324234",
            "telefono": "0981000001",
            "email": "cliente@cliente.com"
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

    # 5. Generar XML via Node.js
    print(f"\n[1] Generando XML con Node.js (doc #{NUMERO_DOC})...")
    script = (
        f'const x=require("./dist/index.js");'
        f'const p={json.dumps(params, ensure_ascii=False)};'
        f'const d={json.dumps(data, ensure_ascii=False)};'
        f'x.default.generateXMLDE(p,d)'
        f'.then(xml=>{{console.log(xml)}})'
        f'.catch(e=>{{console.error(e.message);process.exit(1)}});'
    )
    r = subprocess.run(
        ['node', '-'], input=script,
        capture_output=True, text=True,
        cwd=NODE_PATH, timeout=30
    )
    if r.returncode != 0:
        print(f"    ERROR Node.js: {r.stderr[:500]}")
        sys.exit(1)

    xml_generado = r.stdout.strip()
    print(f"    OK — {len(xml_generado)} caracteres")

    # 6. Firmar XML
    print("\n[2] Firmando XML con certificado digital...")
    signer = XMLSigner(config)
    xml_firmado = signer.firmar_xml(xml_generado)
    print(f"    OK — {len(xml_firmado)} caracteres")

    m_cdc = re.search(r'DE Id="([^"]+)"', xml_firmado)
    cdc = m_cdc.group(1) if m_cdc else 'NO ENCONTRADO'
    print(f"    CDC: {cdc}")

    # 7. Construir envelope SOAP
    print("\n[3] Construyendo envelope SOAP...")
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

    # 8. Guardar archivo
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(soap)

    print(f"    OK — guardado en: {OUTPUT_FILE}")

    print("\n" + "=" * 55)
    print(f"  Archivo listo: {OUTPUT_FILE}")
    print(f"  CDC: {cdc}")
    print("=" * 55)
    print("\nIMPORTANTE: En SoapUI cargar con:")
    print("  File -> Load Request from File")
    print("  NO usar copiar y pegar (rompe la firma)")


if __name__ == '__main__':
    main()
