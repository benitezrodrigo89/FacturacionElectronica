"""Modelos Pydantic para la API de integración."""
from pydantic import BaseModel, Field, model_validator
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
    descripcion: str = Field(min_length=1)
    cantidad: float = Field(gt=0)
    precio_unitario: int = Field(gt=0, description="Precio unitario en guaraníes (PYG)")
    iva: TipoIVA = TipoIVA.IVA_10
    codigo: Optional[str] = None
    unidad_medida: int = Field(default=77, description="Código de unidad de medida SIFEN (77=unidad)")


class ReceptorRequest(BaseModel):
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
        return {"documentoTipo": doc_tipo, "documentoNumero": doc_numero, "nombre": nombre, "cargo": "Cliente"}


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
    receptor: ReceptorRequest
    items: List[ItemRequest] = Field(min_length=1)
    condicion_pago: CondicionPagoRequest = CondicionPagoRequest()
    descripcion: Optional[str] = Field(default=None, description="Descripción de la operación")
    numero_doc: Optional[int] = Field(
        default=None,
        ge=1,
        description="Número de factura asignado por el sistema externo. Si se omite, se usa el próximo número disponible en la BD.",
    )


class CancelacionRequest(BaseModel):
    motivo: str = Field(min_length=5, description="Motivo de la cancelación")


class InutilizacionRequest(BaseModel):
    tipo_documento: int = Field(default=1, description="1=FE, 5=NCE, 6=NDE, 7=NRE")
    numero_desde:   int = Field(gt=0, description="Primer número a inutilizar")
    numero_hasta:   int = Field(gt=0, description="Último número a inutilizar (puede ser igual a numero_desde)")
    motivo:         str = Field(min_length=5, description="Motivo de la inutilización")


class ConformidadRequest(BaseModel):
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
    receptor:           ReceptorRequest
    items:              List[ItemRemisionRequest] = Field(min_length=1)
    motivo:             MotivoRemision = MotivoRemision.OTROS
    transportista:      Optional[TransportistaRequest] = None
    direccion_origen:   Optional[str] = Field(default=None, description="Dirección de origen del traslado")
    direccion_destino:  Optional[str] = Field(default=None, description="Dirección de destino del traslado")
    descripcion:        Optional[str] = None


class NotaDebitoRequest(BaseModel):
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
    vendedor:      VendedorRequest
    items:         List[ItemRequest] = Field(min_length=1)
    condicion_pago: CondicionPagoRequest = CondicionPagoRequest()
    constancia:    ConstanciaRequest
    descripcion:   Optional[str] = None


class FacturaResponse(BaseModel):
    cdc: str
    numero_doc: int
    estado: str
    codigo_sifen: Optional[str]
    descripcion_sifen: str
    protocolo_autorizacion: Optional[str]
    kude_url: str
    fecha_envio: Optional[datetime]
