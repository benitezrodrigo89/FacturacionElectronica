# 📋 TODO List - SIFEN Paraguay

## 🔴 Alta Prioridad (Core Functionality)

### Cliente SOAP
- [ ] Implementar cliente SOAP base con zeep
- [ ] Configurar TLS mutuo con certificado
- [ ] Implementar servicio `recibe-lote`
- [ ] Implementar servicio `consulta-lote`
- [ ] Implementar servicio `consulta` (por CDC)
- [ ] Implementar servicio `consulta-ruc`
- [ ] Implementar servicio `recibe-evento`
- [ ] Manejo de errores SOAP
- [ ] Logging de requests/responses
- [ ] Tests unitarios cliente SOAP

### Gestor de Lotes
- [ ] Clase BatchManager
- [ ] Agrupación de hasta 50 DEs
- [ ] Validación: mismo RUC emisor
- [ ] Validación: mismo tipo documento
- [ ] Compresión en ZIP
- [ ] Control de tamaño (max 1000 KB)
- [ ] Estados de lote (0300, 0301, 0361, 0362)
- [ ] Sistema de reintentos
- [ ] Cola de envío
- [ ] Persistencia de estado (opcional)

### Utilidades CDC
- [ ] Generar CDC según algoritmo oficial
- [ ] Cálculo de dígito verificador
- [ ] Validación de CDC
- [ ] Parsing de CDC (extraer componentes)
- [ ] Tests con casos de ejemplo

## 🟡 Media Prioridad (Enhanced Features)

### Generador KuDE (PDF)
- [ ] Layout base con ReportLab
- [ ] Formato FE (Factura Electrónica)
- [ ] Formato NCE (Nota Crédito)
- [ ] Formato NDE (Nota Débito)
- [ ] Formato AFE (Autofactura)
- [ ] Formato NRE (Nota Remisión)
- [ ] Generación de código QR
- [ ] Inserción de QR en PDF
- [ ] Información fiscal completa
- [ ] Logo empresa (opcional)
- [ ] Tests de generación

### Cliente Integrado
- [ ] Clase SifenClient (orquestador)
- [ ] Método `emitir_factura()` todo-en-uno
- [ ] Método `cancelar_factura()`
- [ ] Método `inutilizar_numeracion()`
- [ ] Método `consultar_de()`
- [ ] Método `consultar_lote()`
- [ ] Manejo de estado interno
- [ ] Caché de consultas
- [ ] Rate limiting

### Generador QR
- [ ] Generar QR según especificación SIFEN
- [ ] URL correcta según ambiente
- [ ] Parámetros correctos
- [ ] Formato imagen (PNG)
- [ ] Tamaño configurable
- [ ] Tests de QR

## 🟢 Baja Prioridad (Nice to Have)

### Validaciones Avanzadas
- [ ] Validador de RUC
- [ ] Validador de timbrado
- [ ] Validador de montos (NT-021: innominados)
- [ ] Validador de descuentos globales (NT-001)
- [ ] Validador de compras públicas (NT-026)
- [ ] Suite completa de validaciones

### Testing
- [ ] Tests unitarios core
- [ ] Tests unitarios services
- [ ] Tests de integración
- [ ] Tests end-to-end
- [ ] Mocks para SOAP
- [ ] Coverage > 80%
- [ ] CI/CD con GitHub Actions

### Documentación
- [ ] Docstrings completos
- [ ] Sphinx documentation
- [ ] ReadTheDocs setup
- [ ] Ejemplos adicionales
- [ ] Video tutoriales
- [ ] FAQ extendido

### CLI Tool
- [ ] Comando `sifen init`
- [ ] Comando `sifen generar-factura`
- [ ] Comando `sifen firmar`
- [ ] Comando `sifen enviar`
- [ ] Comando `sifen consultar`
- [ ] Comando `sifen cancelar`
- [ ] Configuración interactiva

### Base de Datos (Opcional)
- [ ] Modelos SQLAlchemy
- [ ] Tabla DEs emitidos
- [ ] Tabla lotes enviados
- [ ] Tabla eventos
- [ ] Historial de consultas
- [ ] Sincronización con SIFEN

### UI Web (Opcional)
- [ ] FastAPI backend
- [ ] React/Vue frontend
- [ ] Dashboard de DEs
- [ ] Formulario de emisión
- [ ] Consulta de estados
- [ ] Descarga de KuDEs

## 🔧 Mejoras y Refactoring

### Performance
- [ ] Caché de certificado
- [ ] Pool de conexiones SOAP
- [ ] Procesamiento asíncrono
- [ ] Queue workers
- [ ] Batch processing optimizado

### Seguridad
- [ ] Encriptación de CSC en config
- [ ] Secure storage de certificados
- [ ] Audit logging
- [ ] Rate limiting por RUC
- [ ] Validación de entrada estricta

### Compatibilidad
- [ ] Soporte Python 3.8-3.12
- [ ] Soporte múltiples OS
- [ ] Docker image
- [ ] Docker Compose para dev
- [ ] Kubernetes manifests

## 📝 Documentación Pendiente

- [ ] Guía de migración desde otros sistemas
- [ ] Comparativa con soluciones existentes
- [ ] Casos de uso por industria
- [ ] Troubleshooting guide completa
- [ ] API Reference completa
- [ ] Changelog detallado

## 🐛 Bugs Conocidos

_(Ninguno por ahora - proyecto en fase inicial)_

## 💡 Ideas Futuras

- [ ] Integración con ERP populares
- [ ] Plugin para WooCommerce/Shopify
- [ ] API REST wrapper
- [ ] Webhooks para eventos
- [ ] Dashboard analytics
- [ ] Reportes mensuales automáticos
- [ ] Sincronización con contabilidad
- [ ] App móvil para consultas

---

**Última actualización**: 2026-05-28  
**Prioridad actual**: Cliente SOAP + Gestor de Lotes
