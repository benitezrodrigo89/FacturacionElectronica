-- Esquema de base de datos para SIFEN Paraguay
-- Ejecutar una sola vez: psql -U postgres -d sifen_py -f schema.sql

CREATE TABLE IF NOT EXISTS documentos_electronicos (
    id                      SERIAL PRIMARY KEY,
    cdc                     VARCHAR(44) UNIQUE NOT NULL,
    numero_doc              INTEGER NOT NULL,
    establecimiento         VARCHAR(3) NOT NULL DEFAULT '001',
    punto_expedicion        VARCHAR(3) NOT NULL DEFAULT '001',
    tipo_documento          INTEGER NOT NULL DEFAULT 1,  -- 1=Factura
    fecha_emision           TIMESTAMPTZ,
    ruc_receptor            VARCHAR(20),
    razon_social_receptor   VARCHAR(255),
    monto_total             BIGINT,                      -- en guaraníes

    -- Documento
    xml_firmado             TEXT NOT NULL,               -- rDE firmado completo
    soap_envelope           TEXT,                        -- envelope enviado a SIFEN

    -- Estado SIFEN
    estado                  VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    -- 'pendiente' | 'aprobado' | 'rechazado' | 'duplicado' | 'error'
    codigo_sifen            VARCHAR(10),                 -- ej: 0260, 1001, 0160
    descripcion_sifen       TEXT,                        -- mensaje de SIFEN
    protocolo_autorizacion  VARCHAR(50),                 -- dProtAut (solo si aprobado)
    respuesta_xml           TEXT,                        -- XML completo de respuesta

    -- Control
    intentos                INTEGER NOT NULL DEFAULT 1,
    fecha_envio             TIMESTAMPTZ,
    fecha_respuesta         TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Índices útiles para consultas frecuentes
CREATE INDEX IF NOT EXISTS idx_de_estado     ON documentos_electronicos (estado);
CREATE INDEX IF NOT EXISTS idx_de_numero_doc ON documentos_electronicos (numero_doc);
CREATE INDEX IF NOT EXISTS idx_de_fecha      ON documentos_electronicos (fecha_emision);
CREATE INDEX IF NOT EXISTS idx_de_ruc_rec    ON documentos_electronicos (ruc_receptor);

-- Trigger para actualizar updated_at automáticamente
CREATE OR REPLACE FUNCTION actualizar_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trig_de_updated_at ON documentos_electronicos;
CREATE TRIGGER trig_de_updated_at
    BEFORE UPDATE ON documentos_electronicos
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();
