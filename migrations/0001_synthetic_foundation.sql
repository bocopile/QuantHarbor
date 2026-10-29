-- Initial synthetic metadata only. Not a financial ledger schema.
CREATE TABLE qh.runtime_identity (
    singleton boolean PRIMARY KEY CHECK (singleton),
    environment text NOT NULL CHECK (environment = 'synthetic'),
    schema_version integer NOT NULL CHECK (schema_version = 1),
    canonicalization_version text NOT NULL CHECK (canonicalization_version = 'qh-canonical-json-v1')
);
INSERT INTO qh.runtime_identity VALUES (true, 'synthetic', 1, 'qh-canonical-json-v1');
CREATE TABLE qh.synthetic_probe (
    probe_id integer PRIMARY KEY,
    exact_value numeric(38,18) NOT NULL,
    description text NOT NULL
);
