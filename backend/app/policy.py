import hashlib
import json
import re
from urllib.parse import urlsplit

POLICY_VERSION = "edge-2026-10-v2"
PUBLIC_WORDS = set("anayasa hukuk hukuku sözleşme sözleşmesi borç borçlar ticaret ticari iş işçi işveren çalışma fesih tazminat kıdem ihbar işe iade ücret alacak temerrüt sorumluluk ayıp tüketici tüketicinin korunması kişisel veri verilerin koruma korunması medeni ceza idare idari vergi yargıtay danıştay mahkemesi mahkeme karar kararları içtihat mevzuat kanun kanunu madde maddesi m fıkra yönetmelik tebliğ anayasa aym tbk ttk hmk cmk tck tm k kvkk sgk ispat delil arabuluculuk yetki görev zamanaşımı süre teminat rehin ipotek garanti kefalet kira hizmet rekabet esas ve veya ile için hakkında usul geçici yürürlük tarihinde tarihinde\"".split())
SENSITIVE = [
    re.compile(r"\b\d{11}\b"), re.compile(r"\bTR\s?\d[\d\s]{20,}\b", re.I),
    re.compile(r"[\w.+-]+@[\w.-]+\.\w+"), re.compile(r"(?:\+90|0)[\s()-]*5\d[\d\s()-]{8,}"),
    re.compile(r"\b(?:sk-|bearer\s|api[_ -]?key|password|parola|şifre)\S*", re.I),
    re.compile(r"\b\d+[.,]\d+\s*(?:TL|TRY|EUR|USD|₺)\b", re.I),
]
INJECTION = re.compile(r"ignore (?:all |previous |the )*instructions|system prompt|önceki talimatları|talimatları (?:yok say|unut)|<script|javascript:", re.I)


def request_digest(query, destination, query_type, user_id, matter_id):
    value = [query, destination, query_type, user_id, matter_id, POLICY_VERSION]
    return hashlib.sha256(json.dumps(value, ensure_ascii=False).encode()).hexdigest()


def evaluate(query, destination, query_type, allowed_hosts):
    reasons = []
    hosts = {host.strip().lower() for host in allowed_hosts}
    try:
        url = urlsplit(destination)
        valid_origin = (
            url.scheme == "https" and url.hostname in hosts and not url.username and not url.password
            and url.port in (None, 443)
        )
        # A hostname allowlist does not constrain the URL path, which can carry
        # names, case identifiers and secrets just as readily as a query body.
        # Only the registered root endpoint is available in this initial build.
        if url.path not in ("", "/"):
            reasons.append("destination_path_not_registered")
        if url.query or url.fragment:
            reasons.append("destination_must_not_contain_query_or_fragment")
    except ValueError:
        valid_origin = False
    if not valid_origin:
        reasons.append("destination_not_allowed")
    # urlsplit normalizes some control characters. Reject the original input
    # rather than allowing that normalization to conceal an outbound payload.
    if (len(destination) > 500 or destination != destination.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in destination)
            or "\\" in destination):
        reasons.append("unsafe_destination_encoding")
    if (len(query) > 500 or not query.strip() or INJECTION.search(query)
            or not re.fullmatch(r"[^\W\d_]+(?: +[^\W\d_]+)*", query)):
        reasons.append("unsafe_query")
    if any(pattern.search(query) for pattern in SENSITIVE):
        reasons.append("sensitive_data_detected")
    # Public traffic is compiled from a closed vocabulary, not arbitrary conversation text.
    words = re.findall(r"[^\W\d_]+", query.casefold().replace("i̇", "i"))
    if any(word not in PUBLIC_WORDS for word in words):
        reasons.append("query_outside_public_legal_vocabulary")
    # Even short numeric groups can reconstruct a private identifier or date.
    # Numerical citations will need a source-bound builder before admission.
    if any(char.isnumeric() for char in query):
        reasons.append("numeric_citations_require_source_registry")
    if query_type not in ("public", "matter"):
        reasons.append("unknown_query_type")
    if reasons:
        decision = "DENY"
    elif query_type == "matter":
        decision = "REQUIRE_APPROVAL"
        reasons.append("exact_request_approval_required")
    else:
        decision = "ALLOW"
    return {"decision": decision, "reason_codes": reasons, "policy_version": POLICY_VERSION,
            "checks": ["destination", "closed_public_vocabulary", "direct_identifiers", "injection_patterns"],
            "limitations": ["Serbest metin ve kimliksizleştirildiği varsayılan dosya özetleri dışarı aktarılamaz."]}
