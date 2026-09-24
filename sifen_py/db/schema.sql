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
    data_json               TEXT,                        -- datos originales del documento (JSON)

    -- Estado SIFEN
    estado                  VARCHAR(20) NOT NULL DEFAULT 'pendiente',
    -- 'pendiente' | 'aprobado' | 'rechazado' | 'duplicado' | 'error'
    codigo_sifen            VARCHAR(10),                 -- ej: 0260, 1001, 0160
    descripcion_sifen       TEXT,                        -- mensaje de SIFEN
    protocolo_autorizacion  VARCHAR(50),                 -- dProtAut (solo si aprobado)
    respuesta_xml           TEXT,                        -- XML completo de respuesta

    -- Documento referenciado (para NCE, NDE, NRE)
    cdc_doc_referenciado    VARCHAR(44),                 -- CDC de la FE/doc que origina esta NC/ND/NR

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
CREATE INDEX IF NOT EXISTS idx_de_cdc_ref    ON documentos_electronicos (cdc_doc_referenciado);

-- Migración para BD existentes (agrega columna si no existe)
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='documentos_electronicos' AND column_name='cdc_doc_referenciado'
  ) THEN
    ALTER TABLE documentos_electronicos ADD COLUMN cdc_doc_referenciado VARCHAR(44);
  END IF;
END $$;

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

-- ─────────────────────────────────────────────────────────────
-- Clientes frecuentes (solo para uso de la webapp)
-- La API no valida contra esta tabla.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clientes_sifen (
    id              SERIAL PRIMARY KEY,
    ruc             VARCHAR(20) NOT NULL,
    razon_social    VARCHAR(255) NOT NULL,
    direccion       VARCHAR(255),
    telefono        VARCHAR(50),
    email           VARCHAR(100),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_clientes_sifen_ruc ON clientes_sifen (ruc) WHERE activo = TRUE;
CREATE INDEX IF NOT EXISTS idx_clientes_sifen_razon ON clientes_sifen (razon_social);

DROP TRIGGER IF EXISTS trig_clientes_sifen_updated_at ON clientes_sifen;
CREATE TRIGGER trig_clientes_sifen_updated_at
    BEFORE UPDATE ON clientes_sifen
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();

-- ─────────────────────────────────────────────────────────────
-- Productos / Servicios frecuentes (solo para uso de la webapp)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS productos_sifen (
    id              SERIAL PRIMARY KEY,
    codigo          VARCHAR(50),
    descripcion     VARCHAR(255) NOT NULL,
    precio_unitario INTEGER NOT NULL DEFAULT 0,  -- en guaraníes
    unidad_medida   INTEGER NOT NULL DEFAULT 77, -- código SIFEN (77=Unidad)
    iva             INTEGER NOT NULL DEFAULT 10  CHECK (iva IN (0, 5, 10)),
    activo          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_productos_sifen_descripcion ON productos_sifen (descripcion);
CREATE INDEX IF NOT EXISTS idx_productos_sifen_codigo      ON productos_sifen (codigo);

DROP TRIGGER IF EXISTS trig_productos_sifen_updated_at ON productos_sifen;
CREATE TRIGGER trig_productos_sifen_updated_at
    BEFORE UPDATE ON productos_sifen
    FOR EACH ROW EXECUTE FUNCTION actualizar_updated_at();
