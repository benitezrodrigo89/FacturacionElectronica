"""Modelos Pydantic para la API de integración."""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import List, Optional
from datetime import datetime
from enum import IntEnum


class TipoIVA(IntEnum):
    EXENTO = 0
    IVA_5 = 5
    IVA_10 = 10


class FormaPago(IntEnum):
    EFECTIVO = 1
    CHEQUE = 2
    TARJETA_CREDITO = 3
    TARJETA_DEBITO = 4
    TRANSFERENCIA = 5
    GIRO = 6
    BILLETERA_ELECTRONICA = 7
    VALE = 9
    OTRO = 99


class ItemRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "descripcion": "Servicio de consultoría",
        "cantidad": 1,
        "precio_unitario": 500000,
        "iva": 10,
        "codigo": "SRV-001",
        "unidad_medida": 77,
    }})
    descripcion: str = Field(min_length=1)
    cantidad: float = Field(gt=0)
    precio_unitario: int = Field(gt=0, description="Precio unitario en guaraníes (PYG)")
    iva: TipoIVA = TipoIVA.IVA_10
    codigo: Optional[str] = None
    unidad_medida: int = Field(default=77, description="Código de unidad de medida SIFEN (77=unidad)")


class ReceptorRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {
            "summary": "Contribuyente con RUC",
            "value": {
                "contribuyente": True,
                "ruc": "80069563-1",
                "razon_social": "EMPRESA CLIENTE S.A.",
                "email": "facturacion@cliente.com",
                "telefono": "0981123456",
            },
        },
        {
            "summary": "Persona física con cédula",
            "value": {
                "contribuyente": False,
                "documento_tipo": 1,
                "documento_numero": "1234567",
                "razon_social": "JUAN PÉREZ",
            },
        },
        {
            "summary": "Venta innominada (público general)",
            "value": {
                "contribuyente": False,
                "documento_tipo": 5,
                "razon_social": "Sin Nombre",
            },
        },
    ]})
    contribuyente: bool = Field(
        default=True,
        description="True si el receptor tiene RUC (contribuyente). False si es persona física o innominado.",
    )
    ruc: Optional[str] = Field(
        default=None,
        description="RUC con dígito verificador, ej: 1234567-8. Requerido cuando contribuyente=True.",
    )
    documento_tipo: Optional[int] = Field(
        default=None,
        description=(
            "Tipo de documento del receptor — requerido cuando contribuyente=False. "
            "1=Cédula paraguaya, 2=Pasaporte, 3=Cédula extranjera, "
            "4=Carnet de residencia, 5=Innominado (venta al público sin identificación), "
            "6=Tarjeta Diplomática, 9=No especificado"
        ),
    )
    documento_numero: Optional[str] = Field(
        default=None,
        description="Número del documento. No requerido cuando documento_tipo=5 (innominado).",
    )
    razon_social: str = Field(
        description="Razón social o nombre del receptor. Para innominado (tipo 5) se usa 'Sin Nombre'.",
    )
    direccion: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None

    @model_validator(mode='after')
    def _validar(self):
        if self.contribuyente:
            if not self.ruc:
                raise ValueError("ruc es requerido cuando contribuyente=True")
        else:
            if self.documento_tipo is None:
                raise ValueError("documento_tipo es requerido cuando contribuyente=False")
            if self.documento_tipo != 5 and not self.documento_numero:
                raise ValueError(
                    "documento_numero es requerido cuando contribuyente=False y documento_tipo != 5 (innominado)"
                )
        return self

    def id_para_bd(self) -> str:
        """Identificador del receptor para guardar en la columna ruc_receptor de BD."""
        if self.contribuyente:
            return self.ruc
        return self.documento_numero or "0"

    def build_cliente_block(self) -> dict:
        """Bloque 'cliente' para el generador XML de SIFEN."""
        base = {
            "direccion": self.direccion or "Sin especificar",
            "numeroCasa": "0",
            "departamento": 1,
            "departamentoDescripcion": "ASUNCION",
            "distrito": 1,
            "distritoDescripcion": "ASUNCION (DISTRITO)",
            "ciudad": 1,
            "ciudadDescripcion": "ASUNCION (DISTRITO)",
            "pais": "PRY",
            "paisDescripcion": "Paraguay",
            "telefono": self.telefono or "",
            "email": self.email or "",
        }
        if self.contribuyente:
            ruc = self.ruc.strip()
            doc_numero = ruc.split('-')[0] if '-' in ruc else ruc
            base.update({
                "contribuyente": True,
                "ruc": ruc,
                "razonSocial": self.razon_social,
                "tipoOperacion": 1,
                "tipoContribuyente": 2,
                "documentoTipo": 1,
                "documentoNumero": doc_numero,
            })
        else:
            doc_tipo = self.documento_tipo
            doc_numero = "0" if doc_tipo == 5 else self.documento_numero
            razon_social = "Sin Nombre" if doc_tipo == 5 else self.razon_social
            base.update({
                "contribuyente": False,
                "documentoTipo": doc_tipo,
                "documentoNumero": doc_numero,
                "razonSocial": razon_social,
                "tipoOperacion": 2,
            })
        return base

    def build_usuario_block(self) -> dict:
        """Bloque 'usuario' (gRespDE) para el generador XML de SIFEN."""
        if self.contribuyente:
            ruc = self.ruc.strip()
            doc_numero = ruc.split('-')[0] if '-' in ruc else ruc
            return {"documentoTipo": 1, "documentoNumero": doc_numero, "nombre": self.razon_social, "cargo": "Cliente"}
        doc_tipo = self.documento_tipo
        doc_numero = "0" if doc_tipo == 5 else self.documento_numero
        nombre = "Sin Nombre" if doc_tipo == 5 else self.razon_social
        # gRespDE no acepta tipo 5 (Innominado) — usar 9 (No especificado) como fallback
        tipo_usuario = 9 if doc_tipo == 5 else doc_tipo
        bloque = {"documentoTipo": tipo_usuario, "documentoNumero": doc_numero, "nombre": nombre, "cargo": "Cliente"}
        if tipo_usuario == 9:
            bloque["documentoTipoDescripcion"] = "No especificado"
        return bloque


class CuotaRequest(BaseModel):
    moneda: str = Field(default="PYG", description="Código de moneda, ej: PYG")
    monto: int = Field(gt=0, description="Monto de la cuota en la moneda indicada")
    vencimiento: str = Field(description="Fecha de vencimiento, formato YYYY-MM-DD")


class CreditoRequest(BaseModel):
    tipo: int = Field(description="1=Plazo, 2=Cuota")
    plazo: Optional[str] = Field(default=None, description="Descripción del plazo — requerido cuando tipo=1, ej: '30 días'")
    cuotas: Optional[int] = Field(default=None, description="Cantidad de cuotas — requerido cuando tipo=2")
    info_cuotas: Optional[List[CuotaRequest]] = Field(default=None, description="Detalle de cuotas — opcional cuando tipo=2")


class EntregaRequest(BaseModel):
    forma_pago: FormaPago = Field(description="Forma de pago de esta entrega")
    monto: int = Field(gt=0, description="Monto de esta entrega en guaraníes")


class CondicionPagoRequest(BaseModel):
    tipo: int = Field(default=1, description="1=Contado, 2=Crédito")
    forma_pago: FormaPago = Field(default=FormaPago.EFECTIVO, description="Forma de pago principal (ignorado si se usa 'entregas')")
    monto: Optional[int] = Field(default=None, description="Monto total de la entrega. Si se omite se calcula del total de ítems. Ignorado si se usa 'entregas'.")
    entregas: Optional[List[EntregaRequest]] = Field(
        default=None,
        description="Lista de formas de pago con sus montos. Usar cuando el pago es mixto (ej: parte efectivo, parte transferencia). Si se especifica, reemplaza 'forma_pago' y 'monto'.",
    )
    credito: Optional[CreditoRequest] = Field(default=None, description="Detalle del crédito — requerido cuando tipo=2")


class FacturaRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {
            "summary": "Factura contado a contribuyente",
            "value": {
                "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A.", "email": "facturacion@cliente.com"},
                "items": [
                    {"descripcion": "Servicio de consultoría", "cantidad": 1, "precio_unitario": 500000, "iva": 10},
                    {"descripcion": "Licencia de software", "cantidad": 2, "precio_unitario": 150000, "iva": 10},
                ],
                "condicion_pago": {"tipo": 1, "forma_pago": 1},
            },
        },
        {
            "summary": "Factura crédito a contribuyente",
            "value": {
                "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A."},
                "items": [{"descripcion": "Producto A", "cantidad": 5, "precio_unitario": 100000, "iva": 10}],
                "condicion_pago": {
                    "tipo": 2,
                    "credito": {"tipo": 1, "plazo": "30 días"},
                },
            },
        },
        {
            "summary": "Factura contado a persona física",
            "value": {
                "receptor": {"contribuyente": False, "documento_tipo": 1, "documento_numero": "1234567", "razon_social": "JUAN PÉREZ"},
                "items": [{"descripcion": "Producto B", "cantidad": 1, "precio_unitario": 80000, "iva": 10}],
                "condicion_pago": {"tipo": 1, "forma_pago": 5},
            },
        },
        {
            "summary": "Factura innominada (venta al público)",
            "value": {
                "receptor": {"contribuyente": False, "documento_tipo": 5, "razon_social": "Sin Nombre"},
                "items": [{"descripcion": "Producto C", "cantidad": 3, "precio_unitario": 20000, "iva": 10}],
                "condicion_pago": {"tipo": 1, "forma_pago": 1},
            },
        },
        {
            "summary": "Contado mixto: efectivo + transferencia",
            "value": {
                "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A."},
                "items": [{"descripcion": "Servicio de mantenimiento", "cantidad": 1, "precio_unitario": 1000000, "iva": 10}],
                "condicion_pago": {
                    "tipo": 1,
                    "entregas": [
                        {"forma_pago": 1, "monto": 400000},
                        {"forma_pago": 5, "monto": 700000},
                    ],
                },
            },
        },
        {
            "summary": "Contado mixto: tarjeta + efectivo",
            "value": {
                "receptor": {"contribuyente": False, "documento_tipo": 1, "documento_numero": "1234567", "razon_social": "JUAN PÉREZ"},
                "items": [{"descripcion": "Producto D", "cantidad": 2, "precio_unitario": 300000, "iva": 10}],
                "condicion_pago": {
                    "tipo": 1,
                    "entregas": [
                        {"forma_pago": 3, "monto": 500000},
                        {"forma_pago": 1, "monto": 160000},
                    ],
                },
            },
        },
        {
            "summary": "Crédito en cuotas con detalle",
            "value": {
                "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A."},
                "items": [{"descripcion": "Equipo de computación", "cantidad": 1, "precio_unitario": 3300000, "iva": 10}],
                "condicion_pago": {
                    "tipo": 2,
                    "credito": {
                        "tipo": 2,
                        "cuotas": 3,
                        "info_cuotas": [
                            {"moneda": "PYG", "monto": 1210000, "vencimiento": "2026-12-26"},
                            {"moneda": "PYG", "monto": 1210000, "vencimiento": "2027-01-26"},
                            {"moneda": "PYG", "monto": 1210000, "vencimiento": "2027-02-26"},
                        ],
                    },
                },
            },
        },
    ]})
    receptor: ReceptorRequest
    items: List[ItemRequest] = Field(min_length=1)
    condicion_pago: CondicionPagoRequest = CondicionPagoRequest()
    descripcion: Optional[str] = Field(default=None, description="Descripción de la operación")
    numero_doc: Optional[int] = Field(
        default=None,
        ge=1,
        description="Número de factura asignado por el sistema externo. Si se omite, se usa el próximo número disponible en la BD.",
    )
    origen: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Identificador del sistema que emite el documento, ej: 'genexus', 'erp', 'pos'. Si se omite se registra como 'api'.",
    )


class CancelacionRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "motivo": "Error en datos del receptor",
    }})
    motivo: str = Field(min_length=5, description="Motivo de la cancelación")


class InutilizacionRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "tipo_documento": 1,
        "numero_desde": 5,
        "numero_hasta": 7,
        "motivo": "Números generados por error durante pruebas",
    }})
    tipo_documento: int = Field(default=1, description="1=FE, 5=NCE, 6=NDE, 7=NRE")
    numero_desde:   int = Field(gt=0, description="Primer número a inutilizar")
    numero_hasta:   int = Field(gt=0, description="Último número a inutilizar (puede ser igual a numero_desde)")
    motivo:         str = Field(min_length=5, description="Motivo de la inutilización")


class ConformidadRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "tipo_conformidad": 1,
        "fecha_recepcion": "2026-11-26T10:00:00",
    }})
    tipo_conformidad: int = Field(
        default=1,
        ge=1, le=2,
        description="1=Conformidad total, 2=Conformidad parcial",
    )
    fecha_recepcion: str = Field(
        description="Fecha y hora de recepción en formato ISO 8601, ej: 2026-09-18T10:00:00"
    )


class MotivoNCE(IntEnum):
    DEVOLUCION_Y_AJUSTE  = 1
    DEVOLUCION           = 2
    DESCUENTO            = 3
    BONIFICACION         = 4
    CREDITO_INCOBRABLE   = 5
    RECUPERO_COSTO       = 6
    RECUPERO_GASTO       = 7
    OTROS                = 8


MotivoNDE = MotivoNCE  # NDE comparte los mismos códigos de motivo


class DocumentoReferencia(BaseModel):
    cdc:             str
    timbrado:        Optional[str] = None
    establecimiento: Optional[str] = None
    punto:           Optional[str] = None
    numero:          Optional[int] = None
    fecha:           Optional[str] = Field(default=None, description="Formato YYYY-MM-DD")
    formato:         int = Field(
        default=1,
        description="Formato del documento referenciado: 1=Electrónico, 2=Impreso, 3=Constancia Electrónica",
    )


class NotaCreditoRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [
        {
            "summary": "NCE — devolución con acreditación en efectivo",
            "value": {
                "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A."},
                "items": [{"descripcion": "Devolución parcial — Servicio de consultoría", "cantidad": 1, "precio_unitario": 100000, "iva": 10}],
                "condicion_pago": {"tipo": 1, "forma_pago": 1},
                "motivo": 2,
                "documento_referencia": {"cdc": "01800695631001001000000012026112600000000001234561", "formato": 1},
            },
        },
        {
            "summary": "NCE — descuento sin referencia a factura",
            "value": {
                "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A."},
                "items": [{"descripcion": "Descuento comercial acordado", "cantidad": 1, "precio_unitario": 50000, "iva": 10}],
                "condicion_pago": {"tipo": 1, "forma_pago": 5},
                "motivo": 3,
            },
        },
    ]})
    receptor:              ReceptorRequest
    items:                 List[ItemRequest] = Field(min_length=1)
    condicion_pago:        CondicionPagoRequest  = CondicionPagoRequest()
    motivo:                MotivoNCE             = MotivoNCE.OTROS
    documento_referencia:  Optional[DocumentoReferencia] = Field(
        default=None, description="Factura original que se está acreditando"
    )
    descripcion:           Optional[str] = None


# ── Nota de Remisión ──────────────────────────────────────────────────────────

class MotivoRemision(IntEnum):
    TRASLADO_ENTRE_LOCALES  = 1
    TRASLADO_A_TERCEROS     = 2
    EXPORTACION             = 3
    CONSIGNACION            = 4
    DEVOLUCION              = 5
    OTROS                   = 9


class ItemRemisionRequest(BaseModel):
    descripcion:    str
    cantidad:       float = Field(gt=0)
    codigo:         Optional[str] = None
    unidad_medida:  int   = 77
    precio_unitario: Optional[int] = Field(
        default=None,
        description="Precio unitario en PYG. Opcional para remisión sin valor comercial."
    )


class VehiculoRequest(BaseModel):
    matricula:  str
    marca:      Optional[str] = None


class TransportistaRequest(BaseModel):
    nombre:           str
    documento_numero: str
    vehiculo:         Optional[VehiculoRequest] = None


class NotaRemisionRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A."},
        "items": [{"descripcion": "Mercadería A", "cantidad": 10, "unidad_medida": 77}],
        "motivo": 1,
        "direccion_origen": "Av. España 123, Asunción",
        "direccion_destino": "Ruta 2 Km 10, San Lorenzo",
        "transportista": {
            "nombre": "CARLOS TRANSPORTES",
            "documento_numero": "9876543",
            "vehiculo": {"matricula": "ABC-123", "marca": "Mercedes"},
        },
    }})
    receptor:           ReceptorRequest
    items:              List[ItemRemisionRequest] = Field(min_length=1)
    motivo:             MotivoRemision = MotivoRemision.OTROS
    transportista:      Optional[TransportistaRequest] = None
    direccion_origen:   Optional[str] = Field(default=None, description="Dirección de origen del traslado")
    direccion_destino:  Optional[str] = Field(default=None, description="Dirección de destino del traslado")
    descripcion:        Optional[str] = None


class NotaDebitoRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "receptor": {"contribuyente": True, "ruc": "80069563-1", "razon_social": "EMPRESA CLIENTE S.A."},
        "items": [{"descripcion": "Ajuste de precio — Servicio adicional", "cantidad": 1, "precio_unitario": 50000, "iva": 10}],
        "condicion_pago": {"tipo": 1, "forma_pago": 1},
        "motivo": 8,
        "documento_referencia": {"cdc": "01800695631001001000000012026112600000000001234561", "formato": 1},
    }})
    receptor:             ReceptorRequest
    items:                List[ItemRequest] = Field(min_length=1)
    condicion_pago:       CondicionPagoRequest  = CondicionPagoRequest()
    motivo:               MotivoNDE             = MotivoNDE.OTROS
    documento_referencia: Optional[DocumentoReferencia] = Field(
        default=None, description="Factura original que origina la nota de débito"
    )
    descripcion:          Optional[str] = None


# ── Autofactura ───────────────────────────────────────────────────────────────

class VendedorRequest(BaseModel):
    nombre:           str  = Field(description="Nombre completo del vendedor (persona física)")
    documento_tipo:   int  = Field(default=1, description="Tipo de documento: 1=CI, 5=Pasaporte, 6=Cédula Extranjero")
    documento_numero: str  = Field(description="Número de documento del vendedor (solo dígitos)")
    tipo_vendedor:    int  = Field(default=1, description="1=No contribuyente, 2=Extranjero")
    direccion:        str  = Field(default="Sin especificar")
    numero_casa:      str  = Field(default="0")
    departamento:     int  = Field(default=1)
    distrito:         int  = Field(default=1)
    ciudad:           int  = Field(default=1)


class ConstanciaRequest(BaseModel):
    constancia_numero:  str = Field(description="Número de la constancia (11 dígitos)")
    constancia_control: str = Field(description="Número de control de la constancia (8 caracteres)")
    lugar:              str = Field(default="Asunción", description="Lugar de la transacción")
    departamento:       int = Field(default=1)
    distrito:           int = Field(default=1)
    ciudad:             int = Field(default=1)


class AutofacturaRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "vendedor": {
            "nombre": "JUAN PÉREZ",
            "documento_tipo": 1,
            "documento_numero": "1234567",
            "tipo_vendedor": 1,
            "direccion": "Barrio San Pablo, Asunción",
        },
        "items": [{"descripcion": "Compra de materiales de construcción", "cantidad": 1, "precio_unitario": 200000, "iva": 10}],
        "condicion_pago": {"tipo": 1, "forma_pago": 1},
        "constancia": {
            "constancia_numero": "12345678901",
            "constancia_control": "ABC12345",
            "lugar": "Asunción",
        },
    }})
    vendedor:      VendedorRequest
    items:         List[ItemRequest] = Field(min_length=1)
    condicion_pago: CondicionPagoRequest = CondicionPagoRequest()
    constancia:    ConstanciaRequest
    descripcion:   Optional[str] = None


class FacturaResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {
        "cdc": "01800695631001001000000012026112600000000001234561",
        "numero_doc": 1,
        "estado": "aprobado",
        "codigo_sifen": "0422",
        "descripcion_sifen": "CDC Autorizado",
        "protocolo_autorizacion": "12345678901234567",
        "kude_url": "/api/v1/facturas/01800695631001001000000012026112600000000001234561/kude",
        "fecha_envio": "2026-11-26T10:30:00",
    }})
    cdc: str
    numero_doc: int
    estado: str
    codigo_sifen: Optional[str]
    descripcion_sifen: str
    protocolo_autorizacion: Optional[str]
    kude_url: str
    fecha_envio: Optional[datetime]
