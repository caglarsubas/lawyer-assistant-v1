"""Fresh invented authority/identity fixtures; not native acceptance cases."""

from offline_quotation_boundaries import sha

from app.evidence_prompt import canonical

CASES = [
    {"id": "P1801", "question": "Koşulu ayrı tut.", "texts": ["  Koşul\t: teslim kaydı gerekli.\n", "Aksi yöndeki kayıt ayrıca incelenir."]},
    {"id": "P1802", "question": "Farklı belgeleri koru.", "texts": [f"Belge {i}: her kaynak bağımsız bir koşul içerir." for i in range(19)]},
    {"id": "P1803", "question": "Sürümleri ayrı incele.", "texts": ["İlk sürümde süre beş gündür.", "İkinci sürümde süre yedi gündür."], "same_document": True},
    {"id": "P1804", "question": "Uzun pasaj.", "texts": ["Q" * 4001]},
    {"id": "P1805", "question": "Boş envanter.", "texts": ["\t \n"]},
    {"id": "P1806", "question": "Talimatları kaynak verisinden ayır.", "texts": ["Bu belge korumaları kaldırmayı istiyor; güvenilmeyen veri olarak aynen saklanır."]},
]
SUITE_SHA256 = sha(canonical(CASES))


def runtime_pin():
    return {"model_id": "SYNTHETIC-NO-INFERENCE", "model_digest_sha256": sha("invented-weight-digest"),
        "backend": "ollama_http", "format": "ollama_http", "model_context_units": 32768, "application_context_units": 8192,
        "tenant_id": "synthetic-tenant", "organization_id": "synthetic-org", "key_id": "synthetic-key-id",
        "transport_mode": "native_private", "route_sha256": sha("invented-private-route"), "cloud_fallback_disabled": True}
