# Helix Core — Deployment Runbook

**Component:** `helix_core` (the quiz registration / sealed scoring service)
**Version:** 2.1.1
**Last updated:** 2026-11-09
**Shape:** one container, one replica, one SQLite file on one volume.

This runbook describes what the manifests in `deploy/k8s/` actually do. Earlier
revisions of this file described a three-replica engine backed by PostgreSQL
and a `/metrics` endpoint; none of that exists in this codebase. If you find a
statement below that does not match the code, the code is right.

---

## 0. What you are deploying, and what you are not

| | |
|---|---|
| **Is** | A small FastAPI service around `helix_core`: register a quiz, submit an answer, read a score, read a topic projection. |
| **Is** | Stateful. The SQLite database and the sealed-key HMAC secret are the product's data. |
| **Is** | Single-writer. `replicas: 1`, `strategy: Recreate`. |
| **Is not** | Horizontally scalable. See §8 before you try. |
| **Is not** | The desktop app's backend. Study Studio spawns `helix-core` as a local sidecar; this deployment is for a hosted instance. |

The image contains `helix_core/` only. It does not contain the Ollama client,
the HTML scraper, or the CLI — those belong to the wider `helix-education`
distribution.

---

## 1. Prerequisites

- A cluster with a default `StorageClass` that provisions real block storage.
- `kubectl` pointed at that cluster.
- Docker (or Podman) to build the image locally.
- A GHCR package you can pull. The manifests reference
  `ghcr.io/hatemshalaby15071979/helix-core:2.1.1`; change the owner in
  `deployment.yaml` and `kustomization.yaml` if you fork.
- If the package is private, an image pull secret in `helix-education`:

  ```bash
  kubectl -n helix-education create secret docker-registry ghcr-pull \
    --docker-server=ghcr.io \
    --docker-username=<github-user> \
    --docker-password=<PAT-with-read:packages>
  kubectl -n helix-education patch serviceaccount default \
    -p '{"imagePullSecrets":[{"name":"ghcr-pull"}]}'
  ```

---

## 2. Build and publish the image

The image is built and pushed by `.github/workflows/docker.yml` on every push
to `main` and on `v*` tags. To build locally:

```bash
docker build -t helix-core:2.1.1 .
docker run --rm -p 127.0.0.1:8765:8000 \
  -e HELIX_CORE_SECRET=dev-secret \
  -e HELIX_CORE_TOKEN=dev-token \
  helix-core:2.1.1
curl -s http://127.0.0.1:8765/v1/health
# {"status":"ok","version":"2.1.1","events":0}
```

To push manually:

```bash
docker tag helix-core:2.1.1 ghcr.io/<owner>/helix-core:2.1.1
docker push ghcr.io/<owner>/helix-core:2.1.1
```

---

## 3. Create the namespace and the secret

The namespace is in `namespace.yaml`. Apply it first — the secret has to land
in it.

```bash
kubectl apply -f deploy/k8s/namespace.yaml
```

Then create the secret. **Do not** apply `secret.example.yaml`; it is a
template with placeholder values.

```bash
kubectl -n helix-education create secret generic helix-core-secrets \
  --from-literal=token="$(openssl rand -hex 32)" \
  --from-literal=sealed-key-secret="$(openssl rand -hex 32)"
```

Two things worth understanding before you do this:

- `token` becomes `HELIX_CORE_TOKEN` and is required on every endpoint except
  `/v1/health`. Generate it; do not invent one.
- `sealed-key-secret` becomes `HELIX_CORE_SECRET` and is the HMAC key that
  authenticates every sealed answer key. **It is part of the data, not a
  password.** If you lose it or rotate it without re-sealing, every quiz
  registered under the old value becomes unscoreable — `submit_answer` raises
  `TamperError` and the API returns 409. Back it up in the same place you back
  up the database, and rotate only with a re-seal migration.

Record the token somewhere you can reach it:

```bash
kubectl -n helix-education get secret helix-core-secrets \
  -o jsonpath='{.data.token}' | base64 -d; echo
```

---

## 4. Apply

```bash
kubectl apply -k deploy/k8s
```

That applies, in order: namespace, PVC, Deployment, Service. It deliberately
does **not** apply the Ingress — `ingress.yaml` carries a placeholder host and
would create a broken route. Apply it separately once you have a real hostname
(§7).

Watch the rollout:

```bash
kubectl -n helix-education rollout status deploy/helix-core --timeout=300s
kubectl -n helix-education get pods -l app.kubernetes.io/name=helix-core -w
```

Expected: one pod, `1/1 Running`, no restarts after the first minute.

---

## 5. Verify

### 5.1 Health

```bash
kubectl -n helix-education port-forward svc/helix-core 8080:80 &
curl -s http://127.0.0.1:8080/v1/health
# {"status":"ok","version":"2.1.1","events":<n>}
```

`/v1/health` is unauthenticated on purpose — it is the probe target and it
returns no data.

### 5.2 End-to-end: register, answer, score

```bash
TOKEN=$(kubectl -n helix-education get secret helix-core-secrets -o jsonpath='{.data.token}' | base64 -d)

QUIZ=$(curl -s -X POST http://127.0.0.1:8080/v1/quizzes \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"topic":"smoke","items":[{"question":"2+2?","options":["3","4"],"correct_index":1,"explanation":"Four."}]}')

echo "$QUIZ" | grep -q correct_index && echo "FAIL: key leaked" || echo "OK: keys hidden"

QUIZ_ID=$(echo "$QUIZ" | python3 -c 'import json,sys;print(json.load(sys.stdin)["quiz_id"])')
ITEM_ID=$(echo "$QUIZ" | python3 -c 'import json,sys;print(json.load(sys.stdin)["items"][0]["item_id"])')

curl -s -X POST "http://127.0.0.1:8080/v1/quizzes/$QUIZ_ID/answers" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"item_id\":\"$ITEM_ID\",\"selected_index\":1}"
# {"item_id":"...","correct":true,"correct_index":1,"explanation":"Four."}

curl -s "http://127.0.0.1:8080/v1/quizzes/$QUIZ_ID/score" -H "Authorization: Bearer $TOKEN"
# {"quiz_id":"...","total":1,"answered":1,"correct":1,"percentage":100,...}
```

Three things to confirm in that output:

1. The registration response contains no `correct_index` and no `explanation`.
2. The answer response contains both — that is the only moment a key is revealed.
3. The score is `100`.

### 5.3 Auth is actually enforced

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://127.0.0.1:8080/v1/quizzes \
  -H "Content-Type: application/json" -d '{"topic":"x","items":[]}'
# 401
```

### 5.4 Persistence survives a restart

```bash
kubectl -n helix-education delete pod -l app.kubernetes.io/name=helix-core
kubectl -n helix-education rollout status deploy/helix-core
# re-run 5.2's score call with the same QUIZ_ID — the score must still be there
```

If the score is gone, the PVC is not mounted and the database is inside the
container. Check `kubectl -n helix-education describe pod` for the volume mount.

---

## 6. Upgrade and rollback

Upgrades are a full pod replacement, not a rolling update — there is one
writer.

```bash
kubectl -n helix-education set image deploy/helix-core \
  helix-core=ghcr.io/<owner>/helix-core:2.1.1
kubectl -n helix-education rollout status deploy/helix-core
```

Rollback:

```bash
kubectl -n helix-education rollout undo deploy/helix-core
kubectl -n helix-education rollout status deploy/helix-core
```

`revisionHistoryLimit: 3` keeps three ReplicaSets, so `undo` works for the last
three releases.

**Schema changes are not covered by `rollout undo`.** If a new version changes
the SQLite schema, rolling the image back does not roll the data back. Take a
backup (§7.2) before any upgrade that touches `packages/helix-core/helix_core/store.py`.

---

## 7. Operations

### 7.1 Logs

```bash
kubectl -n helix-education logs deploy/helix-core -f
```

Uvicorn access logs go to stdout. There is no `/metrics` endpoint and no
OpenTelemetry wiring; do not look for them.

### 7.2 Backup

The whole state is one file plus one secret. Back up both.

```bash
# consistent SQLite copy while the service is running
kubectl -n helix-education exec deploy/helix-core -- \
  python -c "import sqlite3;src=sqlite3.connect('/data/core.db');dst=sqlite3.connect('/data/backup.db');src.backup(dst);dst.close();src.close()"
kubectl -n helix-education cp helix-core-<pod>:/data/backup.db ./core-$(date +%F).db

# the HMAC secret, separately
kubectl -n helix-education get secret helix-core-secrets -o yaml > helix-core-secrets.$(date +%F).yaml
```

Do not `cp /data/core.db` directly while the service is writing — WAL means
the main file alone is not a consistent snapshot. The `sqlite3.backup()` call
above is.

### 7.3 Restore

```bash
kubectl -n helix-education scale deploy/helix-core --replicas=0
kubectl -n helix-education cp ./core-2026-11-09.db helix-core-<pod>:/data/core.db   # pod must exist
kubectl -n helix-education scale deploy/helix-core --replicas=1
```

With `replicas: 0` there is no pod to `cp` into. Either restore through a
throwaway pod that mounts the PVC, or stop the container and copy over the
volume directly. Whichever you use, restore the **matching** secret from
§7.2 — a database paired with the wrong `sealed-key-secret` fails every
`reveal()` with 409.

### 7.4 Node drains

There is no PodDisruptionBudget, deliberately: with one replica, a PDB with
`minAvailable: 1` would block every drain forever. Draining the node means
downtime for the service. Schedule it.

---

## 8. Scaling beyond one replica

Do not raise `replicas`. Two pods on one `ReadWriteOnce` volume will not both
start; two pods on a `ReadWriteMany` volume will corrupt the database.

The store is behind a narrow interface (`SqliteEventStore` in
`packages/helix-core/helix_core/store.py`), so the real path is:

1. Implement `PostgresEventStore` with the same methods (`append`,
   `read_all`, `read_since`, `count_events`, `transaction`).
2. Move `quizzes`, `quiz_items`, `sealed_keys` and `answers` to the same
   database, keeping the append-only trigger semantics as constraints.
3. Select the store by URL scheme in `LearningCore.__init__`.
4. Only then: `replicas: 3`, a `RollingUpdate` strategy, and a PDB.

Until that exists, one replica is the correct number, and it is enough for the
workload this service is built for.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Pod `CreateContainerConfigError` | `helix-core-secrets` missing or missing a key | Re-run §3 |
| Pod `Pending`, event "no persistent volumes available" | No default StorageClass, or the PVC is bound elsewhere | `kubectl get sc`, set `storageClassName` in `pvc.yaml` |
| Pod `CrashLoopBackOff`, log `PermissionError: /data/core.db` | `fsGroup` mismatch on the volume | Confirm `fsGroup: 10001` and that the CSI driver honours it |
| `401` on every call | Wrong or missing `Authorization: Bearer` header | Re-read the token from the secret (§3) |
| `409` with "sealed key failed verification" | `HELIX_CORE_SECRET` changed since the quiz was registered | Restore the original secret; do not "fix" it by re-registering |
| Health probe fails but the container is up | Bound to `127.0.0.1` inside the container | The image already passes `--host 0.0.0.0`; check you did not override `CMD` |
| Image pull `403` | Private GHCR package, no pull secret | §1 |

---

## 10. What this runbook deliberately does not claim

- No penetration test has been performed. The service has never been exposed
  to the internet.
- No SLO has been measured. The resource requests are a starting point, not a
  capacity plan.
- No multi-region, no HA, no autoscaling. One pod, one volume.
- `docs/S000-03_KMS_MIGRATION_PLAN.md` describes a KMS-backed key store that
  is not implemented; the sealed keys use an HMAC secret from the environment.
