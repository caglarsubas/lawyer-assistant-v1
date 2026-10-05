"""Authenticated live checks; readiness is not legal or production qualification."""
from fastapi import APIRouter, Depends, Request

from .auth import authenticate
from .db import now
from .scanner import probe_scanner


def intake_readiness(app):
    settings = app.state.settings
    if settings.demo_mode:
        return {"status": "ready", "demo_mode": True,
                "issues": [{"code": "synthetic_demo_only", "message": "Sentetik geliştirme modu: gerçek müvekkil belgesi yüklemeyin."}],
                "scanner": {"status": "demo-bypass"}, "extractor": {"status": "demo-local"}, "checked_at": now()}
    scanner = probe_scanner(settings.clamav_host, port=settings.clamav_port,
                            timeout_seconds=3, max_signature_age_days=settings.scanner_max_signature_age_days)
    extractor = (app.state.extractor.probe() if app.state.extractor else {
        "status": "blocked", "issues": [{"code": "extractor_missing", "message": "Yalıtılmış belge işleme hizmeti yapılandırılmadı."}],
    })
    states = {scanner["status"], extractor["status"]}
    status = "ready" if states == {"ready"} else "blocked" if "blocked" in states else "unavailable"
    return {"status": status, "demo_mode": False, "scanner": scanner, "extractor": extractor,
            "issues": scanner.get("issues", []) + extractor.get("issues", []), "checked_at": now()}


def readiness_router():
    router = APIRouter(prefix="/api/v1", tags=["readiness"])

    @router.get("/intake/readiness")
    def intake(request: Request, user=Depends(authenticate)):
        result = intake_readiness(request.app)
        authenticate(request)  # A slow upstream must not extend a revoked session.
        return result

    @router.get("/readiness")
    def readiness(request: Request, user=Depends(authenticate)):
        provider = request.app.state.provider
        observed = provider.probe()
        static_ready = provider.readiness()["configuration_ready"]
        checks = observed.get("checks", {"configuration": static_ready,
                                         "connection": observed["ready"], "model": observed["ready"]})
        result = {
            "checked_at": now(),
            "provider": {"status": "ready" if observed["ready"] else "blocked" if not static_ready else "unavailable",
                         "issues": observed.get("issues", []), "checks": checks,
                         'transport': provider.transport_metadata(),
                         "qualification": "runtime-connectivity-only"},
            "intake": intake_readiness(request.app),
            "limitations": ["Bağlantı denetimi model çıktısının hukuki doğruluğunu, dosya güvenliğini veya çıkarım kalitesini garanti etmez.",
                            "Yüklenen her dosya için zorunlu tarama ve erişim denetimleri yeniden uygulanır."],
        }
        model = observed.get("model")
        if isinstance(model, dict) and isinstance(model.get("id"), str):
            result["provider"]["model"] = model["id"]
        authenticate(request)
        return result

    return router
