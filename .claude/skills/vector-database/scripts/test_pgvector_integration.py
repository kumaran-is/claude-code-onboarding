"""INTEGRATION tests for the pgvector SQL documented in this skill and in rag-architect.

The SQL under test is read from the Markdown at run time, so a doc edit that breaks the
pattern fails here:
  - vector-database/SKILL.md                              extension, vector column, model stamp, HNSW, scoped query
  - vector-database/references/pgvector-migration-template.md   HNSW template, null guard, operator alignment
  - rag-architect/references/versioning-and-freshness.md  rag_chunks table, tenant RLS policy, current-version filter

Skipped unless RUN_DB_INTEGRATION=1. Needs a disposable PostgreSQL 18 + pgvector >= 0.8 server, e.g.
  pgvector/pgvector:0.8.7-pg18@sha256:38681dc6eaf55308e2a4c6de392d131652dcfac70e1263e35cd9b5ea3fe39782
  PGVECTOR_IT_ADMIN_DSN  superuser DSN; the tests create and drop their own database and app role.
Negative control: NEG_NO_RLS=1 disables row-level security after setup; the three RLS tests must then fail.

Run: RUN_DB_INTEGRATION=1 PGVECTOR_IT_ADMIN_DSN=... pytest -q .claude/skills/vector-database/scripts/test_pgvector_integration.py
"""

import math
import os
import re
import secrets
from collections.abc import Iterator
from pathlib import Path

import pytest

if os.environ.get("RUN_DB_INTEGRATION") != "1":
    pytest.skip("integration test: set RUN_DB_INTEGRATION=1", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")
from psycopg import errors, sql  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402

SKILLS = Path(__file__).resolve().parents[2]
SKILL_MD = SKILLS / "vector-database" / "SKILL.md"
TEMPLATE_MD = SKILLS / "vector-database" / "references" / "pgvector-migration-template.md"
VERSIONING_MD = SKILLS / "rag-architect" / "references" / "versioning-and-freshness.md"

DIMS = 1536
ACTIVE_MODEL = "text-embedding-3-small"


# ------------------------------------------------------------------ SQL extraction
def _sql_blocks(md: Path) -> list[str]:
    text = md.read_text(encoding="utf-8")
    blocks = re.findall(r"```sql\n(.*?)```", text, re.S)
    return [re.sub(r"--[^\n]*", "", b) for b in blocks]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def statement(md: Path, starts_with: str, table: str | None = None) -> str:
    """Return the first documented statement whose normalized text starts with `starts_with`."""
    for block in _sql_blocks(md):
        for stmt in block.split(";"):
            candidate = _norm(stmt.replace("{table}", table) if table else stmt)
            if candidate.startswith(_norm(starts_with)):
                return candidate
    raise AssertionError(f"documented SQL starting with {starts_with!r} not found in {md.name}")


def block_containing(md: Path, marker: str) -> list[str]:
    for block in _sql_blocks(md):
        if marker in block:
            return [_norm(s) for s in block.split(";") if _norm(s)]
    raise AssertionError(f"no SQL block containing {marker!r} in {md.name}")


def fragment(md: Path, contains: str) -> str:
    for block in _sql_blocks(md):
        for para in re.split(r"\n\s*\n", block):
            if contains in para:
                return _norm(para)
    raise AssertionError(f"no SQL fragment containing {contains!r} in {md.name}")


def named(stmt: str) -> str:
    """$1 → %(p1)s so psycopg binds the documented positional parameters by name."""
    return re.sub(r"\$(\d+)", r"%(p\1)s", stmt)


# ------------------------------------------------------------------ vectors
def axis_vec(*weights: float) -> str:
    vals = list(weights) + [0.0] * (DIMS - len(weights))
    return "[" + ",".join(f"{v:g}" for v in vals) + "]"


def cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    return 1 - dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


class SecretDsns(dict):
    """DSNs carry passwords; pytest prints fixture values in failure tracebacks, so hide them."""

    def __repr__(self) -> str:
        return "<integration DSNs: redacted>"


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def env() -> Iterator[dict[str, str]]:
    admin_dsn = os.environ.get("PGVECTOR_IT_ADMIN_DSN")
    if not admin_dsn:
        pytest.fail("RUN_DB_INTEGRATION=1 but PGVECTOR_IT_ADMIN_DSN is not set")
    suffix = secrets.token_hex(4)
    dbname, role, role_pw = f"vecit_{suffix}", f"vecit_app_{suffix}", secrets.token_urlsafe(24)
    with psycopg.connect(admin_dsn, autocommit=True) as root:
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        root.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(role_pw)
            )
        )
    db_admin = make_conninfo(admin_dsn, dbname=dbname)
    app_dsn = make_conninfo(admin_dsn, dbname=dbname, user=role, password=role_pw)
    try:
        _setup_schema(db_admin, role)
        yield SecretDsns(admin=db_admin, app=app_dsn)
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as root:
            root.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname)))
            root.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


def _setup_schema(dsn: str, app_role: str) -> None:
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(statement(SKILL_MD, "CREATE EXTENSION IF NOT EXISTS vector"))
        # Base table the SKILL.md ALTERs and query pattern assume (id, title, tenant_id);
        # `name` is the column the template's null-guard query selects.
        conn.execute(
            "CREATE TABLE documents (id bigserial PRIMARY KEY, title text, name text, "
            "tenant_id varchar(100) NOT NULL)"
        )
        conn.execute(statement(SKILL_MD, "ALTER TABLE documents ADD COLUMN is_current"))
        conn.execute(statement(SKILL_MD, "ALTER TABLE documents ADD COLUMN embedding vector("))
        conn.execute(statement(SKILL_MD, "ALTER TABLE documents ADD COLUMN embedding_model"))
        conn.execute(statement(SKILL_MD, "ALTER TABLE documents ADD CONSTRAINT documents_embedding_model_stamped"))
        conn.execute(
            """
            INSERT INTO documents (title, name, tenant_id, embedding, embedding_model)
            SELECT 'doc ' || g, 'doc ' || g, 'bulk-' || (g %% 10),
                   (SELECT array_agg(random()::real) FROM generate_series(1, %s) WHERE g > 0)::vector,
                   %s
            FROM generate_series(1, 2000) g
            """,
            (DIMS, ACTIVE_MODEL),
        )
        conn.execute(statement(SKILL_MD, "CREATE INDEX CONCURRENTLY documents_embedding_hnsw"))
        conn.execute("ANALYZE documents")

        for stmt in block_containing(VERSIONING_MD, "CREATE TABLE rag_chunks"):
            conn.execute(stmt)
        # ACL labels per chunk (rag-ingest-checklist.md §E); the versioned table has no ACL column.
        conn.execute("ALTER TABLE rag_chunks ADD COLUMN acl_principals text[] NOT NULL DEFAULT '{}'")
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(app_role)))
        conn.execute(
            sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON rag_chunks TO {}").format(sql.Identifier(app_role))
        )
        _seed_chunks(conn)
        if os.environ.get("NEG_NO_RLS") == "1":
            conn.execute("ALTER TABLE rag_chunks DISABLE ROW LEVEL SECURITY")


def _seed_chunks(conn: psycopg.Connection) -> None:
    rows = [
        ("t1-a", "11111111-0000-0000-0000-000000000001", 1, "t1", "tenant one handbook", axis_vec(1, 0.1), None, ["group:all"]),
        ("t1-fin", "11111111-0000-0000-0000-000000000002", 1, "t1", "tenant one payroll", axis_vec(1, 0.2), None, ["group:finance"]),
        ("t1-v1", "11111111-0000-0000-0000-000000000003", 1, "t1", "policy v1 old text", axis_vec(1, 0.3), "now", ["group:all"]),
        ("t1-v2", "11111111-0000-0000-0000-000000000003", 2, "t1", "policy v2 new text", axis_vec(1, 0.3), None, ["group:all"]),
        # Same direction as the probe vector: the nearest neighbour overall, but in another tenant.
        ("t2-secret", "22222222-0000-0000-0000-000000000001", 1, "t2", "PLANTED-T2-SECRET", axis_vec(1, 0.0), None, ["group:all"]),
    ]
    for chunk_id, doc_id, ver, tenant, text, emb, superseded, acl in rows:
        conn.execute(
            "INSERT INTO rag_chunks (chunk_id, document_id, document_version, tenant_id, text, embedding, "
            "embedding_model, superseded_at, acl_principals) "
            "VALUES (%s, %s, %s, %s, %s, %s::vector, %s, CASE WHEN %s::text IS NULL THEN NULL ELSE now() END, %s)",
            (chunk_id, doc_id, ver, tenant, text, emb, ACTIVE_MODEL, superseded, acl),
        )


def admin_conn(env: dict[str, str]) -> psycopg.Connection:
    return psycopg.connect(env["admin"], cursor_factory=psycopg.ClientCursor)


def app_conn(env: dict[str, str]) -> psycopg.Connection:
    return psycopg.connect(env["app"], cursor_factory=psycopg.ClientCursor)


def set_tenant(conn: psycopg.Connection, tenant: str) -> None:
    # As documented in versioning-and-freshness.md §7: transaction-local tenant setting.
    conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tenant,))


# ------------------------------------------------------------------ 1-7: schema, index, query patterns
def test_extension_version_and_vector_dims(env: dict[str, str]) -> None:
    with admin_conn(env) as conn:
        ext = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()[0]
        assert tuple(int(x) for x in ext.split(".")[:2]) >= (0, 8), ext
        for table in ("documents", "rag_chunks"):
            typ = conn.execute(
                "SELECT format_type(atttypid, atttypmod) FROM pg_attribute "
                "WHERE attrelid = %s::regclass AND attname = 'embedding'",
                (table,),
            ).fetchone()[0]
            assert typ == f"vector({DIMS})", (table, typ)


def test_hnsw_index_uses_documented_ops_class(env: dict[str, str]) -> None:
    with admin_conn(env) as conn:
        indexdef = conn.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = 'documents_embedding_hnsw'"
        ).fetchone()[0]
    assert "USING hnsw (embedding vector_cosine_ops)" in indexdef
    assert "m='16'" in indexdef and "ef_construction='64'" in indexdef


def test_explain_cosine_uses_hnsw_and_l2_does_not(env: dict[str, str]) -> None:
    probe = statement(TEMPLATE_MD, "SELECT id FROM documents ORDER BY embedding <=> $1 LIMIT 10")
    q = axis_vec(*([0.5] * 8))
    with admin_conn(env) as conn:
        cos_plan = "\n".join(r[0] for r in conn.execute("EXPLAIN " + named(probe), {"p1": q}))
        l2_plan = "\n".join(r[0] for r in conn.execute("EXPLAIN " + named(probe.replace("<=>", "<->")), {"p1": q}))
    assert "Index Scan using documents_embedding_hnsw" in cos_plan, cos_plan
    assert "documents_embedding_hnsw" not in l2_plan, l2_plan  # operator/ops-class mismatch → no index


def test_scoped_query_cosine_ordering_matches_exact_distance(env: dict[str, str]) -> None:
    query = statement(SKILL_MD, "SELECT d.id, d.title, 1 - (d.embedding <=> $1::vector) AS similarity")
    vecs = {"near": [1.0, 0.1], "mid": [1.0, 1.0], "far": [0.1, 1.0]}
    probe = [1.0, 0.0]
    with admin_conn(env) as conn:
        for title, w in vecs.items():
            conn.execute(
                "INSERT INTO documents (title, tenant_id, embedding, embedding_model) VALUES (%s, 'order-t', %s::vector, %s)",
                (title, axis_vec(*w), ACTIVE_MODEL),
            )
        conn.execute(statement(SKILL_MD, "SET LOCAL hnsw.ef_search = 100"))
        conn.execute("SET LOCAL hnsw.iterative_scan = strict_order")  # filtered ANN: ann-vs-knn.md
        rows = conn.execute(named(query), {"p1": axis_vec(*probe), "p2": "order-t", "p3": ACTIVE_MODEL}).fetchall()
        conn.rollback()
    expected = sorted(vecs, key=lambda t: cosine_distance(probe, vecs[t]))
    assert [r[1] for r in rows] == expected
    for _id, title, sim in rows:
        assert sim == pytest.approx(1 - cosine_distance(probe, vecs[title]), abs=1e-5)


def test_embedding_model_stamp_enforced_and_filtered(env: dict[str, str]) -> None:
    query = statement(SKILL_MD, "SELECT d.id, d.title, 1 - (d.embedding <=> $1::vector) AS similarity")
    with admin_conn(env) as conn:
        with pytest.raises(errors.CheckViolation):
            conn.execute(
                "INSERT INTO documents (title, tenant_id, embedding, embedding_model) VALUES ('x', 'm-t', %s::vector, NULL)",
                (axis_vec(1),),
            )
        conn.rollback()
        for title, model in (("active", ACTIVE_MODEL), ("legacy", "legacy-embed-v1")):
            conn.execute(
                "INSERT INTO documents (title, tenant_id, embedding, embedding_model) VALUES (%s, 'm-t', %s::vector, %s)",
                (title, axis_vec(1, 0.1), model),
            )
        conn.execute("SET LOCAL hnsw.iterative_scan = strict_order")
        titles = [r[1] for r in conn.execute(named(query), {"p1": axis_vec(1), "p2": "m-t", "p3": ACTIVE_MODEL})]
        conn.rollback()
    assert titles == ["active"]


def test_dimension_mismatch_rejected(env: dict[str, str]) -> None:
    with admin_conn(env) as conn:
        with pytest.raises(errors.DataException, match=f"expected {DIMS} dimensions, not 768"):
            conn.execute(
                "INSERT INTO documents (title, tenant_id, embedding, embedding_model) VALUES ('d', 'dim-t', %s::vector, %s)",
                ("[" + ",".join(["0.1"] * 768) + "]", ACTIVE_MODEL),
            )
        conn.rollback()
        with pytest.raises(errors.DataException, match="different vector dimensions"):
            conn.execute("SELECT embedding <=> %s::vector FROM documents LIMIT 1", ("[" + ",".join(["0.1"] * 768) + "]",))


def test_null_guard_excludes_unembedded_rows(env: dict[str, str]) -> None:
    guarded = statement(TEMPLATE_MD, "SELECT id, name, 1 - (embedding <=> $1::vector) AS similarity", table="documents")
    unguarded = guarded.replace("WHERE embedding IS NOT NULL ", "")
    assert unguarded != guarded
    with admin_conn(env) as conn:
        null_id = conn.execute(
            "INSERT INTO documents (title, name, tenant_id, embedding, embedding_model) "
            "VALUES ('pending', 'pending', 'null-t', NULL, NULL) RETURNING id"
        ).fetchone()[0]
        conn.execute("SET LOCAL enable_indexscan = off")  # exact scan: the path where NULLs would surface
        params = {"p1": axis_vec(1), "p2": 10_000}
        guarded_ids = {r[0] for r in conn.execute(named(guarded), params)}
        unguarded_ids = {r[0] for r in conn.execute(named(unguarded), params)}
        conn.rollback()
    assert null_id not in guarded_ids
    assert null_id in unguarded_ids  # positive control: without the guard the NULL row is returned


# ------------------------------------------------------------------ 8-12: tenant, ACL, staleness (app role)
def test_rls_tenant_isolation_results_counts_neighbours(env: dict[str, str]) -> None:
    with app_conn(env) as conn:
        set_tenant(conn, "t1")
        nn = conn.execute(
            "SELECT tenant_id, text FROM rag_chunks ORDER BY embedding <=> %s::vector LIMIT 10", (axis_vec(1),)
        ).fetchall()
        count = conn.execute("SELECT count(*) FROM rag_chunks").fetchone()[0]
        planted = conn.execute("SELECT count(*) FROM rag_chunks WHERE text LIKE '%PLANTED-T2%'").fetchone()[0]
    assert {t for t, _ in nn} == {"t1"}, nn
    assert count == 4 and planted == 0


def test_rls_without_tenant_context_returns_zero_rows(env: dict[str, str]) -> None:
    with app_conn(env) as conn:
        assert conn.execute("SELECT count(*) FROM rag_chunks").fetchone()[0] == 0


def test_rls_with_check_blocks_cross_tenant_write(env: dict[str, str]) -> None:
    with app_conn(env) as conn:
        set_tenant(conn, "t1")
        with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
            conn.execute(
                "INSERT INTO rag_chunks (chunk_id, document_id, tenant_id, text, embedding_model) "
                "VALUES ('forged', gen_random_uuid(), 't2', 'forged write', %s)",
                (ACTIVE_MODEL,),
            )


def test_acl_filter_in_retrieval_call_and_revocation(env: dict[str, str]) -> None:
    acl_query = (
        "SELECT chunk_id FROM rag_chunks WHERE superseded_at IS NULL AND acl_principals && %s::text[] "
        "ORDER BY embedding <=> %s::vector LIMIT 10"
    )
    with app_conn(env) as conn:
        set_tenant(conn, "t1")
        basic = {r[0] for r in conn.execute(acl_query, (["group:all"], axis_vec(1)))}
        finance = {r[0] for r in conn.execute(acl_query, (["group:all", "group:finance"], axis_vec(1)))}
        conn.execute("UPDATE rag_chunks SET acl_principals = '{group:hr}' WHERE chunk_id = 't1-fin'")  # revoke at source
        revoked = {r[0] for r in conn.execute(acl_query, (["group:all", "group:finance"], axis_vec(1)))}
        conn.rollback()
    assert "t1-fin" not in basic
    assert "t1-fin" in finance
    assert "t1-fin" not in revoked


def test_superseded_version_excluded_by_default_filter(env: dict[str, str]) -> None:
    current_filter = fragment(VERSIONING_MD, "AND superseded_at IS NULL")
    assert current_filter == "WHERE tenant_id = $1 AND superseded_at IS NULL"
    with app_conn(env) as conn:
        set_tenant(conn, "t1")
        texts = [
            r[0]
            for r in conn.execute(
                named(f"SELECT text FROM rag_chunks {current_filter} AND document_id = '11111111-0000-0000-0000-000000000003'"),
                {"p1": "t1"},
            )
        ]
        all_versions = conn.execute(
            "SELECT count(*) FROM rag_chunks WHERE document_id = '11111111-0000-0000-0000-000000000003'"
        ).fetchone()[0]
    assert texts == ["policy v2 new text"]
    assert all_versions == 2  # the superseded row still exists; only the default filter hides it
