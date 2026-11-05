#!/usr/bin/env python3
"""Render and check member-cluster Operator destinations without cluster access."""

import os
from pathlib import Path
import re
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[1]
KUSTOMIZE = os.environ.get("KUSTOMIZE", "kustomize")


def render(path):
    output = subprocess.check_output(
        [KUSTOMIZE, "build", str(ROOT / path)], text=True
    )
    return [item for item in yaml.safe_load_all(output) if item]


def matches(selector, parameters):
    if any(parameters.get(key) != value for key, value in selector.get("matchLabels", {}).items()):
        return False
    for expression in selector.get("matchExpressions", []):
        key, operator = expression["key"], expression["operator"]
        value, values = parameters.get(key), expression.get("values", [])
        if operator == "In" and value not in values:
            return False
        if operator == "NotIn" and value in values:
            return False
        if operator == "Exists" and key not in parameters:
            return False
        if operator == "DoesNotExist" and key in parameters:
            return False
        assert operator in {"In", "NotIn", "Exists", "DoesNotExist"}, operator
    return True


def generate(app, name, member=True):
    generator = app["spec"]["generators"][0]
    clusters, overrides = generator["merge"]["generators"]
    labels = {"appstudio.redhat.com/member-cluster": "true"} if member else {}
    if not matches(clusters["clusters"]["selector"], labels):
        return None
    parameters = {
        "nameNormalized": name,
        "server": f"https://api.{name}.example:6443",
        **{f"values.{key}": value for key, value in clusters["clusters"]["values"].items()},
    }
    for item in overrides["list"]["elements"]:
        if item["nameNormalized"] == name:
            parameters.update(item)
    if not matches(generator.get("selector", {}), parameters):
        return None
    template = app["spec"]["template"]
    path = re.sub(
        r"{{\s*([^{} ]+)\s*}}",
        lambda match: parameters[match.group(1)],
        template["spec"]["source"]["path"],
    )
    assert "{{" not in path
    return path


def main():
    tenant_list = yaml.safe_load(
        (ROOT / "argo-cd-apps/k-components/deploy-to-all-staging-clusters/all-clusters-list-patch.yaml").read_text()
    )[0]["value"]
    expected = {item["nameNormalized"] for item in tenant_list} | {"lightwell-dev"}
    for overlay in ("staging-downstream", "konflux-public-staging"):
        resources = render(f"argo-cd-apps/overlays/{overlay}")
        apps = [item for item in resources if item.get("kind") == "ApplicationSet" and item["metadata"]["name"] == "cert-manager"]
        assert len(apps) == 1, overlay
        app = apps[0]
        for name in sorted(expected):
            path = generate(app, name)
            assert path == f"components/cert-manager/staging/{name}", (overlay, name, path)
            objects = render(path)
            for kind in ("OperatorGroup", "Subscription"):
                matches_kind = [obj for obj in objects if obj["kind"] == kind]
                assert len(matches_kind) == 1, (name, kind)
                assert matches_kind[0]["metadata"]["name"] == "openshift-cert-manager-operator"
                assert matches_kind[0]["metadata"]["namespace"] == "cert-manager-operator"
        for name in ("stone-prod-p01", "kflux-c-stg-i01", "kflux-c-stg-e01", "unlisted-member"):
            assert generate(app, name) is None, (overlay, name)
        assert generate(app, "stone-stage-p01", member=False) is None
        print(f"PASS {overlay}: {len(expected)} explicit member destinations; common/production/unlisted clusters excluded")
    development = next(
        item for item in render("argo-cd-apps/overlays/development")
        if item.get("kind") == "ApplicationSet" and item["metadata"]["name"] == "cert-manager"
    )
    assert generate(development, "preview-example").rstrip("/") == "components/cert-manager/development"
    assert generate(development, "preview-example", member=False) is None
    render("components/cert-manager/development")
    print("PASS dynamic development members remain supported")


if __name__ == "__main__":
    main()
