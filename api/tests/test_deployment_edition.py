import ast
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI

from api.services import deployment_edition
from api.services.deployment_edition import (
    mount_owner_control_plane,
    public_signup_enabled,
)


def test_client_edition_does_not_import_or_mount_owner_routes():
    client_router = APIRouter()

    assert mount_owner_control_plane(client_router, "client") is False
    assert client_router.routes == []


def test_saas_edition_mounts_owner_control_plane_routes():
    saas_router = APIRouter()

    assert mount_owner_control_plane(saas_router, "saas") is True
    app = FastAPI()
    app.include_router(saas_router)
    app.openapi_schema = None
    paths = app.openapi()["paths"]
    assert any(path.startswith("/admin") for path in paths)
    assert any(path.startswith("/superuser") for path in paths)


def test_admin_routes_require_superuser_except_signed_installation_status():
    routes_root = Path(__file__).resolve().parents[1] / "routes"
    admin_root = routes_root / "admin"
    route_methods = {"get", "post", "put", "patch", "delete", "websocket"}
    audited_routes = 0
    owner_modules = [
        path for path in admin_root.glob("*.py") if path.name != "__init__.py"
    ] + [routes_root / "superuser.py"]

    for source_path in owner_modules:
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            is_route = any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in route_methods
                for decorator in function.decorator_list
            )
            if not is_route:
                continue
            audited_routes += 1
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)]

            if source_path.name == "client_installation_check.py" and function.name in {
                "check_client_installation", "enroll_client_installation",
            }:
                parameter_names = {argument.arg for argument in function.args.args}
                called_names = {
                    node.func.id for node in calls if isinstance(node.func, ast.Name)
                }
                assert "authorization" in parameter_names
                required = {"load_license", "record_client_installation_check"} if function.name == "check_client_installation" else {
                    "load_license", "verify_enrollment", "consume_installation_enrollment"
                }
                assert required <= called_names
                continue

            assert any(
                isinstance(node.func, ast.Name)
                and node.func.id == "Depends"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == "get_superuser"
                for node in calls
            ), f"{source_path.name}:{function.lineno} {function.name} lacks owner authorization"

    assert audited_routes >= 50


def test_unknown_edition_is_rejected():
    with pytest.raises(ValueError, match="edition must be"):
        mount_owner_control_plane(APIRouter(), "unknown")


def test_client_image_edition_is_not_replaced_by_runtime_environment(monkeypatch):
    monkeypatch.setattr(deployment_edition, "IMAGE_EDITION", "client")
    monkeypatch.setenv("KODEWAVES_EDITION", "client")
    assert deployment_edition.runtime_edition() == "client"
    monkeypatch.setenv("KODEWAVES_EDITION", "saas")
    assert deployment_edition.runtime_edition() == "client"


def test_public_signup_is_unconditionally_disabled_for_client_editions():
    assert public_signup_enabled("client", "true") is False
    assert public_signup_enabled("client", "false") is False


def test_public_signup_follows_hosted_saas_setting():
    assert public_signup_enabled("saas", "true") is True
    assert public_signup_enabled("saas", "false") is False


def test_public_signup_rejects_unknown_edition():
    with pytest.raises(ValueError, match="edition must be"):
        public_signup_enabled("unknown", "true")
