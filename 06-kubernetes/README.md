# DataNexus Era 3 — Helm Chart

Production Helm chart for the DataNexus API service. Deploys a hardened,
auto-scaling, observable FastAPI service on Kubernetes (target: AWS EKS Mumbai).

## What's included

| Resource | Purpose |
|---|---|
| Deployment | Rolling updates, 3 replicas baseline, anti-affinity across zones |
| Service | ClusterIP on port 8000 |
| Ingress | nginx + cert-manager TLS termination |
| ConfigMap | All non-secret env vars |
| Secret | JWT key, Postgres DSN, Atlas/Airflow passwords (replace in prod) |
| HPA | CPU + memory based, 3-20 replicas |
| PDB | minAvailable: 2 (survives node drain) |
| NetworkPolicy | Locked-down ingress and egress |
| ServiceAccount | IRSA-ready for AWS IAM role |
| ServiceMonitor | Prometheus scraping |

## Security posture

- Non-root user (UID 1000)
- Read-only root filesystem (writable `/tmp` via emptyDir)
- All Linux capabilities dropped
- `seccomp: RuntimeDefault`
- No privilege escalation allowed
- NetworkPolicy restricts traffic to ingress controller + monitoring

## Quick deploy

```bash
# Add your container registry secret
kubectl create secret docker-registry datanexus-registry \
    --docker-server=your-registry.com \
    --docker-username=YOUR_USER \
    --docker-password=YOUR_PASS

# Generate a real JWT secret
JWT_KEY=$(openssl rand -hex 32)

# Install the chart
helm upgrade --install datanexus ./era3/k8s \
    --namespace datanexus \
    --create-namespace \
    --set image.repository=YOUR_REGISTRY/datanexus-api \
    --set image.tag=3.0.0-era3 \
    --set ingress.hosts[0].host=api.yourdomain.com \
    --set "secrets.jwtSecretKey=${JWT_KEY}"
```

## Production deployment (AWS EKS Mumbai)

1. **Create the EKS cluster** (eksctl recommended):
   ```bash
   eksctl create cluster -f eks-cluster.yaml
   ```

2. **Install required platform components**:
   - nginx-ingress controller
   - cert-manager (Let's Encrypt)
   - kube-prometheus-stack (monitoring)
   - external-secrets-operator (for AWS Secrets Manager integration)

3. **Create IAM role for IRSA**:
   ```bash
   eksctl create iamserviceaccount \
       --cluster=datanexus-prod \
       --namespace=datanexus \
       --name=datanexus-api \
       --attach-policy-arn=arn:aws:iam::ACCOUNT:policy/datanexus-api-policy \
       --approve
   ```

4. **Override `values.yaml` with production settings**:
   ```yaml
   serviceAccount:
     annotations:
       eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/datanexus-api-role
   ingress:
     hosts:
       - host: api.datanexus.io
   ```

5. **Verify**:
   ```bash
   kubectl -n datanexus get pods,svc,ingress,hpa
   curl https://api.datanexus.io/health
   ```

## Helm template validation

```bash
# Lint the chart
helm lint era3/k8s/

# Render templates without installing
helm template datanexus era3/k8s/ --debug

# Test against a real cluster (dry-run)
helm install datanexus era3/k8s/ --dry-run --namespace datanexus
```

## Upgrade strategy

The chart uses `RollingUpdate` with `maxSurge: 1, maxUnavailable: 0`.
This means a 3-replica deployment will scale to 4 during upgrade, then back to 3 — no downtime.

```bash
helm upgrade datanexus era3/k8s/ --namespace datanexus --reuse-values --set image.tag=NEW_TAG
```

## Rollback

```bash
helm rollback datanexus --namespace datanexus
```

---

DataNexus · datanexus.io · Apache 2.0
