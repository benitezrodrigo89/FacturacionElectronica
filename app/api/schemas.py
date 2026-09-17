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


class FacturaResponse(BaseModel):
    cdc: str
    numero_doc: int
    estado: str
    codigo_sifen: Optional[str]
    descripcion_sifen: str
    protocolo_autorizacion: Optional[str]
    kude_url: str
    fecha_envio: Optional[datetime]
