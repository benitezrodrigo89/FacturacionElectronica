"""
Generación y validación del CDC (Código de Control de Documento Electrónico)
según Manual Técnico SIFEN v150 — sección 3.2
"""
from datetime import datetime
from sifen_py.core.exceptions import CDCException


def calcular_digito_verificador_ruc(ruc_sin_dv: str) -> int:
    """
    Calcula el dígito verificador de un RUC usando módulo 11.
    """
    base = 11
    multiplicador = 2
    suma = 0
    for digito in reversed(ruc_sin_dv):
        suma += int(digito) * multiplicador
        multiplicador = multiplicador + 1 if multiplicador < base else 2
    resto = suma % base
    dv = 0 if resto <= 1 else base - resto
    return dv


def calcular_digito_verificador_cdc(cdc_sin_dv: str) -> int:
    """
    Calcula el dígito verificador del CDC de 43 caracteres (sin el último dígito).
    Algoritmo módulo 11 según Manual Técnico SIFEN v150.
    """
    base = 11
    multiplicador = 2
    suma = 0
    for digito in reversed(cdc_sin_dv):
        suma += int(digito) * multiplicador
        multiplicador = multiplicador + 1 if multiplicador < base else 2
    resto = suma % base
    return 0 if resto <= 1 else base - resto


def generar_cdc(
    tipo_documento: int,
    ruc_emisor: str,
    dv_emisor: str,
    establecimiento: str,
    punto_expedicion: str,
    numero: str,
    tipo_contribuyente: int,
    fecha_emision: datetime,
    tipo_emision: int = 1,
    codigo_seguridad: str = "00000000",
) -> str:
    """
    Genera el CDC de 44 dígitos según el algoritmo del Manual Técnico v150.

    Estructura del CDC (44 dígitos):
      [0]    1  dígito  → Tipo de documento (C002)
      [1-8]  8  dígitos → RUC emisor (sin DV, relleno a la izquierda con ceros)
      [9]    1  dígito  → DV del RUC emisor
      [10-12] 3 dígitos → Establecimiento (E001)
      [13-15] 3 dígitos → Punto de expedición (E002)
      [16-22] 7 dígitos → Número de documento (E003)
      [23]   1  dígito  → Tipo de contribuyente (D202)
      [24-31] 8 dígitos → Fecha de emisión AAAAMMDD
      [32]   1  dígito  → Tipo de emisión (C003)
      [33-40] 8 dígitos → Código de seguridad del contribuyente
      [41-42] 2 dígitos → 00 (reservado)
      [43]   1  dígito  → Dígito verificador del CDC

    Args:
        tipo_documento:    Tipo de DE según catálogo C002 (1=FE, 4=AFE, 5=NCE, 6=NDE, 7=NRE)
        ruc_emisor:        RUC sin dígito verificador (ej. "80000001")
        dv_emisor:         Dígito verificador del RUC (ej. "1")
        establecimiento:   Código de establecimiento 3 dígitos (ej. "001")
        punto_expedicion:  Punto de expedición 3 dígitos (ej. "001")
        numero:            Número correlativo del documento 7 dígitos (ej. "0000001")
        tipo_contribuyente: 1=Persona Física, 2=Persona Jurídica
        fecha_emision:     Fecha y hora de emisión
        tipo_emision:      1=Normal, 2=Contingencia, 3=Sin internet
        codigo_seguridad:  CSC del contribuyente, 8 dígitos
    """
    try:
        # Validar longitudes
        ruc_padded   = ruc_emisor.zfill(8)[:8]
        estab_padded = establecimiento.zfill(3)[:3]
        punto_padded = punto_expedicion.zfill(3)[:3]
        num_padded   = numero.zfill(7)[:7]
        csc_padded   = codigo_seguridad.zfill(8)[:8]
        fecha_str    = fecha_emision.strftime('%Y%m%d')

        cdc_sin_dv = (
            f"{tipo_documento}"
            f"{ruc_padded}"
            f"{dv_emisor}"
            f"{estab_padded}"
            f"{punto_padded}"
            f"{num_padded}"
            f"{tipo_contribuyente}"
            f"{fecha_str}"
            f"{tipo_emision}"
            f"{csc_padded}"
            f"00"
        )

        if len(cdc_sin_dv) != 43:
            raise CDCException(
                f"CDC sin DV tiene longitud incorrecta: {len(cdc_sin_dv)} (esperado 43). "
                f"Valor: {cdc_sin_dv}"
            )

        dv = calcular_digito_verificador_cdc(cdc_sin_dv)
        return f"{cdc_sin_dv}{dv}"

    except CDCException:
        raise
    except Exception as e:
        raise CDCException(f"Error generando CDC: {e}") from e


def validar_cdc(cdc: str) -> bool:
    """
    Valida que un CDC de 44 dígitos sea correcto (longitud y dígito verificador).
    """
    if not cdc or len(cdc) != 44:
        return False
    if not cdc.isdigit():
        return False
    dv_calculado = calcular_digito_verificador_cdc(cdc[:43])
    return dv_calculado == int(cdc[43])


def descomponer_cdc(cdc: str) -> dict:
    """
    Descompone un CDC de 44 dígitos en sus partes.
    Útil para debugging y logging.
    """
    if not validar_cdc(cdc):
        raise CDCException(f"CDC inválido: {cdc}")
    return {
        'tipo_documento':    int(cdc[0]),
        'ruc_emisor':        cdc[1:9].lstrip('0'),
        'dv_emisor':         cdc[9],
        'establecimiento':   cdc[10:13],
        'punto_expedicion':  cdc[13:16],
        'numero':            cdc[16:23],
        'tipo_contribuyente': int(cdc[23]),
        'fecha_emision':     cdc[24:32],
        'tipo_emision':      int(cdc[32]),
        'codigo_seguridad':  cdc[33:41],
        'reservado':         cdc[41:43],
        'dv':                int(cdc[43]),
    }
