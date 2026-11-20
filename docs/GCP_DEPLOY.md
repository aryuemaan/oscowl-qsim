# Deploying on Google Cloud

Two deployment shapes:

1. **Cloud Run**: the web app and API in one container. Scales to zero, so it costs almost nothing when idle. This is the demo setup.
2. **GKE batch jobs on GPU/TPU**: large simulations (big bond dimensions, many noise trajectories) run by `app.worker` with the JAX backend.

## Prerequisites (one time)

1. Create a Google Cloud project and enable billing: https://console.cloud.google.com
2. Install the gcloud CLI (Windows installer): https://cloud.google.com/sdk/docs/install
3. In Git Bash:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

## 1. Cloud Run

Optionally store the Gemini key as a secret, so it never sits in the image or the console:

```bash
printf "%s" "YOUR_GEMINI_KEY" | gcloud secrets create gemini-api-key --data-file=-
```

Deploy (builds in the cloud with Cloud Build; you do not need Docker locally):

```bash
export PROJECT_ID=your-project-id
export REGION=asia-south1          # Mumbai; or us-central1, europe-west1, ...
bash deploy/cloudrun/deploy.sh
```

The script enables the APIs, creates an Artifact Registry repository, builds the image, grants the
runtime service account access to the secret, deploys, and prints the URL.

Service settings: 2 vCPU, 2 GiB RAM, 300 s request timeout, concurrency 4, 0–5 instances, and the dense
simulator capped at 22 qubits (`SV_HARD_MAX`) to fit in memory. Raise `--memory` and `MAX_BOND_LIMIT`
for heavier interactive runs.

Update: run the same script again. Logs: `gcloud run services logs read oscowl-qsim --region $REGION`.

> If your organisation blocks `--allow-unauthenticated`, remove that flag and use
> `gcloud run services proxy oscowl-qsim --region $REGION` to open it locally.

## 2. GKE batch jobs (GPU or TPU)

Use these for runs that are too heavy for Cloud Run. The same image runs `python -m app.worker`.

```bash
export REGION=us-central1 REPO=qsim
gcloud artifacts repositories create $REPO --repository-format=docker --location $REGION   # skip if it exists
# GPU image (JAX with CUDA):
gcloud builds submit --config deploy/gke/cloudbuild-worker.yaml \
  --substitutions=_IMAGE=$REGION-docker.pkg.dev/$PROJECT_ID/$REPO/oscowl-qsim-gpu:latest,_EXTRA_PIP="jax[cuda12] google-cloud-storage" .
```

For TPU, use `_EXTRA_PIP="jax[tpu] google-cloud-storage"` and an image name ending in `oscowl-qsim-tpu:latest`.

Create a cluster with a GPU (or TPU) node pool. Accelerator availability varies by region; see the GKE GPU and TPU docs:

```bash
gcloud container clusters create-auto qsim-cluster --region $REGION    # Autopilot provisions GPU nodes on demand
gcloud container clusters get-credentials qsim-cluster --region $REGION
```

Submit a job:

```bash
kubectl create configmap qsim-job-spec --from-file=job.json=deploy/gke/job-spec.json
# edit the image line in the YAML first
kubectl apply -f deploy/gke/sim-job-gpu.yaml      # or sim-job-tpu.yaml
kubectl logs -f job/qsim-sim-gpu
```

The job spec format is documented in `backend/app/worker.py`. To keep results, add
`--out gs://YOUR_BUCKET/results/run.json` to the job command.

**Honest note on JAX:** the MPS core runs on NumPy or JAX with identical results (verified). On a
laptop CPU, NumPy is faster, because JAX dispatches many small operations one by one. JAX pays off on
GPU/TPU when the bond dimension is large (hundreds) and the contractions become big matrix multiplications.

## 3. Cost control

- Cloud Run with `--min-instances 0` costs nothing when idle.
- Delete GKE clusters after the demo: `gcloud container clusters delete qsim-cluster --region $REGION`.
- Set a billing budget alert in the console.
- The Gemini API is billed per token; the backend caches identical requests in memory.

## 4. Clean up

```bash
gcloud run services delete oscowl-qsim --region $REGION
gcloud artifacts repositories delete qsim --location $REGION
gcloud secrets delete gemini-api-key
```
