#!/usr/bin/env python3
"""
GitHub Actions 워크플로우를 트리거하는 스크립트
외부 시스템에서 Firestore에 저장한 후 이 스크립트를 호출하여 자동 배포를 시작합니다.

사용법:
    python scripts/trigger-github-deploy.py

환경 변수:
    GITHUB_TOKEN: GitHub Personal Access Token (필수)
    GITHUB_REPO: GitHub 저장소 (예: kr-ai-dev-association/tech-blog) (선택, 기본값 사용)
    GITHUB_WORKFLOW: 워크플로우 파일명 (예: deploy-seo.yml) (선택, 기본값 사용)
"""

import os
import sys
import requests
import json

# GitHub API 설정
GITHUB_API_BASE = "https://api.github.com"
GITHUB_REPO = os.getenv("GITHUB_REPO", "kr-ai-dev-association/tech-blog")
GITHUB_WORKFLOW = os.getenv("GITHUB_WORKFLOW", "deploy-seo.yml")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

def trigger_workflow():
    """GitHub Actions 워크플로우를 트리거합니다."""
    
    if not GITHUB_TOKEN:
        print("❌ Error: GITHUB_TOKEN environment variable is not set")
        print("💡 Please set GITHUB_TOKEN with a GitHub Personal Access Token")
        print("   Create one at: https://github.com/settings/tokens")
        print("   Required permissions: repo, workflow")
        return False
    
    url = f"{GITHUB_API_BASE}/repos/{GITHUB_REPO}/actions/workflows/{GITHUB_WORKFLOW}/dispatches"
    
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {GITHUB_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "ref": "main",  # 또는 "master"
        "inputs": {}  # 워크플로우에 inputs가 있는 경우 여기에 추가
    }
    
    print(f"🚀 Triggering GitHub Actions workflow: {GITHUB_WORKFLOW}")
    print(f"📦 Repository: {GITHUB_REPO}")
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        if response.status_code == 204:
            print("✅ Workflow triggered successfully!")
            print(f"🔗 Check status at: https://github.com/{GITHUB_REPO}/actions")
            return True
        else:
            print(f"❌ Failed to trigger workflow. Status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Error triggering workflow: {e}")
        return False

if __name__ == "__main__":
    success = trigger_workflow()
    sys.exit(0 if success else 1)
