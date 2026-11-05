# cert-manager Operator coverage

Feature: [KONFLUX-16057](https://redhat.atlassian.net/browse/KONFLUX-16057).

The member-cluster ApplicationSet remains the existing owner of
`openshift-cert-manager-operator` Subscriptions in `cert-manager-operator`.
Application names remain `cert-manager-<cluster-name>`. Reuse those resources;
do not create another Subscription or move common clusters into this selector.

## Destinations and promotion

Development continues to select clusters labelled
`appstudio.redhat.com/member-cluster: "true"`, including dynamically named
preview clusters. Both staging roots use `cert-manager-staging-clusters` to
select only the configured staging members:

- `stone-stage-p01`
- `stone-stg-rh01`
- `lightwell-dev` (existing staging destination)
- `kflux-stg-es01`
- `kflux-stg-p02`
- `kflux-hub-stg-01`

The existing new-cluster playbook adds new staging members to this selector as
well as their source mapping and component overlay. Run its `applicationsets`
and `components` steps together; adding a registration alone does not enable
an unconfigured destination.

The staged `kflux-stg-es01` mapping is added by the staging component, so it does
not change production ApplicationSet output. Each selected cluster has its own
component overlay and exactly one rendered OperatorGroup and Subscription.
The Application uses `CreateNamespace=true` for the Operator namespace.

Production rollout is separate. Its intended member cohorts are:

| Cohort | Destinations |
| --- | --- |
| Ring 2 | `kflux-fedora-01`, `kflux-ocp-p01`, `kflux-osp-p01`, `kflux-prd-es01`, `kflux-prd-rh03`, `kflux-rhel-p01`, `stone-prod-p01`, `kflux-lw-p01` |
| Ring 3 | `stone-prd-rh01`, `stone-prod-p02` |
| Ring 4 | `kflux-prd-rh02` |

This staging change does not modify production resources. Adding the missing
`kflux-prd-es01` Operator mapping and production selection belongs to the
production follow-up, after staging evidence. Apply future version/feature
overrides in the selected per-cluster overlays, not in a shared production base.

The four common clusters are owned through
`redhat-appstudio/infra-common-deployments`: internal staging
`kflux-c-stg-i01`, external staging `kflux-c-stg-e01`, internal production
`kflux-c-prd-i01`, external production `kflux-c-prd-e01`. Their local Argo
instance must be the sole owner of their Operator installation.

## Existing settings and the upgrade-control decision

This change preserves the existing package, catalog, `stable-v1` channel,
Automatic install-plan approval and other operand settings. It does not select
a new CSV, opt into the TP trust-manager operand or create a TrustManager CR.

Automatic approval can upgrade every Subscription when a new channel release
appears, independently of GitOps rings. Per-cluster source paths alone do not
prevent that. A decision on production Manual approval or another supported
upgrade gate is pending; controlled production Operator upgrades cannot be
claimed until that gate is agreed and implemented. Do not use `startingCSV` as
an upgrade pin with Automatic approval.

## Read-only render checks

Run `python hack/test-cert-manager-coverage.py` with PyYAML and Kustomize on the
PATH, or set `KUSTOMIZE` to its executable. The workflow runs this check on
relevant PRs. It checks actual rendered source paths and prerequisites, excludes
common/production/unlisted clusters from staging and retains dynamic dev
selection. These are local render checks, not cluster E2E tests.

## Rollout and certificate-issuance evidence

Before syncing to a destination, record its cluster identity and verify:

1. Exactly one Argo Application owns the installation. Internal and public Argo
   fleets must not both own the same destination's Subscription.
2. There is no second cert-manager installation, Subscription or conflicting
   OperatorGroup. Capture current CSV, channel, approval policy, other operand
   configuration, deployment readiness and existing Certificate Ready states.
3. The selected release supports that OpenShift version. Scope any upgrade or
   feature change to the approved cohort and use the agreed install-plan gate.

After an installation/upgrade, require the intended CSV to be Succeeded and
the Operator, controller, webhook and cainjector to be ready. Compare previously
Ready certificates with their pre-upgrade states. Run the fresh issuance probe
below on the approved target; it validates controller/webhook/local issuance,
not every external issuer integration. Validate affected issuer-specific
workflows too. Record the evidence before advancing to another cohort.

```bash
set -euo pipefail
# Set this to the reviewed target context explicitly.
cm_validation_context='<approved-context>'
cm_validation_namespace="cert-manager-check-$(date -u +%Y%m%d%H%M%S)-${RANDOM}"
oc --context "$cm_validation_context" create namespace "$cm_validation_namespace"
cm_validation_uid=$(oc --context "$cm_validation_context" get namespace \
  "$cm_validation_namespace" -o jsonpath='{.metadata.uid}')

oc --context "$cm_validation_context" create -f - <<EOF
apiVersion: cert-manager.io/v1
kind: Issuer
metadata:
  name: issuance-check
  namespace: ${cm_validation_namespace}
spec:
  selfSigned: {}
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: issuance-check
  namespace: ${cm_validation_namespace}
spec:
  secretName: issuance-check-tls
  dnsNames:
    - cert-manager-check.invalid
  issuerRef:
    name: issuance-check
    kind: Issuer
EOF

oc --context "$cm_validation_context" -n "$cm_validation_namespace" \
  wait issuer/issuance-check --for=condition=Ready --timeout=60s
oc --context "$cm_validation_context" -n "$cm_validation_namespace" \
  wait certificate/issuance-check --for=condition=Ready --timeout=120s
oc --context "$cm_validation_context" -n "$cm_validation_namespace" \
  get certificate issuance-check
oc --context "$cm_validation_context" -n "$cm_validation_namespace" \
  get secret issuance-check-tls -o jsonpath='{.type}'

# Capture results before cleanup. Remove only the namespace created above.
test "$(oc --context "$cm_validation_context" get namespace \
  "$cm_validation_namespace" -o jsonpath='{.metadata.uid}')" = "$cm_validation_uid" && \
  oc --context "$cm_validation_context" delete namespace "$cm_validation_namespace"
```

If a check fails, retain the test namespace for diagnosis and stop promotion.
No live Operator upgrade or issuance result is demonstrated by rendering this PR.
