"""INTEGRATION tests for reference/agent-memory-lifecycle.md against PostgreSQL + Redis.

Artifacts under test:
  - reference/agent-memory-lifecycle.md §5   org-scope RLS policy (SQL read from the Markdown at run time)
  - assets/schemas/memory_item.schema.json   required fields and enums become the table's NOT NULL / CHECK constraints
  - scripts/validate_memory_item.py          lineage (NO_LINEAGE) rejection
  - reference/agentic-caching-patterns.md rule 8   answer-cache key per principal + memory version, bumped on erasure

The per-subject policy and the read/erase/cache helpers below are a minimal reference implementation of
the §5 "subject filters apply on top", §7 and rule 8 text; they are test code, not a library.

Skipped unless RUN_DB_INTEGRATION=1. Needs a disposable PostgreSQL 16+ and Redis 7+:
  MEMORY_IT_ADMIN_DSN   superuser DSN; the tests create and drop their own database and app role
  MEMORY_IT_REDIS_URL   redis://:<password>@127.0.0.1:<port>/0 (keys use a random per-run prefix and are deleted)
Negative controls (each must make tests fail):
  NEG_NO_RLS=1             disable row-level security after setup → the two isolation tests fail
  NEG_SKIP_CACHE_ERASE=1   erasure deletes rows but does not bump the memory version → the erasure test fails
"""

import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

if os.environ.get("RUN_DB_INTEGRATION") != "1":
    pytest.skip("integration test: set RUN_DB_INTEGRATION=1", allow_module_level=True)

psycopg = pytest.importorskip("psycopg")
redis_lib = pytest.importorskip("redis")
from psycopg import errors, sql  # noqa: E402
from psycopg.conninfo import make_conninfo  # noqa: E402

SKILL = Path(__file__).resolve().parents[1]
LIFECYCLE_MD = SKILL / "reference" / "agent-memory-lifecycle.md"
SCHEMA_JSON = SKILL / "assets" / "schemas" / "memory_item.schema.json"
EXAMPLE_JSON = SKILL / "assets" / "examples" / "memory_item.example.json"
VALIDATOR = SKILL / "scripts" / "validate_memory_item.py"


def documented_rls_sql() -> list[str]:
    text = LIFECYCLE_MD.read_text(encoding="utf-8")
    for block in re.findall(r"```sql\n(.*?)```", text, re.S):
        if "CREATE POLICY org_scope" in block:
            body = re.sub(r"--[^\n]*", "", block)
            return [re.sub(r"\s+", " ", s).strip() for s in body.split(";") if s.strip()]
    raise AssertionError("org_scope RLS block not found in agent-memory-lifecycle.md §5")


def ddl_from_schema() -> str:
    schema = json.loads(SCHEMA_JSON.read_text(encoding="utf-8"))
    props, required = schema["properties"], set(schema["required"])

    def enum_check(field: str) -> str:
        values = ", ".join("'" + v.replace("'", "''") + "'" for v in props[field]["enum"])
        return f"CHECK ({field} IN ({values}))"

    for field in ("org_id", "source_refs", "provenance_quality", "expires_at", "status"):
        assert field in required, f"schema no longer requires {field}"
    return f"""
        CREATE TABLE memory_item (
            item_id            text PRIMARY KEY,
            memory_type        text NOT NULL {enum_check("memory_type")},
            org_id             text NOT NULL,
            subject_type       text NOT NULL {enum_check("subject_type")},
            subject_id         text NOT NULL,
            role_visibility    text[] NOT NULL,
            consequential      boolean NOT NULL,
            content            text,
            source_refs        text[] NOT NULL CHECK (cardinality(source_refs) > 0),
            source_versions    text[] NOT NULL,
            canonical_version  int NOT NULL,
            provenance_quality text NOT NULL {enum_check("provenance_quality")},
            status             text NOT NULL {enum_check("status")},
            generated_at       timestamptz NOT NULL DEFAULT now(),
            expires_at         timestamptz NOT NULL
        )"""


class SecretDsns(dict):
    """DSNs carry passwords; pytest prints fixture values in failure tracebacks, so hide them."""

    def __repr__(self) -> str:
        return "<integration DSNs: redacted>"


class RedactedRedis(redis_lib.Redis):
    """redis-py's repr includes the connection password; keep it out of failure output."""

    def __repr__(self) -> str:
        return "<RedactedRedis>"


# ------------------------------------------------------------------ fixtures
@pytest.fixture(scope="module")
def env() -> Iterator[dict[str, str]]:
    admin_dsn = os.environ.get("MEMORY_IT_ADMIN_DSN")
    if not admin_dsn or not os.environ.get("MEMORY_IT_REDIS_URL"):
        pytest.fail("RUN_DB_INTEGRATION=1 but MEMORY_IT_ADMIN_DSN / MEMORY_IT_REDIS_URL is not set")
    suffix = secrets.token_hex(4)
    dbname, role, role_pw = f"memit_{suffix}", f"memit_app_{suffix}", secrets.token_urlsafe(24)
    with psycopg.connect(admin_dsn, autocommit=True) as root:
        root.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))
        root.execute(
            sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD {}").format(
                sql.Identifier(role), sql.Literal(role_pw)
            )
        )
    db_admin = make_conninfo(admin_dsn, dbname=dbname)
    try:
        with psycopg.connect(db_admin, autocommit=True) as conn:
            conn.execute(ddl_from_schema())
            for stmt in documented_rls_sql():
                conn.execute(stmt)
            # §5: "Subject and role filters apply on top" — enforced here as a restrictive policy.
            conn.execute(
                "CREATE POLICY subject_scope ON memory_item AS RESTRICTIVE "
                "USING (subject_id = current_setting('app.subject_id', true)) "
                "WITH CHECK (subject_id = current_setting('app.subject_id', true))"
            )
            conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role)))
            conn.execute(
                sql.SQL("GRANT SELECT, INSERT, UPDATE, DELETE ON memory_item TO {}").format(sql.Identifier(role))
            )
            if os.environ.get("NEG_NO_RLS") == "1":
                conn.execute("ALTER TABLE memory_item DISABLE ROW LEVEL SECURITY")
        yield SecretDsns(
            admin=db_admin,
            app=make_conninfo(admin_dsn, dbname=dbname, user=role, password=role_pw),
            prefix=f"memit:{suffix}",
        )
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as root:
            root.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname)))
            root.execute(sql.SQL("DROP ROLE IF EXISTS {}").format(sql.Identifier(role)))


@pytest.fixture(scope="module")
def cache(env: dict[str, str]) -> Iterator["redis_lib.Redis"]:
    client = RedactedRedis.from_url(os.environ["MEMORY_IT_REDIS_URL"], decode_responses=True)
    client.ping()
    yield client
    for key in client.scan_iter(f"{env['prefix']}:*"):
        client.delete(key)
    client.close()


# ------------------------------------------------------------------ reference helpers (test code)
def scoped(env: dict[str, str], org: str, subject: str) -> "psycopg.Connection":
    conn = psycopg.connect(env["app"])
    # §5: org from the verified token, transaction-local so a pooled connection never carries it over.
    conn.execute("SELECT set_config('app.org_id', %s, true), set_config('app.subject_id', %s, true)", (org, subject))
    return conn


def plant(env: dict[str, str], org: str, subject: str, item_id: str, content: str, expires: str = "1 year") -> None:
    with scoped(env, org, subject) as conn:
        conn.execute(
            "INSERT INTO memory_item (item_id, memory_type, org_id, subject_type, subject_id, role_visibility, "
            "consequential, content, source_refs, source_versions, canonical_version, provenance_quality, status, "
            "expires_at) VALUES (%s, 'long_term_user_entity', %s, 'user', %s, '{self}', false, %s, "
            "'{conversation:t1:turn-1}', '{1}', 1, 'USER_STATED', 'CURRENT', now() + %s::interval)",
            (item_id, org, subject, content, expires),
        )


def recall(env: dict[str, str], org: str, subject: str) -> list[tuple[str, str]]:
    """Authorized read: no org/subject predicate in SQL; RLS supplies the scope."""
    with scoped(env, org, subject) as conn:
        return conn.execute(
            "SELECT item_id, content FROM memory_item WHERE status = 'CURRENT' AND expires_at > now() ORDER BY item_id"
        ).fetchall()


def mem_version(cache: "redis_lib.Redis", prefix: str, org: str, subject: str) -> int:
    return int(cache.get(f"{prefix}:memver:{org}:{subject}") or 0)


def answer_key(cache: "redis_lib.Redis", prefix: str, org: str, subject: str, query: str) -> str:
    # Rule 8: per-principal key that includes the principal's memory version.
    digest = hashlib.sha256(query.encode()).hexdigest()[:16]
    return f"{prefix}:answer:{org}:{subject}:v{mem_version(cache, prefix, org, subject)}:{digest}"


def erase_subject(env: dict[str, str], cache: "redis_lib.Redis", org: str, subject: str) -> int:
    with scoped(env, org, subject) as conn:
        deleted = conn.execute("DELETE FROM memory_item WHERE subject_id = %s", (subject,)).rowcount
    if os.environ.get("NEG_SKIP_CACHE_ERASE") != "1":
        cache.incr(f"{env['prefix']}:memver:{org}:{subject}")
    return deleted


# ------------------------------------------------------------------ tests
def test_per_principal_isolation_via_rls(env: dict[str, str]) -> None:
    plant(env, "org-a", "user-1", "iso-u1", "user one prefers email")
    plant(env, "org-a", "user-2", "iso-u2", "PLANTED-USER2-SECRET")
    rows = recall(env, "org-a", "user-1")
    with scoped(env, "org-a", "user-1") as conn:
        leaked = conn.execute("SELECT count(*) FROM memory_item WHERE content LIKE '%PLANTED-USER2%'").fetchone()[0]
    assert ("iso-u1", "user one prefers email") in rows
    assert all(item_id != "iso-u2" for item_id, _ in rows)
    assert leaked == 0


def test_cross_org_read_and_write_denied(env: dict[str, str]) -> None:
    plant(env, "org-a", "user-9", "xorg-a", "PLANTED-ORG-A-SECRET")
    with scoped(env, "org-b", "user-9") as conn:  # same subject id string, different org
        seen = conn.execute("SELECT count(*) FROM memory_item WHERE org_id = 'org-a'").fetchone()[0]
        with pytest.raises(errors.InsufficientPrivilege, match="row-level security"):
            conn.execute(
                "INSERT INTO memory_item (item_id, memory_type, org_id, subject_type, subject_id, role_visibility, "
                "consequential, content, source_refs, source_versions, canonical_version, provenance_quality, "
                "status, expires_at) VALUES ('forged', 'long_term_user_entity', 'org-a', 'user', 'user-9', '{self}', "
                "false, 'forged', '{x:1}', '{1}', 1, 'USER_STATED', 'CURRENT', now() + interval '1 day')"
            )
    with psycopg.connect(env["app"]) as conn:  # no org context at all: fail closed
        unscoped = conn.execute("SELECT count(*) FROM memory_item").fetchone()[0]
    assert seen == 0
    assert unscoped == 0


def test_erasure_deletes_rows_and_invalidates_cache(env: dict[str, str], cache: "redis_lib.Redis") -> None:
    org, subject, query = "org-a", "user-erase", "what currency do I prefer?"
    plant(env, org, subject, "erase-1", "PLANTED-ERASE-ME prefers EUR")
    answer = recall(env, org, subject)[0][1]
    cache.set(answer_key(cache, env["prefix"], org, subject, query), answer, ex=3600)
    cached_before = cache.get(answer_key(cache, env["prefix"], org, subject, query))
    assert cached_before == answer  # positive control

    assert erase_subject(env, cache, org, subject) == 1
    with psycopg.connect(env["admin"]) as conn:  # superuser probe across every scope
        remaining = conn.execute("SELECT count(*) FROM memory_item WHERE content LIKE '%PLANTED-ERASE-ME%'").fetchone()[0]
    assert remaining == 0
    cached_after = cache.get(answer_key(cache, env["prefix"], org, subject, query))
    assert cached_after is None, "erased memory still served from the answer cache"


def test_expired_item_not_served(env: dict[str, str]) -> None:
    plant(env, "org-a", "user-ret", "ret-live", "still valid")
    plant(env, "org-a", "user-ret", "ret-expired", "PLANTED-EXPIRED", expires="-1 minute")
    ids = [item_id for item_id, _ in recall(env, "org-a", "user-ret")]
    assert ids == ["ret-live"]


def test_provenance_and_lineage_required(env: dict[str, str], tmp_path: Path) -> None:
    base = (
        "INSERT INTO memory_item (item_id, memory_type, org_id, subject_type, subject_id, role_visibility, "
        "consequential, content, source_refs, source_versions, canonical_version, provenance_quality, status, "
        "expires_at) VALUES (%s, 'long_term_user_entity', 'org-a', 'user', 'user-prov', '{self}', false, 'x', "
        "%s, '{1}', 1, %s, 'CURRENT', now() + interval '1 day')"
    )
    cases = [
        ("p-empty-lineage", [], "USER_STATED", errors.CheckViolation),
        ("p-null-prov", ["x:1"], None, errors.NotNullViolation),
        ("p-bad-prov", ["x:1"], "TRUST_ME", errors.CheckViolation),
    ]
    for item_id, refs, prov, exc in cases:
        with scoped(env, "org-a", "user-prov") as conn, pytest.raises(exc):
            conn.execute(base, (item_id, refs, prov))

    good = json.loads(EXAMPLE_JSON.read_text(encoding="utf-8"))["memory_items"][0]
    bad = dict(good, source_refs=[])
    results = {}
    for name, item in (("good", good), ("bad", bad)):
        path = tmp_path / f"{name}.memory.json"
        path.write_text(json.dumps({"memory_items": [item]}), encoding="utf-8")
        results[name] = subprocess.run(
            [sys.executable, str(VALIDATOR), "--json", str(path)], capture_output=True, text=True, timeout=60
        )
    assert results["good"].returncode == 0, results["good"].stdout + results["good"].stderr
    assert results["bad"].returncode == 1
    assert "NO_LINEAGE" in results["bad"].stdout


def test_cache_key_scoped_per_principal(env: dict[str, str], cache: "redis_lib.Redis") -> None:
    query = "summarize my preferences"
    key_u1 = answer_key(cache, env["prefix"], "org-a", "user-1", query)
    cache.set(key_u1, "PLANTED-USER1-ANSWER", ex=3600)
    key_u2 = answer_key(cache, env["prefix"], "org-a", "user-2", query)
    key_other_org = answer_key(cache, env["prefix"], "org-b", "user-1", query)
    assert len({key_u1, key_u2, key_other_org}) == 3
    # Locals only in asserts: pytest's introspection would otherwise render the client, whose repr carries the URL.
    hit_u2, hit_other_org, hit_u1 = cache.get(key_u2), cache.get(key_other_org), cache.get(key_u1)
    assert hit_u2 is None
    assert hit_other_org is None
    assert hit_u1 == "PLANTED-USER1-ANSWER"
