"""
Constantes del sistema SIFEN - Manual Técnico v150
"""

# Versión del esquema XSD
SIFEN_XSD_VERSION = "150"

# Ambientes SIFEN
AMBIENTE_TEST = "test"
AMBIENTE_PRODUCCION = "prod"

# URLs de los servicios web
URLS = {
    AMBIENTE_TEST: {
        "base":          "https://sifen-test.set.gov.py",
        "recibe":        "https://sifen-test.set.gov.py/de/ws/sync/recibe.wsdl",
        "recibe_lote":   "https://sifen-test.set.gov.py/de/ws/async/recibe-lote.wsdl",
        "consulta_lote": "https://sifen-test.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
        "consulta_de":   "https://sifen-test.set.gov.py/de/ws/consultas/consulta.wsdl",
        "consulta_ruc":  "https://sifen-test.set.gov.py/de/ws/consultas/consulta-ruc.wsdl",
        "recibe_evento": "https://sifen-test.set.gov.py/de/ws/async/recibe-evento.wsdl",
        "qr":            "https://ekuatia.set.gov.py/consultas-test/qr",
    },
    AMBIENTE_PRODUCCION: {
        "base":          "https://sifen.set.gov.py",
        "recibe":        "https://sifen.set.gov.py/de/ws/sync/recibe.wsdl",
        "recibe_lote":   "https://sifen.set.gov.py/de/ws/async/recibe-lote.wsdl",
        "consulta_lote": "https://sifen.set.gov.py/de/ws/consultas/consulta-lote.wsdl",
        "consulta_de":   "https://sifen.set.gov.py/de/ws/consultas/consulta.wsdl",
        "consulta_ruc":  "https://sifen.set.gov.py/de/ws/consultas/consulta-ruc.wsdl",
        "recibe_evento": "https://sifen.set.gov.py/de/ws/async/recibe-evento.wsdl",
        "qr":            "https://ekuatia.set.gov.py/consultas/qr",
    }
}

# Namespace XML
NAMESPACES = {
    'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
    'xsd': 'http://ekuatia.set.gov.py/sifen/xsd',
    'ds': 'http://www.w3.org/2000/09/xmldsig#'
}

# Tipos de Documentos Electrónicos (C002)
TIPO_DOCUMENTO = {
    'FACTURA_ELECTRONICA': 1,
    'FACTURA_ELECTRONICA_EXPORTACION': 1,
    'FACTURA_ELECTRONICA_IMPORTACION': 1,
    'AUTOFACTURA_ELECTRONICA': 4,
    'NOTA_CREDITO_ELECTRONICA': 5,
    'NOTA_DEBITO_ELECTRONICA': 6,
    'NOTA_REMISION_ELECTRONICA': 7
}

# Tipos de Transacción (D011)
TIPO_TRANSACCION = {
    'VENTA_MERCADERIA': 1,
    'PRESTACION_SERVICIOS': 2,
    'MIXTO': 3,
    'VENTA_ACTIVO_FIJO': 4,
    'VENTA_DIVISAS': 5,
    'COMPRA_DIVISAS': 6,
    'PROMOCION_MUESTRAS': 7,
    'DONACION': 8,
    'ANTICIPO': 9,
    'COMPRA_PRODUCTOS': 10,
    'COMPRA_SERVICIOS': 11,
    'VENTA_CREDITO_FISCAL': 12,
    'MUESTRAS_MEDICAS': 13
}

# Tipos de Operación (D202)
TIPO_OPERACION = {
    'B2B': 1,  # Business to Business
    'B2C': 2,  # Business to Consumer
    'B2G': 3,  # Business to Government
    'B2F': 4   # Business to Final Consumer
}

# Naturaleza del Receptor (D201)
NATURALEZA_RECEPTOR = {
    'CONTRIBUYENTE': 1,
    'NO_CONTRIBUYENTE': 2
}

# Tipos de Documento de Identidad (D208)
TIPO_DOCUMENTO_IDENTIDAD = {
    'CEDULA_PARAGUAYA': 1,
    'PASAPORTE': 2,
    'CEDULA_EXTRANJERA': 3,
    'CARNET_RESIDENCIA': 4,
    'INNOMINADO': 5,
    'TARJETA_DIPLOMATICA': 6,
    'OTRO': 9
}

# Tipos de Contribuyente (D212)
TIPO_CONTRIBUYENTE = {
    'PERSONA_FISICA': 1,
    'PERSONA_JURIDICA': 2
}

# Condición de la Operación (E605)
CONDICION_OPERACION = {
    'CONTADO': 1,
    'CREDITO': 2
}

# Tipos de Pago (E608)
TIPO_PAGO = {
    'EFECTIVO': 1,
    'CHEQUE': 2,
    'TARJETA_CREDITO': 3,
    'TARJETA_DEBITO': 4,
    'TRANSFERENCIA': 5,
    'GIRO': 6,
    'BILLETERA_ELECTRONICA': 7,
    'TARJETA_EMPRESARIAL': 8,
    'VALE': 9,
    'OTROS': 99
}

# Monedas (E606)
MONEDAS = {
    'PYG': 'PYG',  # Guaraníes
    'USD': 'USD',  # Dólares americanos
    'EUR': 'EUR',  # Euros
    'BRL': 'BRL',  # Reales
    'ARS': 'ARS'   # Pesos argentinos
}

# Códigos de Afectación del IVA (E733)
AFECTACION_IVA = {
    'GRAVADO_IVA': 1,
    'EXONERADO': 2,
    'EXENTO': 3,
    'GRAVADO_PARCIAL': 4
}

# Tasas de IVA (E734)
TASAS_IVA = {
    10: 10,  # 10%
    5: 5,    # 5%
    0: 0     # Exento
}

# Tipos de Eventos
TIPO_EVENTO = {
    'CANCELACION': 1,
    'INUTILIZACION': 2,
    'CONFORMIDAD': 3,
    'DISCONFORMIDAD': 4,
    'DESCONOCIMIENTO': 5,
    'NOTIFICACION_RECEPCION': 6,
    'NOMINACION_FE': 7
}

# Códigos de Respuesta de Lotes
CODIGOS_RESPUESTA_LOTE = {
    '0300': 'Lote recibido con éxito',
    '0301': 'Lote no encolado para procesamiento',
    '0360': 'No existe número de lote consultado',
    '0361': 'Lote en procesamiento',
    '0362': 'Procesamiento de lote concluido',
    '0364': 'Consulta extemporánea de Lote'
}

# Códigos de Respuesta de DE
CODIGOS_RESPUESTA_DE = {
    '0420': 'DE no existe o rechazado',
    '0422': 'DE aprobado'
}

# Límites del Sistema
LIMITE_DOCS_POR_LOTE = 50
LIMITE_ITEMS_POR_DOC = 9999
TAMANO_MAX_LOTE_KB = 1000

# Validaciones importantes (Notas Técnicas)
MONTO_INNOMINADO_MAX = 35000000  # 35 millones de guaraníes (NT-021)

# Formato de fechas
FORMATO_FECHA = '%Y-%m-%d'
FORMATO_FECHA_HORA = '%Y-%m-%dT%H:%M:%S'
FORMATO_FECHA_HORA_KZ = '%Y-%m-%dT%H:%M:%S-04:00'  # Paraguay UTC-4

# Códigos de error comunes (solo algunos ejemplos)
CODIGOS_ERROR = {
    '1103': 'Número de timbrado no vigente',
    '1251': 'RUC inhabilitado para facturación electrónica',
    '1321': 'Tipo de documento incorrecto para monto >= 35M',
    '1862': 'Descuento global no coincide',
    '2364': 'Error en cálculo del descuento total',
    '2365': 'Error en cálculo del total general',
    '2439': 'CDC asociado no corresponde al emisor',
    '2440': 'Timbrado electrónico en documento impreso',
    '2441': 'CDC asociado no corresponde al receptor',
    '2442': 'Receptor en CDC no coincide con nominación',
    '2501': 'CSC no vigente'
}

# Regímenes tributarios
REGIMENES_TRIBUTARIOS = {
    '8': 'IVA General'
}
