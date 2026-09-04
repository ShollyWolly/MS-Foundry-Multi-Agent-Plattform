# Multi-Agent Platform on Azure AI Foundry

Bootstrap stack: a resource group + Foundry account/project + one model deployment + Cosmos DB
(provisioned via Terraform), a Foundry Agent on top of it, and a chat webapp (Microsoft's
[`foundry-agent-webapp`](https://github.com/microsoft-foundry/foundry-agent-webapp) sample)
running locally in Docker, talking to that agent with per-user conversation history.

Agent **tool support is intentionally deferred** (Bing Grounding, Azure AI Search, custom
function calling) — see `CLAUDE.md`'s "Deferred work" section before considering this done.

Real Entra ID login isn't wired up yet — the deployment service principal has no Microsoft
Graph app-registration permissions, so it can't provision the SPA app registration MSAL needs.
The webapp instead runs in `AUTH_MODE=mock` (a simple username/password check against `.env`).
The original Entra/MSAL code is untouched and still there — see `webapp/backend/WebApp.Api/Program.cs`
and `webapp/frontend/src/App.tsx` — switching back to real Entra ID later is a config change
(unset `AUTH_MODE` / `VITE_AUTH_MODE`, or set them to `entra`), not a re-implementation.

## Layout

```
infra/terraform/   Azure resources: resource group, Foundry account + project, model deployment, Cosmos DB, RBAC
infra/scripts/      create_agent.py — creates the Foundry Agent (data-plane, not an ARM resource)
webapp/             vendored + additively-patched foundry-agent-webapp
docker-compose.yml  runs the webapp locally
```

## Usage

1. **Provision the Azure resources:**

   ```sh
   cd infra/terraform
   cp terraform.tfvars.example terraform.tfvars   # fill in subscription_id / service_principal_client_id
   export ARM_CLIENT_ID=... ARM_CLIENT_SECRET=... ARM_TENANT_ID=... ARM_SUBSCRIPTION_ID=...
   terraform init
   terraform apply
   ```

2. **Create the Foundry Agent** (data-plane call, not something Terraform can manage):

   ```sh
   conda env create -f infra/scripts/environment.yml   # first time only
   conda activate multi-agent-platform
   export AZURE_CLIENT_ID=... AZURE_CLIENT_SECRET=... AZURE_TENANT_ID=...
   python infra/scripts/create_agent.py
   ```

   This writes `AI_AGENT_ENDPOINT` / `AI_AGENT_ID` / `COSMOS_*` to `infra/scripts/.generated.env`
   — a generated, gitignored file, kept separate from the hand-maintained root `.env` on purpose
   (a script should never mutate the config file you edit by hand). It retries for a few minutes
   if it hits `PermissionDenied`, since the RBAC role Terraform just granted can take a while to
   propagate.

3. **Fill in `.env`** (copy from `.env.example` if you haven't already):

   ```sh
   cp .env.example .env   # if not already present
   # set AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID (same SP as above)
   # set MOCK_AUTH_USERNAME / MOCK_AUTH_PASSWORD to whatever you want to log in with
   ```

4. **Run the webapp:**

   ```sh
   docker compose up --build
   ```

   `docker-compose.yml` loads both `.env` and `infra/scripts/.generated.env`. Open
   http://localhost:8080, sign in with your `MOCK_AUTH_USERNAME` / `MOCK_AUTH_PASSWORD`, and chat
   with the agent. Conversations are private per logged-in username (Cosmos-backed) — log in as a
   different `MOCK_AUTH_USERNAME` to see a separate, empty conversation list.

## Notes

- Model deployment defaults to `gpt-5-mini`; region defaults to `swedencentral`. Both, along with
  every resource name, are Terraform variables — see `infra/terraform/variables.tf`.
- The `azurerm_role_assignment` grants the service principal the **Foundry User** role at the
  project scope — the role Microsoft's docs describe as the minimum for creating/using agents
  (older docs call it "Azure AI User"; it won't show up if you grep `az role definition list`
  for "AI" or "Cognitive" by name, only by exact match). If your tenant differs, adjust
  `role_definition_name` in `infra/terraform/main.tf`.
- The `gpt-5-mini` deployment defaults to the **DataZoneStandard** SKU, not GlobalStandard —
  this subscription's GlobalStandard quota for `gpt-5-mini` in `swedencentral` was already fully
  used (3000/3000) at provisioning time. Change `model_sku_name` if you have GlobalStandard quota
  elsewhere.
- Re-running `create_agent.py` with the same `--name` creates a new *version* of the same named
  agent (the current Foundry Agents API is versioned, not the classic Assistants API) — safe to
  re-run.
- Cosmos DB stores conversation *metadata* only (id, title, owner, timestamps) — actual message
  content still lives in Foundry's own Conversations API. This is what makes per-user conversation
  lists possible (Foundry's own store is agent-scoped, not user-scoped). Deleting a conversation
  soft-deletes the Cosmos record; the underlying Foundry conversation isn't removed.
- See the repo's `CLAUDE.md` for the SDK-choice direction (Microsoft Agent Framework → Foundry
  SDK → LangChain/LangGraph) and a longer list of gotchas hit while setting this up.
