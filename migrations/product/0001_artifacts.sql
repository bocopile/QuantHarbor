CREATE SCHEMA qh_product;
CREATE TABLE qh_product.schema_migrations (
    version integer PRIMARY KEY CHECK (version = 1),
    checksum text NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$')
);
CREATE TABLE qh_product.artifacts (
    namespace text NOT NULL CHECK (namespace IN ('report','snapshot','experiment','target')),
    kind text NOT NULL CHECK (kind IN ('Report','PortfolioSnapshot','ExperimentResult','plan','candidate','result')),
    artifact_id text NOT NULL CHECK (artifact_id ~ '^[ -~]{1,128}$'),
    environment text NOT NULL CHECK (environment = 'synthetic'),
    account_ref text NOT NULL CHECK (account_ref ~ '^[ -~]{1,128}$'),
    created_at text NOT NULL CHECK (length(created_at) BETWEEN 1 AND 40),
    record_hash text NOT NULL CHECK (record_hash ~ '^[0-9a-f]{64}$'),
    wire_sha256 text NOT NULL CHECK (wire_sha256 ~ '^[0-9a-f]{64}$'),
    payload bytea NOT NULL CHECK (octet_length(payload) BETWEEN 1 AND 65536),
    predecessor text CHECK (predecessor ~ '^[ -~]{1,128}$'),
    comparison_key text CHECK (comparison_key ~ '^[ -~]{1,128}$'),
    plan_id text CHECK (plan_id ~ '^[ -~]{1,128}$'),
    PRIMARY KEY (namespace,kind,artifact_id),
    CHECK (encode(sha256(payload),'hex') = wire_sha256),
    CHECK ((namespace='report' AND kind='Report') OR (namespace='snapshot' AND kind='PortfolioSnapshot')
        OR (namespace='experiment' AND kind='ExperimentResult') OR (namespace='target' AND kind IN ('plan','candidate','result')))
);
CREATE INDEX artifacts_listing ON qh_product.artifacts(namespace,environment,account_ref,created_at,kind,artifact_id);
CREATE UNIQUE INDEX experiment_one_child ON qh_product.artifacts(predecessor)
    WHERE namespace='experiment' AND predecessor IS NOT NULL;
CREATE FUNCTION qh_product.append_artifacts(batch jsonb, capacity integer) RETURNS void
LANGUAGE plpgsql AS $fn$
DECLARE r jsonb; old qh_product.artifacts%ROWTYPE; parent qh_product.artifacts%ROWTYPE;
    ns text; n bigint; b bigint;
BEGIN
    PERFORM pg_advisory_xact_lock(5130028);
    IF capacity < 1 OR capacity > 128 OR jsonb_typeof(batch)<>'array'
        OR jsonb_array_length(batch) NOT BETWEEN 1 AND 128 THEN
        RAISE EXCEPTION 'product_artifact_capacity';
    END IF;
    ns := batch->0->>'namespace';
    FOR r IN SELECT value FROM jsonb_array_elements(batch) LOOP
        IF r->>'namespace' IS DISTINCT FROM ns THEN RAISE EXCEPTION 'product_artifact_namespace'; END IF;
        SELECT * INTO old FROM qh_product.artifacts WHERE namespace=ns AND kind=r->>'kind' AND artifact_id=r->>'artifact_id';
        IF FOUND THEN
            IF to_jsonb(old) - 'payload' <> r - 'payload' OR old.payload <> decode(r->>'payload','hex') THEN
                RAISE EXCEPTION 'product_artifact_conflict';
            END IF;
            CONTINUE;
        END IF;
        IF r->>'predecessor' IS NOT NULL THEN
            SELECT * INTO parent FROM qh_product.artifacts WHERE namespace=ns
                AND kind=CASE WHEN ns='target' THEN 'plan' ELSE r->>'kind' END AND artifact_id=r->>'predecessor';
            IF NOT FOUND OR parent.account_ref<>r->>'account_ref' OR parent.environment<>r->>'environment'
                OR parent.created_at::timestamptz > (r->>'created_at')::timestamptz
                OR (ns='experiment' AND parent.comparison_key IS DISTINCT FROM r->>'comparison_key') THEN
                RAISE EXCEPTION 'product_artifact_predecessor';
            END IF;
        END IF;
        IF ns='target' AND r->>'kind'<>'plan' THEN
            IF NOT EXISTS(SELECT 1 FROM qh_product.artifacts WHERE namespace=ns AND kind='plan'
                AND artifact_id=r->>'plan_id' AND account_ref=r->>'account_ref' AND environment=r->>'environment') THEN
                RAISE EXCEPTION 'product_artifact_plan';
            END IF;
        END IF;
        INSERT INTO qh_product.artifacts VALUES(ns,r->>'kind',r->>'artifact_id',r->>'environment',r->>'account_ref',
            r->>'created_at',r->>'record_hash',r->>'wire_sha256',decode(r->>'payload','hex'),
            r->>'predecessor',r->>'comparison_key',r->>'plan_id');
    END LOOP;
    SELECT count(*),coalesce(sum(octet_length(payload)),0) INTO n,b FROM qh_product.artifacts WHERE namespace=ns;
    IF n>capacity OR n>128 OR b>8388608 THEN RAISE EXCEPTION 'product_artifact_capacity'; END IF;
    SELECT count(*),coalesce(sum(octet_length(payload)),0) INTO n,b FROM qh_product.artifacts;
    IF n>512 OR b>33554432 THEN RAISE EXCEPTION 'product_artifact_capacity'; END IF;
END $fn$;
