"""Modelos de respuesta Pydantic para la API REST."""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class DocumentoResponse(BaseModel):
    id:                     int
    cdc:                    str
    numero_doc:             int
    establecimiento:        str
    punto_expedicion:       str
    estado:                 str
    codigo_sifen:           Optional[str]
    descripcion_sifen:      Optional[str]
    protocolo_autorizacion: Optional[str]
    ruc_receptor:           Optional[str]
    razon_social_receptor:  Optional[str]
    monto_total:            Optional[int]
    intentos:               int
    fecha_emision:          Optional[datetime]
    fecha_envio:            Optional[datetime]
    fecha_respuesta:        Optional[datetime]


class DocumentoListItem(BaseModel):
    id:                     int
    cdc:                    str
    numero_doc:             int
    estado:                 str
    codigo_sifen:           Optional[str]
    protocolo_autorizacion: Optional[str]
    fecha_envio:            Optional[datetime]
    intentos:               int


class ConsultaSifenResponse(BaseModel):
    cdc:                    str
    codigo_sifen:           str
    descripcion:            str
    estado_sifen:           Optional[str]
    protocolo_autorizacion: Optional[str]
    fecha_procesamiento:    Optional[str]
    estado_bd:              Optional[str]


class ResumenResponse(BaseModel):
    estados:    dict
    total:      int
