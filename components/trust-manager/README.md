# Trust-manager

[KFLUXVNGD-1481](https://redhat.atlassian.net/browse/KFLUXVNGD-1481) prepares
development and staging for the cert-manager Operator-managed operand.

| Ring | Desired state | Operand requests and limits |
| --- | --- | --- |
| 0 (development) | `TrustManager/cluster` | 25m CPU / 64Mi memory |
| 1 (staging) | `TrustManager/cluster` | 100m CPU / 256Mi memory |
| 2–4 (production) | Existing Helm chart | Unchanged |

The singleton is cluster-scoped and reads CA sources from `cert-manager`.
The Operator chooses its Red Hat operand image. Secret targets remain disabled.
Helm replica, leader-election and Debian package-container settings have no
equivalent in this CR and are not carried over. The existing staging allocation
is retained; the migration does not reduce resources.

`defaultCAPackage.policy: Enabled` supplies OpenShift's injected CA bundle to
`useDefaultCAs` sources. This replaces the chart's Debian package, so compare
required roots and validate consumers during rollout. Bundle definitions remain
in their existing components, including `cert-manager-trusted-ca`.
See the [Red Hat TrustManager API documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.19/html/security_and_compliance/cert-manager-operator-for-red-hat-openshift#cert-manager-trust-manager).

## Prerequisites and promotion

Preservation, ownership handoff, rollback and safe GitOps resumption belong to
[KFLUXVNGD-1482](https://redhat.atlassian.net/browse/KFLUXVNGD-1482).
This replacement depends on [preservation PR #15725](https://github.com/redhat-appstudio/infra-deployments/pull/15725),
then [Operator enablement PR #15726](https://github.com/redhat-appstudio/infra-deployments/pull/15726).
Their live verification must complete before this replacement is merged:

- Confirm automated trust-manager sync is disabled and the live Bundle CRD retains
  `Prune=false,Delete=false` after its Helm source/patch is removed.
- Confirm a compatible successful Operator CSV, the Subscription opt-in
  `UNSUPPORTED_ADDON_FEATURES=TrustManager=true`, and an established TrustManager
  CRD. `SkipDryRunOnMissingResource` does not install or enable the Operator.
- Perform the reviewed handoff without prune and without concurrent Bundle
  writers. Apply the stop/rollback conditions and GitOps resumption checks owned
  by KFLUXVNGD-1482; preserve existing CA objects and their identities.
- Validate development before staging, including required CA roots, consumer TLS,
  fresh Bundle reconciliation and operand stability.

Production rings retain their existing configuration. Existing destination
selectors are retained; EaaS and common-cluster coverage are not added here.
The `kflux-spoke-stg-01a` and `kflux-spoke-stg-01b` overlays remain intentionally
empty; the other existing ring-1 cluster overlays inherit the singleton.

## New clusters

`hack/new-cluster` creates `rings/<ring>/<cluster>/kustomization.yaml` referencing
`../base` and adds the cluster to the environment's tenant list. New staging
clusters therefore inherit the singleton and retained staging allocation, while
new production clusters continue to inherit their unpromoted Helm base. Follow
Operator → operand/default CA readiness → Bundles ordering for staging bootstrap.
Fresh clusters do not need the old-chart ownership handoff.

## Local checks

Render every ring-0/ring-1 base and cluster overlay with
`kustomize build --enable-helm`, plus `argo-cd-apps/overlays/rd-dev` and
`argo-cd-apps/overlays/rd-staging`. Each promoted component render must contain
exactly one `TrustManager/cluster`, no workload or image override, and the resource
profile above. Check the generated ApplicationSets still use their existing
destinations and have no automatic sync policy. Run `yamllint --no-warnings .`
and `kube-linter lint` on the rendered YAML. An offline onboarding fixture should
exercise the actual component and cluster-list tasks for staging and production,
then render the generated trust-manager overlays to verify their ring selection.
The two intentionally empty staging spoke overlays must continue rendering no resources.
