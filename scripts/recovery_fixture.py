"""Synthetic recovery probes. Only run inside the disposable recovery-drill stack."""

import hashlib
import json
import os
import stat
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "deploy"))

MARKER = "lawyer-recovery-drill-v1"
PAYLOAD = "SYNTHETIC RECOVERY FIXTURE — no client or legal authority data.\n".encode()


def require_drill():
    if os.environ.get("LA_RECOVERY_DRILL") != MARKER:
        raise ValueError("This probe is restricted to the disposable recovery drill")


def code_fingerprint(root):
    """Bind the API's copied source/dependency inputs to the invoking checkout."""
    files = [root / "backend/pyproject.toml", root / "backend/uv.lock", root / "deploy/volume_archive.py"]
    for directory in ("backend/app", "scripts", "ontology"):
        files.extend(path for path in (root / directory).rglob("*")
                     if path.is_file() and path.suffix in {".py", ".json", ".ttl", ".nq", ".trig"})
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return {"sha256": digest.hexdigest(), "files": len(files)}


def file_inventory(roots):
    """Hash every regular byte and directory metadata; never follow volume links."""
    result = {}
    for name, root in roots.items():
        total = count = 0
        digest = hashlib.sha256()
        paths = [root]
        for directory, dirs, files in os.walk(root, followlinks=False):
            paths.extend(Path(directory) / item for item in sorted(dirs + files))
        for path in sorted(paths):
            relative = path.relative_to(root).as_posix()
            # Deliberately invalidated by restore; checked separately before/after.
            if name == "documents" and relative == "publication-epoch":
                continue
            info = path.lstat()
            if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise ValueError("Unexpected volume object")
            header = [relative, stat.S_IFMT(info.st_mode), stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid]
            digest.update(json.dumps(header, separators=(",", ":")).encode() + b"\0")
            if path.is_file():
                content = hashlib.sha256()
                with path.open("rb") as stream:
                    while chunk := stream.read(1024 * 1024):
                        total += len(chunk)
                        content.update(chunk)
                digest.update(content.digest())
                count += 1
        result[name] = {"sha256": digest.hexdigest(), "files": count, "bytes": total}
    return result


def seed_volumes():
    from volume_archive import ROOTS

    for family in ("graphs", "public_sources"):
        target = ROOTS[family] / "SYNTHETIC-RECOVERY-SENTINEL.txt"
        with target.open("xb") as stream:
            stream.write(PAYLOAD)
    epoch = ROOTS["documents"] / "publication-epoch"
    with epoch.open("x") as stream:
        stream.write(str(uuid4()) + "\n")
    reviews = ROOTS["documents"] / "release-authorizations"
    reviews.mkdir(exist_ok=True)
    (reviews / "SYNTHETIC-NOT-AN-AUTHORIZATION.txt").write_bytes(PAYLOAD)
    return {"synthetic_sentinels": True, "epoch_created": True}


@contextmanager
def client():
    import httpx

    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30, trust_env=False) as connection:
        login = connection.post("/api/v1/auth/login", json={"username": "demo", "password": "demo-local-only"})
        login.raise_for_status()
        connection.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        yield connection


def store():
    from app.config import Settings
    from app.db import Store

    settings = Settings(_env_file=None)
    if not settings.demo_mode or not settings.database_url.endswith("@postgres:5432/lawyer_recovery_drill"):
        raise ValueError("Unexpected recovery database")
    return Store(settings)


def seed():
    import httpx
    from sqlalchemy import select

    from app.db import User
    from app.research_jobs import submission

    with client() as connection:
        matter = connection.get("/api/v1/matters").json()[0]["id"]
        base = f"/api/v1/matters/{matter}"
        uploaded = connection.post(base + "/documents", files={"file": ("SYNTHETIC-RECOVERY.txt", PAYLOAD, "text/plain")})
        uploaded.raise_for_status()
        document = uploaded.json()["id"]
        fact = connection.post(base + "/facts", json={"text": "SYNTHETIC recovery fact", "status": "alleged"})
        fact.raise_for_status()
        response = connection.post(base + "/research", json={"question": "Ödeme ve sona erme bildirimleri"})
        response.raise_for_status()
        ident = response.json()["id"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            run = connection.get(base + f"/research/{ident}").json()
            if run["status"] not in {"queued", "running"}:
                break
            time.sleep(0.1)
        if run["status"] != "completed":
            raise ValueError("Synthetic research did not complete")
        product = connection.get(base + "/products/" + run["product_id"])
        product.raise_for_status()
        expected = {"matter": matter, "document": document, "product": run["product_id"], "run": ident,
                    "product_sha256": hashlib.sha256(product.content).hexdigest(), "pending": []}
    db = store()
    try:
        with db.session() as session:
            user = session.scalar(select(User).where(User.username == "demo"))
            for status in ("queued", "running", "cancelling"):
                row = db.add(session, "research", user, {
                    **submission(300), "question": "SYNTHETIC durable interrupted state", "status": status,
                }, matter)
                expected["pending"].append(row.id)
            session.commit()
    finally:
        db.engine.dispose()
    Path("/data/recovery-expected.json").write_text(json.dumps(expected))
    with httpx.Client(base_url="http://opensearch:9200", timeout=30, trust_env=False) as search:
        response = search.put("/synthetic-recovery/_doc/sentinel?refresh=true", json={"text": PAYLOAD.decode()})
        response.raise_for_status()
        search.post("/synthetic-recovery/_flush").raise_for_status()
    return {"authenticated": True, "uploaded_document": True, "completed_research": 1,
            "simulated_unfinished_records": 3, "opensearch_documents": 1}


def verify():
    import httpx
    from sqlalchemy import func, select

    from app.db import Record

    expected = json.loads(Path("/data/recovery-expected.json").read_text())
    if Path("/data/publication-epoch").exists():
        raise ValueError("Historical publication epoch survived restore")
    if Path("/data/release-authorizations/SYNTHETIC-NOT-AN-AUTHORIZATION.txt").read_bytes() != PAYLOAD:
        raise ValueError("Private review bytes not retained")
    with client() as connection:
        base = f"/api/v1/matters/{expected['matter']}"
        original = connection.get(base + f"/documents/{expected['document']}/original")
        original.raise_for_status()
        if original.content != PAYLOAD:
            raise ValueError("Restored document did not decrypt to original bytes")
        product = connection.get(base + "/products/" + expected["product"])
        product.raise_for_status()
        if hashlib.sha256(product.content).hexdigest() != expected["product_sha256"]:
            raise ValueError("Completed product changed after restore")
        finished = connection.get(base + "/research/" + expected["run"])
        finished.raise_for_status()
        if finished.json()["status"] != "completed":
            raise ValueError("Completed job changed after restore")
        for ident in expected["pending"]:
            recovered = connection.get(base + "/research/" + ident)
            recovered.raise_for_status()
            if recovered.json()["status"] != "interrupted":
                raise ValueError("Unfinished research was not recovered as interrupted")
    db = store()
    try:
        with db.session() as session:
            products = session.scalar(select(func.count()).select_from(Record).where(Record.kind == "product"))
            if products != 1:
                raise ValueError("Unexpected product replay")
            # Decode every encrypted aggregate, not just a selected document.
            records = session.scalars(select(Record)).all()
            for record in records:
                db.decode(record)
    finally:
        db.engine.dispose()
    with httpx.Client(timeout=30, trust_env=False) as transport:
        response = transport.get("http://opensearch:9200/synthetic-recovery/_doc/sentinel")
        response.raise_for_status()
        if response.json()["_source"] != {"text": PAYLOAD.decode()}:
            raise ValueError("OpenSearch persistence mismatch")
        for family in ("structural", "jurisprudence"):
            response = transport.get(f"http://fuseki:3030/{family}/query", params={"query": "ASK { ?s ?p ?o }"},
                                     headers={"Accept": "application/sparql-results+json"})
            response.raise_for_status()
            if response.json()["boolean"] is not False:
                raise ValueError("Empty-corpus drill unexpectedly served legal triples")
    return {"authenticated": True, "original_document_decrypted": True, "encrypted_records_decoded": len(records),
            "completed_product_unchanged": True, "completed_job_unchanged": True,
            "interrupted_without_replay": len(expected["pending"]), "opensearch_document_restored": True,
            "fuseki_empty_datasets_available": 2, "historical_epoch_absent": True, "private_review_bytes_retained": True}


def main():
    require_drill()
    action = sys.argv[1]
    if action in {"inventory", "empty", "seed-volumes"}:
        from volume_archive import ROOTS, require_empty
        if action == "empty":
            require_empty()
            result = {"empty": True}
        elif action == "inventory":
            result = {"volumes": file_inventory(ROOTS),
                      "epoch_exists": (ROOTS["documents"] / "publication-epoch").is_file()}
        else:
            result = seed_volumes()
    else:
        result = {"seed": seed, "verify": verify, "code": lambda: code_fingerprint(ROOT)}[action]()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
