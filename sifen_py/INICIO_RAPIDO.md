# 🚀 Inicio Rápido - SIFEN Paraguay

Esta guía te llevará paso a paso para emitir tu primera factura electrónica en **menos de 10 minutos**.

## ✅ Paso 1: Requisitos Previos

### Instalar Node.js
```bash
# Verificar si está instalado
node --version
npm --version

# Si no está instalado:
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install nodejs npm

# macOS
brew install node

# Windows
# Descargar desde https://nodejs.org/
```

### Instalar Python 3.8+
```bash
python3 --version
# Debe ser 3.8 o superior
```

## 📦 Paso 2: Instalar Dependencias

### Dependencias Node.js (Generador XML)
```bash
cd FacturacionElectronica/facturacionelectronicapy-xmlgen-main
npm install
```

### Dependencias Python (Firma y Envío)
```bash
cd ../../sifen_py
pip install -r requirements.txt
```

## 🔐 Paso 3: Preparar Certificado Digital

1. **Obtener certificado** de una PSC habilitada:
   - ACRaiz (https://www.acraiz.gov.py/)
   - Otra PSC autorizada

2. **Colocar el certificado** en una ubicación segura:
   ```bash
   mkdir -p ~/certificados_sifen
   # Copiar tu certificado.pfx aquí
   ```

3. **Anotar**:
   - Ruta del certificado: `/home/usuario/certificados_sifen/micertificado.pfx`
   - Contraseña del certificado
   - RUC del emisor
   - Código de Seguridad CSC (otorgado por la SET)

## ⚙️ Paso 4: Configurar el Sistema

Crear archivo `mi_config.py`:

```python
from sifen_py.core.config import SifenConfig

# AMBIENTE DE PRUEBAS
config = SifenConfig(
    ambiente='test',  # Cambiar a 'prod' para producción

    # Datos del emisor
    ruc='80069563-1',  # TU RUC
    razon_social='MI EMPRESA S.A.',
    nombre_fantasia='MI EMPRESA',

    # Certificado digital
    certificado_path='/home/usuario/certificados_sifen/micertificado.pfx',
    certificado_password='MI_PASSWORD_SECRETO',

    # Código de seguridad
    csc='298398',  # TU CSC de la SET

    # Establecimiento
    establecimiento='001',
    punto_expedicion='001',

    # Datos opcionales
    actividad_economica='1254',
    direccion='Mi dirección comercial',
    departamento=11,  # Ver tabla de departamentos
    distrito=1,
    ciudad=1,
    telefono='021-123456',
    email='facturacion@miempresa.com'
)
```

## 🎯 Paso 5: Primera Factura

Crear archivo `mi_primera_factura.py`:

```python
from mi_config import config
from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.services.signer import XMLSigner
from datetime import datetime

# 1. Preparar datos de la factura
factura = {
    "tipoDocumento": 1,  # Factura Electrónica
    "establecimiento": "001",
    "punto": "001",
    "numero": "0000001",  # Tu numeración
    "fecha": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
    "tipoTransaccion": 1,  # Venta de mercadería
    "moneda": "PYG",

    # Cliente
    "cliente": {
        "contribuyente": True,
        "ruc": "80000001-7",  # RUC del cliente
        "razonSocial": "CLIENTE EJEMPLO S.A.",
        "tipoOperacion": 1,  # B2B
        "direccion": "Asunción",
        "departamento": 11,
        "distrito": 1,
        "ciudad": 1,
        "pais": "PRY",
        "paisDescripcion": "Paraguay"
    },

    # Condición: CONTADO
    "condicion": {
        "tipo": 1,  # Contado
        "entregas": [{
            "tipo": 1,  # Efectivo
            "monto": "110000",  # Total con IVA
            "moneda": "PYG"
        }]
    },

    # Productos/Servicios
    "items": [{
        "codigo": "PROD-001",
        "descripcion": "Producto de prueba",
        "cantidad": 1,
        "precioUnitario": 100000,  # Precio sin IVA
        "ivaTipo": 1,  # Gravado IVA
        "ivaProporcion": 100,
        "iva": 10,  # 10%
        "unidadMedida": 77  # Unidad
    }]
}

# 2. Generar XML
print("Generando XML...")
generador = XMLGeneratorWrapper(config)
xml = generador.generar_xml_de(factura)
print(f"✓ XML generado ({len(xml)} caracteres)")

# 3. Firmar XML
print("Firmando XML...")
firmador = XMLSigner(config)
xml_firmado = firmador.firmar_xml(xml)
print(f"✓ XML firmado")

# 4. Guardar
with open("factura_firmada.xml", "w") as f:
    f.write(xml_firmado)
print("✓ Guardado en: factura_firmada.xml")

print("\n✅ ¡Primera factura generada y firmada!")
print("   Siguiente paso: Enviar a SIFEN")
```

Ejecutar:
```bash
python mi_primera_factura.py
```

## 📤 Paso 6: Enviar a SIFEN

*Próximamente en esta guía - Cliente SOAP en desarrollo*

Por ahora, el XML firmado se puede:
1. Guardar para envío posterior
2. Enviar manualmente via el portal de SIFEN
3. Usar con el cliente SOAP cuando esté completo

## 🎓 Siguiente Nivel

### Ejemplos adicionales:
```bash
# Ver ejemplos incluidos
ls examples/

# Factura a crédito
python examples/ejemplo_factura_credito.py

# Nota de crédito
python examples/ejemplo_nota_credito.py

# Cancelación
python examples/ejemplo_cancelacion.py
```

### Integración con tu sistema:
```python
# En tu sistema existente
from sifen_py import SifenClient

cliente = SifenClient(config)

# Método simple todo-en-uno
resultado = cliente.emitir_factura(tus_datos)

# Acceder al CDC
cdc = resultado['cdc']

# Acceder al PDF
pdf_path = resultado['pdf_path']
```

## 📊 Tipos de Documentos Soportados

| Código | Tipo | Descripción |
|--------|------|-------------|
| 1 | FE | Factura Electrónica |
| 4 | AFE | Autofactura Electrónica |
| 5 | NCE | Nota de Crédito Electrónica |
| 6 | NDE | Nota de Débito Electrónica |
| 7 | NRE | Nota de Remisión Electrónica |

## ❓ Problemas Comunes

### Error: "Node.js no encontrado"
```bash
# Verificar PATH
which node
npm --version

# Reinstalar si es necesario
```

### Error: "Certificado no válido"
- Verificar que el archivo .pfx sea correcto
- Verificar la contraseña
- Verificar que el RUC esté en el certificado
- Verificar vigencia del certificado

### Error: "No se encontró el proyecto Node.js"
```bash
# Verificar estructura de carpetas
ls FacturacionElectronica/facturacionelectronicapy-xmlgen-main/

# Debe tener node_modules/
```

## 📞 Soporte

- **Documentación oficial**: https://ekuatia.set.gov.py/portal/
- **Email SET**: facturacionelectronica@dnit.gov.py
- **Issues del proyecto**: [GitHub]

## ✨ ¡Listo!

Ya estás preparado para emitir facturas electrónicas. 

**Recuerda**:
- ✅ Comenzar siempre en **ambiente de pruebas** (`test`)
- ✅ Validar los datos antes de enviar
- ✅ Guardar los XML firmados
- ✅ Consultar el estado después de 10 minutos del envío
- ✅ Generar el KuDE (PDF) solo cuando esté aprobado

---

🇵🇾 **Sistema SIFEN Paraguay** - Manual Técnico v150
