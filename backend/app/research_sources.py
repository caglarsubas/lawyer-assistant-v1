"""Saved source nominations remain quote evidence, never legal conclusions."""

from datetime import date

from rdflib import URIRef

from .source_corpus import RECIPE, _project


def validate_retained(release, candidates, info):
    """Caller holds the current release guard; never cache a source verdict."""
    if not isinstance(candidates, dict) or not isinstance(candidates.get("hits"), list):
        raise ValueError("Invalid retained source nominations")
    hits, snapshot = candidates["hits"], candidates.get("snapshot")
    if not isinstance(snapshot, dict) or len(hits) > 50:
        raise ValueError("Invalid retained source snapshot")
    if snapshot.get("release_id") is None and not hits:
        return
    expected = {"recipe": RECIPE, "backend": "local_signed_evidence", "release_id": info["release_id"],
        "serving_sha256": info["serving_sha256"], "ontology_sha256": info["ontology_sha256"],
        "activation_sequence": info["pointer"]["sequence"]}
    if any(snapshot.get(key) != value or type(snapshot.get(key)) is not type(value) for key, value in expected.items()):
        raise ValueError("Retained source release changed")
    point = snapshot.get("as_of")
    if point is not None and (not isinstance(point, str) or date.fromisoformat(point).isoformat() != point):
        raise ValueError("Invalid retained source date")
    identities = set()
    for hit in hits:
        if not isinstance(hit, dict) or not isinstance(hit.get("passage_id"), str):
            raise ValueError("Invalid retained source identity")
        node = URIRef(hit["passage_id"])
        if len(hit["passage_id"]) > 512 or not release._evidence_eligible(release._resources, node):
            raise ValueError("Retained passage is outside the released public source")
        projected = _project(release, node)
        if (set(hit) != set(projected) | {"score", "channels"}
                or any(hit.get(key) != value or type(hit.get(key)) is not type(value) for key, value in projected.items())
                or type(hit["score"]) is not int or not 0 <= hit["score"] <= 4000
                or hit["channels"] != ["source_lexical"]
                or hit["passage_id"] in identities):
            raise ValueError("Retained passage does not match its exact signed source")
        identities.add(hit["passage_id"])
    coverage = candidates.get("coverage")
    if (not isinstance(coverage, dict) or type(coverage.get("returned_hits")) is not int
            or coverage.get("returned_hits") != len(hits)):
        raise ValueError("Invalid retained source coverage")


def export_lines(candidates):
    """Called only after validate_retained within the held product guard."""
    if not candidates:
        return []
    lines = ["Bağımsız kamu kaynak pasajları — avukat incelemesi için adaylar",
        "Kaynak alıntısı hukuki uygulanabilirlik, bağlayıcılık veya içtihat etkisi oluşturmaz. Tarih ve kesinleşme ayrıca incelenmelidir.",
        "Alıntı özeti özgün UTF-8 metnini adresler. Belge düzeninde satır sonları dönüştürülebilir; özgün boşluk ve satır sonları için kaynak pasajını inceleyin."]
    for hit in candidates["hits"]:
        lines.extend([hit["text"], "Pasaj: " + hit["passage_id"], "Konum: " + hit["locator"],
            "Kaynak: " + hit["document_id"], "Kaynak sürümü: " + hit["source_version_id"],
            "Kaynak SHA-256: " + hit["source_sha256"], "Metin SHA-256: " + hit["text_sha256"],
            "Konum haritası SHA-256: " + hit["locator_map_sha256"], "Alıntı SHA-256: " + hit["quote_sha256"],
            f"Unicode alıntı aralığı: [{hit['start_offset']}, {hit['end_offset']})",
            "Yayın sürümü: " + hit["release_id"], "Otorite çözümlemesi ve hukuki uygulanabilirlik: değerlendirilmedi"])
    coverage = candidates["coverage"]
    lines.extend(["Kapsam: yalnızca yayımlanan kanıt pasajları; ulusal derlemin tamlığı bilinmiyor.",
        f"Kaynak taraması: {coverage.get('scanned_passages', 'bilinmiyor')}; dönen aday: {len(candidates['hits'])}; durum: {coverage['status']}",
        *candidates["limitations"]])
    return lines
