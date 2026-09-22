# Vanguard proxy regression verification (KFLUXVNGD-1358)

This suite provisions execution access for the caching repository's deployed
proxy regression tests. It uses the shared runner/target profiles rather than
extending the legacy conformance suite's broader permissions.

## Deployment scope

The suite is opt-in: `base/kustomization.yaml` and the ring-1 snapshot root do not
select it. The ring-1 `stone-stg-rh01` overlay explicitly selects the copy under
`base/base-snapshot/suites/konflux-vanguard/proxy`. The snapshot includes its own
profiles. Keep that suite copy in sync through normal snapshot promotion.
Neither p01, lightwell-dev nor any production cluster enables this suite.
Select a representative cluster for each additional ring in a separate rollout.

## Identities and permissions

| Identity | Namespace | Access |
| --- | --- | --- |
| `konflux-bot-0` | `verification-vanguard-proxy-runner` | Submit, observe, cancel and clean up outer PipelineRuns; read their TaskRuns and pod logs |
| `verification-runner` | `verification-vanguard-proxy-runner` | Read only `konflux-info/cluster-config`; create/get/delete test PipelineRuns and read pod logs in the target namespace |
| `caching-proxy-regression-build` | `verification-vanguard-proxy-tenant` | Use the existing `appstudio-pipelines-scc`; no API token mounted |

Both namespaces have the tenant label so normal CA distribution applies. Do not
create a replacement test CA ConfigMap: the test must mount the real default
`caching-ca-bundle` with the `ca-bundle.crt` key. Cluster CA Secrets are not exposed
to any of these identities. RBAC does not grant Secret reads or wildcard access.
As with the shared profile, a trusted launcher can submit arbitrary PipelineRuns
using execution identities in its namespace; these roles are not isolation from
an untrusted submitter.

## Kargo integration contract

Configure the follow-up AnalysisTemplate in infra-common-deployments to:

1. Use this cluster's launcher token to submit an outer PipelineRun in
   `verification-vanguard-proxy-runner`, using `verification-runner`.
2. Run a reviewed immutable caching test revision with:
   - `BUILD_PROXY_TEST_NAMESPACE=verification-vanguard-proxy-tenant`
   - `BUILD_PROXY_TEST_SERVICE_ACCOUNT=caching-proxy-regression-build`
   - `BUILD_PROXY_TEST_EXPECTED_PROXY=squid.container-image-proxy.svc.cluster.local:3128`
     for clusters where that endpoint is the promotion target. This is an assertion,
     not a replacement for reading cluster-config.
3. Run `go test -count=1 -timeout=40m -v ./tests/buildproxy/ -ginkgo.v`.
4. Propagate test failure, timeout and API errors to the Kargo verification result.
   Apply the shared execution contract for serialization and remote-run cleanup.

This setup does not enable an AnalysisTemplate or alter promotion gates. The
existing suite covers container image pulls and a minimal build, including a
negative CA control. An artifact-registry-proxy package-download test is still
needed; provisioning this namespace does not establish that coverage. Confirm
how cluster-config-only changes trigger verification separately from chart
Freight promotion before considering the regression gate complete.

## Credentials and rollout checks

hmariset owns launcher token provisioning and annual renewal. After the namespace
and RBAC merge and sync, issue a TokenRequest for `konflux-bot-0` in the runner
namespace and store it in the agreed Vault path for this suite/cluster. Check the
actual issued expiration: the API server can shorten the requested lifetime.
Record renewal before that expiration. No token values belong in Git, PipelineRun
parameters or logs. The Vault path and ExternalSecret mapping must be agreed with
the infra-common-deployments owner before credentials are provisioned.

Before enabling the gate, verify effective launcher/runner RBAC, the existing SCC,
and the target tenant CA ConfigMap. Then exercise both positive and negative
cases through the remote launcher. Rendering alone does not validate admission,
cluster policies, CA distribution or the complete Kargo execution path.
