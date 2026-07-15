"""
Sistema de Facturación Electrónica SIFEN Paraguay
Manual Técnico v150

Este paquete proporciona todas las herramientas necesarias para la emisión,
firma y envío de Documentos Electrónicos al SIFEN.
"""

__version__ = '1.0.0'
__author__ = 'SIFEN Paraguay Implementation'

from sifen_py.core.config import SifenConfig
from sifen_py.core.exceptions import (
    SifenException,
    ValidationException,
    SignatureException,
    SOAPException,
    BatchException,
    CDCException,
)
from sifen_py.services.soap_client import SifenSOAPClient, RespuestaSIFEN
from sifen_py.services.batch_manager import BatchManager, EstadoDE, EstadoLote
from sifen_py.utils.cdc import generar_cdc, validar_cdc, descomponer_cdc
from sifen_py.generators.kude import KuDEGenerator

__all__ = [
    'SifenConfig',
    'SifenSOAPClient',
    'RespuestaSIFEN',
    'BatchManager',
    'EstadoDE',
    'EstadoLote',
    'KuDEGenerator',
    'generar_cdc',
    'validar_cdc',
    'descomponer_cdc',
    'SifenException',
    'ValidationException',
    'SignatureException',
    'SOAPException',
    'BatchException',
    'CDCException',
    '__version__',
]
