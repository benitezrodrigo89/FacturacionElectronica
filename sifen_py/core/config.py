"""
Configuración del sistema SIFEN
"""
from typing import Optional
from pathlib import Path
from sifen_py.core.constants import AMBIENTE_TEST, AMBIENTE_PRODUCCION, URLS
from sifen_py.core.exceptions import ConfigurationException


class SifenConfig:
    """
    Configuración para el cliente SIFEN

    Attributes:
        ambiente: 'test' o 'prod'
        ruc: RUC del emisor (formato: 80000001-1)
        razon_social: Razón social del emisor
        nombre_fantasia: Nombre de fantasía (opcional)
        certificado_path: Ruta al archivo .pfx o .p12
        certificado_password: Contraseña del certificado
        csc: Código de Seguridad del Contribuyente
        establecimiento: Código de establecimiento (001-999)
        punto_expedicion: Punto de expedición (001-999)
        actividad_economica: Código de actividad económica
    """

    def __init__(
        self,
        ambiente: str,
        ruc: str,
        razon_social: str,
        certificado_path: str,
        certificado_password: str,
        csc: str,
        establecimiento: str = '001',
        punto_expedicion: str = '001',
        nombre_fantasia: Optional[str] = None,
        actividad_economica: Optional[str] = None,
        direccion: Optional[str] = None,
        departamento: Optional[int] = None,
        distrito: Optional[int] = None,
        ciudad: Optional[int] = None,
        telefono: Optional[str] = None,
        email: Optional[str] = None,
        timbrado_numero: str = '00000000',
        timbrado_fecha: Optional[str] = None,
    ):
        # Validar ambiente
        if ambiente not in [AMBIENTE_TEST, AMBIENTE_PRODUCCION]:
            raise ConfigurationException(
                f"Ambiente inválido: {ambiente}. Use 'test' o 'prod'"
            )

        self.ambiente = ambiente
        self.ruc = ruc
        self.razon_social = razon_social
        self.nombre_fantasia = nombre_fantasia or razon_social
        self.certificado_path = Path(certificado_path)
        self.certificado_password = certificado_password
        self.csc = csc
        self.establecimiento = establecimiento
        self.punto_expedicion = punto_expedicion
        self.actividad_economica = actividad_economica
        self.direccion = direccion
        self.departamento = departamento
        self.distrito = distrito
        self.ciudad = ciudad
        self.telefono = telefono
        self.email = email
        self.timbrado_numero = str(timbrado_numero).zfill(8)[:8]
        from datetime import datetime
        self.timbrado_fecha = timbrado_fecha or datetime.now().strftime('%Y-%m-%d')

        # Validar que el certificado existe
        if not self.certificado_path.exists():
            raise ConfigurationException(
                f"Certificado no encontrado: {self.certificado_path}"
            )

        # Validar formato del RUC
        if not self._validar_ruc(ruc):
            raise ConfigurationException(
                f"Formato de RUC inválido: {ruc}. Use formato: 80000001-1"
            )

    @staticmethod
    def _validar_ruc(ruc: str) -> bool:
        """Valida el formato del RUC"""
        if not ruc or '-' not in ruc:
            return False
        partes = ruc.split('-')
        if len(partes) != 2:
            return False
        return partes[0].isdigit() and partes[1].isdigit()

    def get_url(self, servicio: str) -> str:
        """Obtiene la URL del servicio solicitado"""
        return URLS[self.ambiente][servicio]

    def get_ruc_emisor(self) -> str:
        """Retorna el RUC sin el dígito verificador"""
        return self.ruc.split('-')[0]

    def get_dv_emisor(self) -> str:
        """Retorna el dígito verificador del RUC"""
        return self.ruc.split('-')[1]

    def es_produccion(self) -> bool:
        """Verifica si está configurado para producción"""
        return self.ambiente == AMBIENTE_PRODUCCION

    def es_test(self) -> bool:
        """Verifica si está configurado para test"""
        return self.ambiente == AMBIENTE_TEST

    def __repr__(self):
        return (
            f"SifenConfig(ambiente='{self.ambiente}', "
            f"ruc='{self.ruc}', "
            f"establecimiento='{self.establecimiento}')"
        )
