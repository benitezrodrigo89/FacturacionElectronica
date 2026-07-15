"""
Ejemplo básico de uso del sistema SIFEN integrado
Genera XML (Node.js) + Firma (Python)
"""
from sifen_py.core.config import SifenConfig
from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.services.signer import XMLSigner
from loguru import logger
import sys

# Configurar logging
logger.remove()
logger.add(sys.stdout, level="INFO")


def ejemplo_factura_simple():
    """
    Ejemplo de generación y firma de una factura electrónica simple
    """
    print("="*60)
    print("EJEMPLO: Factura Electrónica Simple")
    print("="*60)

    # 1. CONFIGURACIÓN
    print("\n1. Configurando cliente SIFEN...")
    config = SifenConfig(
        ambiente='test',  # Ambiente de pruebas
        ruc='80069563-1',
        razon_social='TIPS S.A. TECNOLOGIA Y SERVICIOS',
        nombre_fantasia='TIPS S.A.',
        certificado_path='/ruta/a/tu/certificado.pfx',  # CAMBIAR
        certificado_password='tu_password',  # CAMBIAR
        csc='298398',  # Código de seguridad
        establecimiento='001',
        punto_expedicion='001',
        actividad_economica='1254',
        direccion='Barrio Carolina',
        departamento=11,
        distrito=145,
        ciudad=3432,
        telefono='0973-527155',
        email='tips@tips.com.py'
    )

    # 2. DATOS DE LA FACTURA
    print("\n2. Preparando datos de la factura...")
    factura_data = {
        "tipoDocumento": 1,  # Factura Electrónica
        "establecimiento": "001",
        "punto": "001",
        "numero": "0000001",
        "fecha": "2026-05-28T10:30:00",
        "tipoEmision": 1,
        "tipoTransaccion": 1,  # Venta de mercadería
        "tipoImpuesto": 1,
        "moneda": "PYG",
        "condicionAnticipo": 1,
        "condicionTipoCambio": 1,

        # Cliente
        "cliente": {
            "contribuyente": True,
            "ruc": "2005001-1",
            "razonSocial": "Cliente Ejemplo S.A.",
            "nombreFantasia": "Cliente Ejemplo",
            "tipoOperacion": 1,  # B2B
            "direccion": "Asunción, Paraguay",
            "numeroCasa": "1515",
            "departamento": 11,
            "departamentoDescripcion": "CENTRAL",
            "distrito": 1,
            "distritoDescripcion": "ASUNCION",
            "ciudad": 1,
            "ciudadDescripcion": "ASUNCION",
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
            "tipoContribuyente": 2,
            "telefono": "021-123456",
            "email": "cliente@ejemplo.com"
        },

        # Condición de venta
        "condicion": {
            "tipo": 1,  # Contado
            "entregas": [{
                "tipo": 1,  # Efectivo
                "monto": "110000",
                "moneda": "PYG",
                "cambio": 0
            }]
        },

        # Items
        "items": [{
            "codigo": "PROD-001",
            "descripcion": "Producto de ejemplo",
            "cantidad": 2,
            "precioUnitario": 50000,
            "ivaTipo": 1,
            "ivaProporcion": 100,
            "iva": 10,
            "unidadMedida": 77
        }]
    }

    # 3. GENERAR XML (via Node.js)
    print("\n3. Generando XML con Node.js...")
    try:
        xml_generator = XMLGeneratorWrapper(config)
        xml = xml_generator.generar_xml_de(factura_data)
        print(f"   ✓ XML generado: {len(xml)} caracteres")

        # Guardar XML sin firmar
        with open("/tmp/factura_sin_firmar.xml", "w", encoding="utf-8") as f:
            f.write(xml)
        print("   ✓ Guardado en: /tmp/factura_sin_firmar.xml")

    except Exception as e:
        print(f"   ✗ Error al generar XML: {e}")
        return

    # 4. FIRMAR XML (Python)
    print("\n4. Firmando XML con certificado digital...")
    try:
        signer = XMLSigner(config)
        xml_firmado = signer.firmar_xml(xml)
        print(f"   ✓ XML firmado: {len(xml_firmado)} caracteres")

        # Guardar XML firmado
        with open("/tmp/factura_firmada.xml", "w", encoding="utf-8") as f:
            f.write(xml_firmado)
        print("   ✓ Guardado en: /tmp/factura_firmada.xml")

        # Verificar firma
        if signer.verificar_firma(xml_firmado):
            print("   ✓ Firma verificada correctamente")

    except Exception as e:
        print(f"   ✗ Error al firmar XML: {e}")
        return

    # 5. INFORMACIÓN
    print("\n5. Información del certificado:")
    cert_info = signer.get_certificate_info()
    print(f"   - Subject: {cert_info.get('subject', {}).get('commonName', 'N/A')}")
    print(f"   - Válido desde: {cert_info.get('not_valid_before', 'N/A')}")
    print(f"   - Válido hasta: {cert_info.get('not_valid_after', 'N/A')}")

    print("\n" + "="*60)
    print("SIGUIENTE PASO: Enviar a SIFEN via SOAP")
    print("="*60)


def ejemplo_evento_cancelacion():
    """
    Ejemplo de generación de evento de cancelación
    """
    print("\n" + "="*60)
    print("EJEMPLO: Evento de Cancelación")
    print("="*60)

    config = SifenConfig(
        ambiente='test',
        ruc='80069563-1',
        razon_social='TIPS S.A.',
        certificado_path='/ruta/a/tu/certificado.pfx',
        certificado_password='tu_password',
        csc='298398'
    )

    print("\n1. Generando XML de cancelación...")
    try:
        xml_generator = XMLGeneratorWrapper(config)
        xml_evento = xml_generator.generar_xml_evento_cancelacion(
            cdc='01800695631001001000000612021112917595714694',
            motivo='Error en la emisión del documento'
        )
        print(f"   ✓ XML evento generado: {len(xml_evento)} caracteres")

        # Guardar
        with open("/tmp/evento_cancelacion.xml", "w", encoding="utf-8") as f:
            f.write(xml_evento)
        print("   ✓ Guardado en: /tmp/evento_cancelacion.xml")

    except Exception as e:
        print(f"   ✗ Error: {e}")

    print("\n2. Firmando evento...")
    try:
        signer = XMLSigner(config)
        xml_firmado = signer.firmar_xml(xml_evento)
        print(f"   ✓ Evento firmado: {len(xml_firmado)} caracteres")

        with open("/tmp/evento_cancelacion_firmado.xml", "w", encoding="utf-8") as f:
            f.write(xml_firmado)
        print("   ✓ Guardado en: /tmp/evento_cancelacion_firmado.xml")

    except Exception as e:
        print(f"   ✗ Error: {e}")


if __name__ == "__main__":
    print("\n")
    print("╔" + "="*58 + "╗")
    print("║  SISTEMA DE FACTURACIÓN ELECTRÓNICA SIFEN PARAGUAY     ║")
    print("║  Integración Node.js (XML) + Python (Firma/Envío)     ║")
    print("╚" + "="*58 + "╝")

    print("\n⚠️  IMPORTANTE:")
    print("   Antes de ejecutar, configurar:")
    print("   1. Ruta del certificado digital (.pfx)")
    print("   2. Contraseña del certificado")
    print("   3. Código de Seguridad (CSC)")
    print("\n")

    try:
        # Ejemplo 1: Factura simple
        ejemplo_factura_simple()

        # Ejemplo 2: Cancelación
        # ejemplo_evento_cancelacion()

    except KeyboardInterrupt:
        print("\n\n⚠️  Ejecución interrumpida por el usuario")
    except Exception as e:
        print(f"\n\n✗ Error general: {e}")
        logger.exception("Error en ejemplo")

    print("\n")
