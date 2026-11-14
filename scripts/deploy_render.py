"""Render Automated Deployment CLI using Render's REST API & MCP infrastructure."""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List, Optional
import httpx
from dotenv import load_dotenv

load_dotenv()

RENDER_API_BASE = "https://api.render.com/v1"
GITHUB_REPO = "https://github.com/mohammedrehan143/smart-ai-gateway"


class RenderDeployer:
    """Manages Render service deployment and status tracking."""

    def __init__(self, api_key: str):
        self.api_key = api_key.strip()
        self.client = httpx.Client(
            base_url=RENDER_API_BASE,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            timeout=30.0,
        )

    def get_owner_id(self) -> str:
        resp = self.client.get("/owners")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to fetch Render owners: {resp.status_code} {resp.text}")
        owners = resp.json()
        if not owners:
            raise RuntimeError("No owners/workspaces found for this Render API key.")
        return owners[0]["owner"]["id"]

    def list_services(self) -> List[Dict[str, Any]]:
        resp = self.client.get("/services")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to list services: {resp.status_code} {resp.text}")
        return resp.json()

    def find_service(self, name: str = "smart-ai-gateway") -> Optional[Dict[str, Any]]:
        services = self.list_services()
        for item in services:
            svc = item.get("service", {})
            if svc.get("name") == name:
                return svc
        return None

    def create_web_service(self, name: str = "smart-ai-gateway", branch: str = "main") -> Dict[str, Any]:
        owner_id = self.get_owner_id()
        payload = {
            "type": "web_service",
            "name": name,
            "ownerId": owner_id,
            "repo": GITHUB_REPO,
            "branch": branch,
            "autoDeploy": "yes",
            "serviceDetails": {
                "env": "python",
                "plan": "free",
                "region": "oregon",
                "buildCommand": "pip install --upgrade pip && pip install -r requirements.txt && pip install .",
                "startCommand": "uvicorn app.main:app --host 0.0.0.0 --port $PORT",
                "healthCheckPath": "/health/live",
                "envVars": [
                    {"key": "PYTHON_VERSION", "value": "3.11.7"},
                    {"key": "APP_ENV", "value": "production"},
                    {"key": "LOG_LEVEL", "value": "INFO"},
                    {"key": "CHEAP_MODEL_ALIAS", "value": "mock-cheap"},
                    {"key": "STRONG_MODEL_ALIAS", "value": "mock-strong"},
                    {"key": "FALLBACK_MODEL_ALIAS", "value": "mock-strong"},
                ],
            },
        }
        resp = self.client.post("/services", json=payload)
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to create service: {resp.status_code} {resp.text}")
        return resp.json()["service"]

    def trigger_deploy(self, service_id: str) -> Dict[str, Any]:
        resp = self.client.post(f"/services/{service_id}/deploys")
        if resp.status_code not in (200, 201):
            raise RuntimeError(f"Failed to trigger deploy: {resp.status_code} {resp.text}")
        return resp.json()

    def get_deploy_status(self, service_id: str, deploy_id: str) -> Dict[str, Any]:
        resp = self.client.get(f"/services/{service_id}/deploys/{deploy_id}")
        if resp.status_code != 200:
            raise RuntimeError(f"Failed to get deploy status: {resp.status_code} {resp.text}")
        return resp.json()


def main():
    parser = argparse.ArgumentParser(description="Render Automated Deployment CLI")
    parser.add_argument("--key", default=os.environ.get("RENDER_API_KEY"), help="Render API Key")
    parser.add_argument("--name", default="smart-ai-gateway", help="Service name")
    args = parser.parse_args()

    api_key = args.key
    if not api_key:
        print("[ERROR] Please provide your Render API key via --key or RENDER_API_KEY env variable.")
        print("Generate one at: https://dashboard.render.com/u/settings -> API Keys")
        sys.exit(1)

    deployer = RenderDeployer(api_key=api_key)

    print(">>> Connecting to Render API...")
    existing = deployer.find_service(args.name)
    if existing:
        svc_id = existing["id"]
        url = existing.get("serviceDetails", {}).get("url", f"https://{args.name}.onrender.com")
        print(f"[FOUND] Existing service: '{args.name}' (ID: {svc_id})")
        print(f"Triggering new deployment on branch 'main'...")
        deploy = deployer.trigger_deploy(svc_id)
        dep_id = deploy.get("id", "")
        print(f"[DEPLOYING] Deployment triggered (ID: {dep_id})")
        print(f"Live Service URL: {url}")
    else:
        print(f"[CREATE] Service '{args.name}' not found. Creating new Web Service from {GITHUB_REPO}...")
        svc = deployer.create_web_service(args.name)
        svc_id = svc["id"]
        url = svc.get("serviceDetails", {}).get("url", f"https://{args.name}.onrender.com")
        print(f"[SUCCESS] Service created! (ID: {svc_id})")
        print(f"Live Service URL: {url}")


if __name__ == "__main__":
    main()
