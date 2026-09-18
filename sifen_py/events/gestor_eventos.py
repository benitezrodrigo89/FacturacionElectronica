"""
Orquestador de eventos SIFEN.
Encapsula el flujo: generar XML → firmar → enviar para cada tipo de evento.
"""
from sifen_py.core.config import SifenConfig
from sifen_py.services.xml_wrapper import XMLGeneratorWrapper
from sifen_py.services.signer import XMLSigner
from sifen_py.services.soap_client import SifenSOAPClient, RespuestaSIFEN


class GestorEventos:
    """
    Orquesta eventos SIFEN: genera el XML del evento, lo firma y lo envía.

    Acepta servicios externos opcionales para facilitar testing::

        gestor = GestorEventos(config, wrapper=mock_wrapper, signer=mock_signer, client=mock_client)

    Uso normal::

        gestor = GestorEventos(config)
        resp = gestor.cancelar(cdc='01...', motivo='Error de emisión')
    """

    def __init__(
        self,
        config: SifenConfig,
        wrapper: XMLGeneratorWrapper = None,
        signer:  XMLSigner           = None,
        client:  SifenSOAPClient     = None,
    ):
        self.config  = config
        self.wrapper = wrapper or XMLGeneratorWrapper(config)
        self.signer  = signer  or XMLSigner(config)
        self.client  = client  or SifenSOAPClient(config)

    def cancelar(self, cdc: str, motivo: str) -> RespuestaSIFEN:
        """
        Cancela un DE aprobado ante la SET.

        Args:
            cdc:    CDC del documento a cancelar (44 dígitos)
            motivo: Descripción del motivo de cancelación (mín. 5 caracteres)

        Returns:
            RespuestaSIFEN de la SET
        """
        xml_evento  = self.wrapper.generar_xml_evento_cancelacion(cdc, motivo)
        xml_firmado = self.signer.firmar_xml(xml_evento)
        return self.client.enviar_evento_directo(xml_firmado)

    def inutilizar(
        self,
        tipo_documento:  int,
        establecimiento: str,
        punto:           str,
        numero_desde:    int,
        numero_hasta:    int,
        motivo:          str,
    ) -> RespuestaSIFEN:
        """
        Declara ante la SET que un rango de numeración no será utilizado.

        Args:
            tipo_documento:  1=FE, 5=NCE, 6=NDE, 7=NRE
            establecimiento: Código de establecimiento (ej: '001')
            punto:           Punto de expedición (ej: '001')
            numero_desde:    Primer número a inutilizar
            numero_hasta:    Último número a inutilizar
            motivo:          Motivo de la inutilización

        Returns:
            RespuestaSIFEN de la SET
        """
        xml_evento  = self.wrapper.generar_xml_evento_inutilizacion(
            tipo_documento=tipo_documento,
            establecimiento=establecimiento,
            punto=punto,
            numero_desde=numero_desde,
            numero_hasta=numero_hasta,
            motivo=motivo,
        )
        xml_firmado = self.signer.firmar_xml(xml_evento)
        return self.client.enviar_evento_directo(xml_firmado)

    def conformidad(
        self,
        cdc:              str,
        tipo_conformidad: int,
        fecha_recepcion:  str,
    ) -> RespuestaSIFEN:
        """
        El receptor informa a la SET que recibió el documento.

        Args:
            cdc:              CDC del documento
            tipo_conformidad: 1=Total, 2=Parcial
            fecha_recepcion:  Fecha ISO 8601, ej: '2026-09-18T10:00:00'

        Returns:
            RespuestaSIFEN de la SET
        """
        xml_evento  = self.wrapper.generar_xml_evento_conformidad(
            cdc=cdc,
            tipo_conformidad=tipo_conformidad,
            fecha_recepcion=fecha_recepcion,
        )
        xml_firmado = self.signer.firmar_xml(xml_evento)
        return self.client.enviar_evento_directo(xml_firmado)
