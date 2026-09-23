"""Modelos Pydantic para la API de integración."""
from pydantic import BaseModel, Field
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
    ruc: str = Field(description="RUC con dígito verificador, ej: 1234567-8")
    razon_social: str
    direccion: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None


class CondicionPagoRequest(BaseModel):
    tipo: int = Field(default=1, description="1=Contado, 2=Crédito")
    forma_pago: FormaPago = FormaPago.EFECTIVO
    monto: Optional[int] = Field(default=None, description="Monto. Si se omite se calcula del total de ítems.")


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


class DocumentoReferencia(BaseModel):
    cdc:             str
    timbrado:        Optional[str] = None
    establecimiento: Optional[str] = None
    punto:           Optional[str] = None
    numero:          Optional[int] = None
    fecha:           Optional[str] = Field(default=None, description="Formato YYYY-MM-DD")


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


class FacturaResponse(BaseModel):
    cdc: str
    numero_doc: int
    estado: str
    codigo_sifen: Optional[str]
    descripcion_sifen: str
    protocolo_autorizacion: Optional[str]
    kude_url: str
    fecha_envio: Optional[datetime]
