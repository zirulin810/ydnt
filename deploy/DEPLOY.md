# YDNT Deploayability and Cloud Run Verification Guide

> **Note**: As per the user request, the deployability documentation is fully compiled here for reproducibility and cloud-readiness, though we are not forcing live cloud deployment at this stage.

---

## 1. Local Deployment Pre-check
To verify that the agent is fully deployable without errors, run the dry-run command:
```bash
agents-cli deploy --dry-run
```
This verifies:
- Pydantic schema serializability.
- Workflow DAG loops and connectivity.
- Python packaging requirements in `pyproject.toml`.

---

## 2. Cloud Run Deployment (Google Agent Runtime)
The project utilizes the ADK Agent Runtime to run on Google Cloud Run. 

### Step 1: Set Google Cloud Project
Ensure you are authenticated and target the correct GCP project:
```bash
gcloud config set project halogen-parser-500207-k8
gcloud auth application-default login
```

### Step 2: Run Deployment
Execute the deploy command:
```bash
agents-cli deploy
```
This triggers `agents-cli` to:
1. Compile the agent into a container image.
2. Push the image to GCP Artifact Registry.
3. Deploy the service to Google Cloud Run under the name `ydnt`.
4. Return a public service URL.

---

## 3. Environment Variables configuration in Cloud Run
When running on Cloud Run, ensure the following variables are configured in the Cloud Run service environment:
- `GEMINI_API_KEY`: Set to your Google AI Studio key (if not using default Vertex AI project access).
- `YOUTUBE_API_KEY`: Set to your YouTube Data API key.
- `GITHUB_TOKEN`: Set to your GitHub personal access token (optional).
- `USE_MOCK`: Set to `0` for live mode, or `1` to run the fully reproducible mock mode in the cloud.
