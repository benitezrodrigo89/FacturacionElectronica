# Sistema de Facturación Electrónica SIFEN Paraguay (Integrado)

Sistema **completo y listo para producción** que combina lo mejor de dos mundos:
- ✅ Generación de XML (Node.js - proyecto probado de Marcos Jara)
- ✅ Firma Digital, Envío SOAP, KuDE PDF (Python - implementación nueva)

## 🚀 Características Completas

### ✅ Funcionalidades Implementadas

1. **Generación de XML** (via Node.js wrapper)
   - Todos los tipos de documentos (FE, NCE, NDE, AFE, NRE)
   - Cálculo automático de CDC
   - Validaciones del Manual Técnico v150
   - Eventos completos (Cancelación, Inutilización, etc.)

2. **Firma Digital XML** (Python)
   - XMLDSig W3C Enveloped Signature
   - Soporte para certificados .pfx/.p12
   - Autenticación mutua TLS

3. **Cliente SOAP** (Python)
   - Envío de lotes (hasta 50 DEs)
   - Consulta de estados
   - Consulta de DEs y RUC
   - Gestión de eventos

4. **Generación de KuDE** (Python)
   - PDF con formato oficial
   - Código QR integrado
   - Todos los tipos de documentos

5. **Gestión Completa**
   - Manejo de lotes asíncronos
   - Control de estados (0300, 0301, 0361, 0362)
   - Validaciones según Notas Técnicas
   - Logging completo

## 📋 Requisitos Previos

### Node.js (para generación de XML)
```bash
# Instalar Node.js 14+ y npm
cd FacturacionElectronica/facturacionelectronicapy-xmlgen-main
npm install
```

### Python (para firma, envío y PDF)
```bash
cd sifen_py
pip install -r requirements.txt
```

## 🔧 Instalación Rápida

```bash
# 1. Clonar o descargar el proyecto
git clone <tu-repo>
cd facturacionElectronicaPy

# 2. Instalar dependencias Node.js
cd FacturacionElectronica/facturacionelectronicapy-xmlgen-main
npm install
cd ../..

# 3. Instalar dependencias Python
cd sifen_py
pip install -r requirements.txt

# 4. Configurar certificado y credenciales
cp config.example.py config.py
# Editar config.py con tus datos
```

## 📁 Estructura del Proyecto

```
facturacionElectronicaPy/
├── FacturacionElectronica/
│   ├── Documentacion/              # Manuales y XSD oficiales
│   └── facturacionelectronicapy-xmlgen-main/  # Generador XML (Node.js)
│
└── sifen_py/                       # Sistema Python (NUEVO)
    ├── core/                       # Configuración y constantes
    ├── services/
    │   ├── xml_wrapper.py         # Wrapper Node.js
    │   ├── signer.py              # Firma digital
    │   ├── soap_client.py         # Cliente SOAP
    │   └── batch_manager.py       # Gestor de lotes
    ├── generators/
    │   └── kude.py                # Generador PDF
    ├── utils/
    │   ├── cdc.py                 # Utilidades CDC
    │   └── qr.py                  # Generador QR
    ├── examples/                   # Ejemplos completos
    └── tests/                      # Tests unitarios
```

## 💡 Uso Básico

### Configuración Inicial

```python
from sifen_py import SifenClient
from sifen_py.core.config import SifenConfig

# Configurar el cliente
config = SifenConfig(
    ambiente='test',  # 'test' o 'prod'
    ruc='80000001-1',
    razon_social='Mi Empresa S.A.',
    certificado_path='/path/to/certificado.pfx',
    certificado_password='mi_password',
    csc='CODIGO_SEGURIDAD_123456',
    establecimiento='001',
    punto_expedicion='001'
)

# Crear cliente
cliente = SifenClient(config)
```

### Emitir una Factura Electrónica Completa

```python
# Datos de la factura
factura_data = {
    "tipoDocumento": 1,  # Factura Electrónica
    "establecimiento": "001",
    "punto": "001",
    "numero": "0000001",
    "fecha": "2026-05-28T10:30:00",
    "tipoTransaccion": 1,  # Venta de mercadería
    "moneda": "PYG",
    "cliente": {
        "contribuyente": True,
        "ruc": "80000002-2",
        "razonSocial": "Cliente Ejemplo S.A.",
        "tipoOperacion": 1,  # B2B
        "direccion": "Asunción, Paraguay",
        "departamento": 11,
        "distrito": 145,
        "ciudad": 3432
    },
    "condicion": {
        "tipo": 1,  # Contado
        "entregas": [{
            "tipo": 1,  # Efectivo
            "monto": "100000",
            "moneda": "PYG"
        }]
    },
    "items": [{
        "codigo": "PROD-001",
        "descripcion": "Producto de ejemplo",
        "cantidad": 2,
        "precioUnitario": 50000,
        "ivaTipo": 1,
        "iva": 10,
        "unidadMedida": 77
    }]
}

# Proceso completo (4 pasos)
resultado = cliente.emitir_factura(factura_data)

print(f"CDC: {resultado['cdc']}")
print(f"Estado: {resultado['estado']}")
print(f"Número de Lote: {resultado['numero_lote']}")
print(f"PDF generado: {resultado['pdf_path']}")

# El método emitir_factura hace:
# 1. Generar XML (via Node.js)
# 2. Firmar XML (Python)
# 3. Enviar a SIFEN (Python SOAP)
# 4. Generar KuDE PDF (Python)
```

### Proceso Paso a Paso (Control Manual)

```python
# 1. Generar XML
xml = cliente.generar_xml(factura_data)

# 2. Firmar XML
xml_firmado = cliente.firmar_xml(xml)

# 3. Enviar lote a SIFEN
respuesta_lote = cliente.enviar_lote([xml_firmado])
print(f"Lote enviado: {respuesta_lote.numero_lote}")

# 4. Consultar estado (después de 10 minutos)
import time
time.sleep(600)  # Esperar 10 minutos
estado = cliente.consultar_lote(respuesta_lote.numero_lote)

# 5. Si está aprobado, generar PDF
if estado.aprobado:
    pdf_path = cliente.generar_kude(factura_data, estado.cdc)
    print(f"KuDE generado: {pdf_path}")
```

### Cancelar una Factura

```python
resultado = cliente.cancelar_factura(
    cdc='01800000001001001000000012026052810285012345678901',
    motivo='Error en la emisión del documento'
)

if resultado['aprobado']:
    print("Factura cancelada exitosamente")
```

### Inutilizar Numeración

```python
resultado = cliente.inutilizar_numeracion(
    tipo_documento=1,
    establecimiento='001',
    punto='001',
    numero_desde=100,
    numero_hasta=110,
    motivo='Numeración no utilizada por error en sistema'
)
```

### Consultar un DE por CDC

```python
de = cliente.consultar_de(
    cdc='01800000001001001000000012026052810285012345678901'
)

if de.aprobado:
    print(f"Documento aprobado")
    print(f"Fecha: {de.fecha}")
    print(f"Total: {de.total}")
    # Obtener XML del DE
    xml_de = de.xml
```

## 🌐 Ambientes

### Test (Pruebas)
```python
config = SifenConfig(ambiente='test', ...)
```
- URL: https://sifen-test.set.gov.py
- Documentos SIN valor jurídico

### Producción
```python
config = SifenConfig(ambiente='prod', ...)
```
- URL: https://sifen.set.gov.py
- Documentos CON valor jurídico y tributario

## 📚 Ejemplos Completos

Ver carpeta `examples/` para:
- ✅ `ejemplo_factura_completa.py` - Factura electrónica B2B
- ✅ `ejemplo_factura_contado.py` - Factura contado B2C
- ✅ `ejemplo_factura_credito.py` - Factura a crédito con cuotas
- ✅ `ejemplo_nota_credito.py` - Nota de crédito
- ✅ `ejemplo_autofactura.py` - Autofactura
- ✅ `ejemplo_cancelacion.py` - Cancelación de DE
- ✅ `ejemplo_consultas.py` - Consultas de estado
- ✅ `ejemplo_lote_masivo.py` - Envío de lote con 50 DEs

## ⚠️ Validaciones Importantes (Notas Técnicas)

### NT-021: Documentos Innominados
```python
# Si monto >= 35.000.000 Gs, NO puede ser innominado
if total >= 35000000:
    cliente.tipo_documento_identidad = 1  # Cédula paraguaya
```

### NT-001: Descuentos Globales
```python
# Fórmula: [F010 * E721 / 100] con tolerancia 0.8
descuento_global_item = (descuento_global_total * precio_item) / 100
```

### NT-026: Compras Públicas (B2G)
```python
# Código DNCP ahora es OPCIONAL
factura_data["cliente"]["tipoOperacion"] = 3  # B2G
factura_data["items"][0]["dncp"] = {
    "codigoNivelGeneral": "12345678",  # Opcional
    "codigoNivelEspecifico": "1234"    # Opcional
}
```

## 🔐 Seguridad

### Certificado Digital
- Formato: `.pfx` o `.p12`
- Emitido por PSC habilitada en Paraguay
- Debe contener el RUC del emisor

### CSC (Código de Seguridad del Contribuyente)
- Provisto por la SET
- Debe estar vigente en fecha de emisión
- Se valida en cada envío

### TLS Mutuo
- El sistema configura automáticamente la autenticación mutua
- Certificado cliente se envía en cada request SOAP

## 🧪 Testing

```bash
# Ejecutar todos los tests
pytest tests/

# Con cobertura
pytest tests/ --cov=sifen_py --cov-report=html

# Test específico
pytest tests/test_xml_wrapper.py
```

## 📊 Logs

El sistema genera logs automáticos:
```
logs/
├── sifen_2026-05-28.log
├── sifen_errors_2026-05-28.log
└── sifen_soap_2026-05-28.log
```

## 🆘 Resolución de Problemas

### Error: "Node.js no encontrado"
```bash
# Verificar instalación de Node.js
node --version
npm --version

# Si no está instalado
sudo apt-get install nodejs npm  # Linux
brew install node                # macOS
```

### Error: "Certificado inválido"
```python
# Verificar formato del certificado
from sifen_py.utils.cert_validator import validar_certificado

validar_certificado(
    path='/path/to/cert.pfx',
    password='password',
    ruc='80000001-1'
)
```

### Error: "CSC no vigente" (código 2501)
- Verificar que el CSC esté activo en la fecha de emisión
- Contactar a la SET para renovar

### Error: "Lote no encolado" (código 0301)
Motivos comunes:
- Documentos de diferentes RUC emisores
- Documentos de diferentes tipos
- Más de 50 documentos en el lote
- Tamaño del lote > 1000 KB

## 📞 Soporte Oficial SIFEN

- **Email**: facturacionelectronica@dnit.gov.py
- **Portal**: https://www.dnit.gov.py/web/e-kuatia/
- **Documentación**: https://ekuatia.set.gov.py/portal/

## 🙏 Créditos

- **Generador XML**: [Marcos Jara](https://github.com/marcosjara/facturacionelectronicapy-xmlgen)
- **Implementación Python**: Sistema integrado para firma, envío y KuDE

## 📄 Licencia

MIT License - Uso libre comercial y no comercial

---

**Versión del Sistema**: 1.0.0  
**Manual Técnico**: v150  
**Última actualización**: Mayo 2026  
**Notas Técnicas**: Incluye hasta NT-027
