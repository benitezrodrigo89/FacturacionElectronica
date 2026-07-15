"""
Wrapper para el generador de XML de Node.js
Integra el proyecto facturacionelectronicapy-xmlgen
"""
import json
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from loguru import logger

from sifen_py.core.exceptions import XMLGenerationException
from sifen_py.core.config import SifenConfig


class XMLGeneratorWrapper:
    """
    Wrapper que llama al generador de XML en Node.js
    Usa el proyecto facturacionelectronicapy-xmlgen de Marcos Jara
    """

    def __init__(self, config: SifenConfig):
        """
        Inicializa el wrapper

        Args:
            config: Configuración de SIFEN
        """
        self.config = config
        self.node_project_path = self._find_node_project()
        self._verify_node_installation()

    def _find_node_project(self) -> Path:
        """
        Encuentra la ruta del proyecto Node.js

        Returns:
            Path al proyecto Node.js
        """
        # Buscar desde la ubicación actual
        current = Path(__file__).parent.parent.parent
        node_path = current / "FacturacionElectronica" / "facturacionelectronicapy-xmlgen-main"

        if not node_path.exists():
            raise XMLGenerationException(
                "No se encontró el proyecto Node.js de generación de XML. "
                f"Se esperaba en: {node_path}"
            )

        # Verificar que tenga node_modules instalado
        if not (node_path / "node_modules").exists():
            raise XMLGenerationException(
                f"El proyecto Node.js no tiene las dependencias instaladas. "
                f"Ejecute: cd {node_path} && npm install"
            )

        return node_path

    def _verify_node_installation(self):
        """Verifica que Node.js esté instalado"""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                check=True
            )
            logger.info(f"Node.js detectado: {result.stdout.strip()}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise XMLGenerationException(
                "Node.js no está instalado o no se encuentra en el PATH. "
                "Instale Node.js desde https://nodejs.org/"
            )

    def _prepare_params(self) -> Dict[str, Any]:
        """
        Prepara el parámetro 'params' para el generador Node.js

        Returns:
            Dict con los parámetros del contribuyente
        """
        from datetime import datetime
        return {
            "version": 150,
            "ruc": self.config.ruc,
            "razonSocial": self.config.razon_social,
            "nombreFantasia": self.config.nombre_fantasia,
            # timbrado — puede sobreescribirse pasando timbradoNumero/timbradoFecha en data
            "timbradoNumero": getattr(self.config, 'timbrado_numero', '00000000'),
            "timbradoFecha":  getattr(self.config, 'timbrado_fecha',
                                      datetime.now().strftime('%Y-%m-%d')),
            "actividadesEconomicas": [{
                "codigo": self.config.actividad_economica or "0",
                "descripcion": "Actividad principal"
            }] if self.config.actividad_economica else [],
            "tipoContribuyente": 2,
            "tipoRegimen": 8,
            "establecimientos": [{
                "codigo": self.config.establecimiento,
                "direccion": self.config.direccion or "Sin dirección",
                "numeroCasa": "0",
                "departamento": self.config.departamento or 11,
                "departamentoDescripcion": "CENTRAL",
                "distrito": self.config.distrito or 1,
                "distritoDescripcion": "ASUNCION",
                "ciudad": self.config.ciudad or 1,
                "ciudadDescripcion": "ASUNCION",
                "telefono": self.config.telefono or "",
                "email": self.config.email or "",
                "denominacion": "Sucursal Principal"
            }]
        }

    def generar_xml_de(self, data: Dict[str, Any], tipo_documento: Optional[int] = None) -> str:
        """
        Genera el XML de un Documento Electrónico

        Args:
            data: Datos del documento electrónico
            tipo_documento: Tipo de documento (opcional, se toma de data si no se especifica)

        Returns:
            XML generado como string

        Raises:
            XMLGenerationException: Si hay error en la generación
        """
        # Asegurar que tenga el tipo de documento
        if tipo_documento:
            data["tipoDocumento"] = tipo_documento

        # Asegurar que tenga establecimiento y punto
        if "establecimiento" not in data:
            data["establecimiento"] = self.config.establecimiento
        if "punto" not in data:
            data["punto"] = self.config.punto_expedicion

        # Agregar CSC si no está presente
        if "codigoSeguridadAleatorio" not in data:
            data["codigoSeguridadAleatorio"] = self.config.csc

        # Inyectar objeto 'factura' con presencia=1 (operación presencial) si no viene
        tipo_doc = data.get("tipoDocumento", 1)
        if tipo_doc == 1 and "factura" not in data:
            data["factura"] = {"presencia": 1}

        # Preparar parámetros
        params = self._prepare_params()
        # Permitir sobreescribir timbrado desde data
        if "timbradoNumero" in data:
            params["timbradoNumero"] = str(data.pop("timbradoNumero"))
        if "timbradoFecha" in data:
            params["timbradoFecha"] = data.pop("timbradoFecha")

        # Crear script temporal de Node.js
        script = self._create_node_script(params, data)

        # Ejecutar Node.js
        try:
            result = subprocess.run(
                ["node", "-"],
                input=script,
                capture_output=True,
                text=True,
                cwd=str(self.node_project_path),
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"Error en generación de XML: {result.stderr}")
                raise XMLGenerationException(
                    f"Error al generar XML: {result.stderr}",
                    code="XML_GEN_ERROR",
                    details={"stdout": result.stdout, "stderr": result.stderr}
                )

            xml = result.stdout.strip()

            if not xml or not xml.startswith("<?xml"):
                raise XMLGenerationException(
                    "El generador no devolvió un XML válido",
                    details={"output": xml}
                )

            logger.info(f"XML generado exitosamente. Longitud: {len(xml)} caracteres")
            return xml

        except subprocess.TimeoutExpired:
            raise XMLGenerationException(
                "Timeout al generar XML (>30 segundos)",
                code="XML_GEN_TIMEOUT"
            )
        except Exception as e:
            logger.exception("Error inesperado al generar XML")
            raise XMLGenerationException(
                f"Error inesperado: {str(e)}",
                code="XML_GEN_UNEXPECTED"
            )

    def generar_xml_evento_cancelacion(self, cdc: str, motivo: str) -> str:
        """
        Genera XML para evento de cancelación

        Args:
            cdc: CDC del documento a cancelar
            motivo: Motivo de la cancelación

        Returns:
            XML del evento
        """
        params = self._prepare_params()
        data = {
            "cdc": cdc,
            "motivo": motivo
        }

        script = self._create_event_script("cancelacion", params, data)
        return self._execute_event_script(script)

    def generar_xml_evento_inutilizacion(
        self,
        tipo_documento: int,
        establecimiento: str,
        punto: str,
        numero_desde: int,
        numero_hasta: int,
        motivo: str
    ) -> str:
        """
        Genera XML para evento de inutilización

        Args:
            tipo_documento: Tipo de documento
            establecimiento: Código de establecimiento
            punto: Punto de expedición
            numero_desde: Número inicial
            numero_hasta: Número final
            motivo: Motivo de la inutilización

        Returns:
            XML del evento
        """
        params = self._prepare_params()
        data = {
            "tipoDocumento": tipo_documento,
            "establecimiento": establecimiento,
            "punto": punto,
            "desde": numero_desde,
            "hasta": numero_hasta,
            "motivo": motivo
        }

        script = self._create_event_script("inutilizacion", params, data)
        return self._execute_event_script(script)

    def generar_xml_evento_conformidad(
        self,
        cdc: str,
        tipo_conformidad: int,
        fecha_recepcion: str
    ) -> str:
        """
        Genera XML para evento de conformidad

        Args:
            cdc: CDC del documento
            tipo_conformidad: Tipo de conformidad (1=Total, 2=Parcial)
            fecha_recepcion: Fecha de recepción

        Returns:
            XML del evento
        """
        params = self._prepare_params()
        data = {
            "cdc": cdc,
            "tipoConformidad": tipo_conformidad,
            "fechaRecepcion": fecha_recepcion
        }

        script = self._create_event_script("conformidad", params, data)
        return self._execute_event_script(script)

    def _create_node_script(self, params: Dict, data: Dict) -> str:
        """
        Crea el script de Node.js para ejecutar

        Args:
            params: Parámetros del contribuyente
            data: Datos del documento

        Returns:
            Script de Node.js como string
        """
        params_json = json.dumps(params, ensure_ascii=False)
        data_json = json.dumps(data, ensure_ascii=False)

        return f"""
const xmlgen = require('./dist/index.js');

const params = {params_json};
const data = {data_json};

xmlgen.default.generateXMLDE(params, data).then(xml => {{
    console.log(xml);
}}).catch(error => {{
    console.error(error.message || error);
    process.exit(1);
}});
"""

    def _create_event_script(self, evento: str, params: Dict, data: Dict) -> str:
        """
        Crea script para generación de eventos

        Args:
            evento: Tipo de evento (cancelacion, inutilizacion, etc.)
            params: Parámetros del contribuyente
            data: Datos del evento

        Returns:
            Script de Node.js
        """
        params_json = json.dumps(params, ensure_ascii=False)
        data_json = json.dumps(data, ensure_ascii=False)

        # Mapeo de nombres de eventos
        metodos = {
            "cancelacion": "generateXMLEventoCancelacion",
            "inutilizacion": "generateXMLEventoInutilizacion",
            "conformidad": "generateXMLEventoConformidad",
            "disconformidad": "generateXMLEventoDisconformidad",
            "desconocimiento": "generateXMLEventoDesconocimiento",
            "notificacion": "generateXMLEventoNotificacion"
        }

        metodo = metodos.get(evento)
        if not metodo:
            raise XMLGenerationException(f"Evento no soportado: {evento}")

        return f"""
const xmlgen = require('./dist/index.js');

const params = {params_json};
const data = {data_json};

xmlgen.default.{metodo}(1, params, data).then(xml => {{
    console.log(xml);
}}).catch(error => {{
    console.error(error.message || error);
    process.exit(1);
}});
"""

    def _execute_event_script(self, script: str) -> str:
        """
        Ejecuta script de evento y retorna el XML

        Args:
            script: Script de Node.js

        Returns:
            XML generado
        """
        try:
            result = subprocess.run(
                ["node", "-"],
                input=script,
                capture_output=True,
                text=True,
                cwd=str(self.node_project_path),
                timeout=30
            )

            if result.returncode != 0:
                logger.error(f"Error en generación de evento: {result.stderr}")
                raise XMLGenerationException(
                    f"Error al generar evento: {result.stderr}"
                )

            xml = result.stdout.strip()
            logger.info("Evento XML generado exitosamente")
            return xml

        except subprocess.TimeoutExpired:
            raise XMLGenerationException("Timeout al generar evento XML")
        except Exception as e:
            raise XMLGenerationException(f"Error al generar evento: {str(e)}")
