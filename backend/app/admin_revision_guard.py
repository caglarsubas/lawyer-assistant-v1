"""Require the employee and selected role state that the administrator reviewed."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import Field, model_validator
from sqlalchemy import select

from .auth import authenticate
from .db import Employee, User
from .firm_admin import EmployeeEdit, _roles
from .firm_rbac import require_permission

EMPLOYEE_EDIT_PATH = "/api/v1/firm-admin/employees/{user_id}"


class BoundEmployeeEdit(EmployeeEdit):
    expected_active: bool
    expected_role_revisions: dict[Annotated[str, Field(min_length=1, max_length=64)],
                                  Annotated[int, Field(ge=1)]] = Field(max_length=20)

    @model_validator(mode="after")
    def match_selected_roles(self):
        if self.expected_role_revisions.keys() != set(self.role_ids):
            raise ValueError("Seçilen rollerin tüm güncel sürümleri gerekli")
        return self


def install_admin_revision_guard(app):
    # FastAPI may keep directly included routers as deferred entries.
    included = [getattr(route, "original_router", None) for route in app.router.routes]
    routers = [app.router, *(router for router in included if isinstance(router, APIRouter))]
    routes = [(router, route) for router in routers for route in router.routes if isinstance(route, APIRoute)
              and route.path == EMPLOYEE_EDIT_PATH and "PUT" in route.methods]
    if len(routes) != 1 or routes[0][1].methods != {"PUT"} or routes[0][1].name != "edit_employee":
        raise RuntimeError("Employee edit route identity is unavailable")
    router, original = routes[0]

    def edit_employee(user_id: str, body: BoundEmployeeEdit, request: Request, user=Depends(authenticate)):
        # Authentication holds the exclusive firm guard through the entire response.
        # Role changes and the offline employee operator use the same lock.
        with request.app.state.store.session() as session:
            require_permission(session, user, "firm.manage")
            current = session.execute(select(Employee.revision, User.active).join(
                User, User.id == Employee.user_id
            ).where(Employee.user_id == user_id, Employee.firm_id == user.firm_id,
                    User.firm_id == user.firm_id)).one_or_none()
            if current is None:
                raise HTTPException(404, "Çalışan bulunamadı")
            unchanged = current.revision == body.revision and current.active == body.expected_active
            if unchanged:
                roles = _roles(session, user.firm_id, body.role_ids)
                unchanged = all(role.revision == body.expected_role_revisions[role.id] for role in roles)
        if unchanged:
            return original.endpoint(user_id, body, request, user)
        return JSONResponse(status_code=409, content={
            "detail": "Çalışan veya seçili roller değişti; güncel kaydı açın.",
            "outcome": "revision_conflict",
            "target": "employee",
            "target_id": user_id,
            "current_revision": current.revision,
        })

    # The original router already prefixes paths added through add_api_route.
    router.routes.remove(original)
    router.add_api_route(EMPLOYEE_EDIT_PATH.removeprefix(router.prefix), edit_employee,
                         methods=["PUT"], name=original.name, tags=original.tags[len(router.tags):])
