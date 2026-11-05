# cert-manager Operator coverage

Feature: [KONFLUX-16057](https://redhat.atlassian.net/browse/KONFLUX-16057).

The current implementation covers development and staging only. Production
installation, upgrades and trust-manager enablement are deferred to separate
follow-up changes after non-production validation.

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

Production resources remain unchanged. Production destinations and rollout
cohorts will be addressed in the production follow-up.

The common staging clusters are owned through
`redhat-appstudio/infra-common-deployments`: internal staging
`kflux-c-stg-i01` and external staging `kflux-c-stg-e01`. Their local Argo
instance must be the sole owner of their Operator installation. Common-cluster
production changes are also outside the current scope.

## Existing settings and upgrade control

This change preserves the existing package, catalog, `stable-v1` channel,
Automatic install-plan approval and other operand settings. It does not select
a new CSV, opt into the TP trust-manager operand or create a TrustManager CR.

Automatic approval can upgrade every Subscription when a new channel release
appears, independently of GitOps rings. Per-cluster source paths alone do not
prevent that. Production upgrade-control decisions belong to the separate
production follow-up and do not block this development/staging configuration
change. This change preserves approval settings in every environment. Do not
use `startingCSV` as an upgrade pin with Automatic approval.

## Read-only render checks

Build the affected roots and the added staging Operator overlay locally:

```bash
kustomize build argo-cd-apps/overlays/development
kustomize build argo-cd-apps/overlays/staging-downstream
kustomize build argo-cd-apps/overlays/konflux-public-staging
kustomize build components/cert-manager/staging/kflux-stg-es01
```

Review the rendered cert-manager ApplicationSet selectors and source paths.
Confirm staging includes only the configured member destinations, development
retains dynamic member selection, and each selected component overlay renders
one OperatorGroup and Subscription. Rendering does not validate live ownership
or certificate issuance.

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
