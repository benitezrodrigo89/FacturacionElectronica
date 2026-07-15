"""
Excepciones personalizadas para el sistema SIFEN
"""


class SifenException(Exception):
    """Excepción base para todas las excepciones del sistema SIFEN"""

    def __init__(self, message: str, code: str = None, details: dict = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)

    def __str__(self):
        if self.code:
            return f"[{self.code}] {self.message}"
        return self.message


class ValidationException(SifenException):
    """Excepción para errores de validación de datos"""
    pass


class SignatureException(SifenException):
    """Excepción para errores en la firma digital"""
    pass


class SOAPException(SifenException):
    """Excepción para errores en las comunicaciones SOAP"""
    pass


class CertificateException(SifenException):
    """Excepción para errores relacionados con certificados"""
    pass


class CDCException(SifenException):
    """Excepción para errores en la generación de CDC"""
    pass


class XMLGenerationException(SifenException):
    """Excepción para errores en la generación de XML"""
    pass


class BatchException(SifenException):
    """Excepción para errores en la gestión de lotes"""
    pass


class EventException(SifenException):
    """Excepción para errores en la gestión de eventos"""
    pass


class KuDEException(SifenException):
    """Excepción para errores en la generación de KuDE (PDF)"""
    pass


class ConfigurationException(SifenException):
    """Excepción para errores de configuración del sistema"""
    pass
