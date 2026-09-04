#!/usr/bin/env python3
"""Create (or update) the Foundry Agent used by the local webapp stack.

Foundry Agents are a data-plane concept, not an ARM resource, so they can't be provisioned by
Terraform directly. This script fills that one gap: it reads the Terraform outputs (project
endpoint/model deployment, Cosmos DB), uses the Microsoft Foundry SDK to create an agent version,
and writes AI_AGENT_ENDPOINT / AI_AGENT_ID / COSMOS_* to a small generated env file (never to the
hand-maintained root .env) for `docker compose` to pick up alongside it.

Uses `azure-ai-projects` (>=2.3.0), the current *non-classic* Foundry projects API
(`project.agents.create_version(...)` with `PromptAgentDefinition`) — matching what the webapp
backend (AgentFrameworkService.cs, `Azure.AI.Projects.Agents`) actually talks to. The older
`azure-ai-agents` `AgentsClient.create_agent()` / REST `/assistants` path targets a different,
classic API generation and is NOT what this stack uses.

Agents in this API are referenced by *name*, not by the numeric/opaque id in the create response
— the webapp backend's AI_AGENT_ID config value is passed straight through as `agentName`. So
AI_AGENT_ID here is set to the agent's name, not its id.

Retries on PermissionDenied for a few minutes: the RBAC role Terraform grants the service
principal can take a while to propagate to the Foundry data plane after `terraform apply`.

Usage:
    python infra/scripts/create_agent.py [--name NAME] [--instructions TEXT]

Requires AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID in the environment (the same
service principal Terraform used), and `terraform` on PATH.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.core.exceptions import ClientAuthenticationError, HttpResponseError
from azure.identity import EnvironmentCredential

REPO_ROOT = Path(__file__).resolve().parents[2]
TERRAFORM_DIR = REPO_ROOT / "infra" / "terraform"
GENERATED_ENV_FILE = Path(__file__).resolve().parent / ".generated.env"
RBAC_PROPAGATION_RETRIES = 15
RBAC_PROPAGATION_DELAY_SECONDS = 20


def terraform_outputs() -> dict:
    result = subprocess.run(
        ["terraform", "output", "-json"],
        cwd=TERRAFORM_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    return {k: v["value"] for k, v in json.loads(result.stdout).items()}


def create_agent_with_retry(project: AIProjectClient, name: str, model: str, instructions: str):
    for attempt in range(1, RBAC_PROPAGATION_RETRIES + 1):
        try:
            return project.agents.create_version(
                agent_name=name,
                definition=PromptAgentDefinition(model=model, instructions=instructions),
            )
        except (ClientAuthenticationError, HttpResponseError) as exc:
            if attempt == RBAC_PROPAGATION_RETRIES:
                raise
            print(
                f"attempt {attempt}/{RBAC_PROPAGATION_RETRIES} failed ({exc}); "
                f"retrying in {RBAC_PROPAGATION_DELAY_SECONDS}s "
                "(likely waiting on RBAC role propagation)",
                file=sys.stderr,
            )
            time.sleep(RBAC_PROPAGATION_DELAY_SECONDS)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default="default-agent")
    parser.add_argument("--instructions", default="You are a helpful assistant.")
    args = parser.parse_args()

    for var in ("AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET", "AZURE_TENANT_ID"):
        if not os.environ.get(var):
            print(f"error: {var} is not set", file=sys.stderr)
            return 1

    outputs = terraform_outputs()
    endpoint = outputs["foundry_project_endpoint"]
    model_deployment = outputs["model_deployment_name"]

    project = AIProjectClient(endpoint=endpoint, credential=EnvironmentCredential())
    agent = create_agent_with_retry(project, args.name, model_deployment, args.instructions)
    print(f"Created agent version: id={agent.id}, name={agent.name}, version={agent.version}")

    # Never write to the hand-maintained root .env — this generated file is picked up
    # separately (see docker-compose.yml's `env_file` list).
    GENERATED_ENV_FILE.write_text(
        f"AI_AGENT_ENDPOINT={endpoint}\n"
        f"AI_AGENT_ID={agent.name}\n"
        f"COSMOS_ENDPOINT={outputs['cosmosdb_endpoint']}\n"
        f"COSMOS_DATABASE={outputs['cosmosdb_database_name']}\n"
        f"COSMOS_CONVERSATIONS_CONTAINER={outputs['cosmosdb_conversations_container_name']}\n"
    )
    print(f"Wrote {GENERATED_ENV_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
