import requests
import webbrowser
from urllib.parse import urlencode
import os
from dotenv import load_dotenv

load_dotenv()

def get_env_var(key, default=None):
    value = os.getenv(key)
    if value:
        return value.strip().strip('"')
    return default

def get_auth_url():
    client_id = get_env_var("LINKEDIN_CLIENT_ID") or get_env_var("CLIENT_ID")
    redirect_uri = get_env_var("LINKEDIN_REDIRECT_URI") or get_env_var("REDIRECT_URI")
    
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": "w_member_social profile openid email",
    }
    base_url = "https://www.linkedin.com/oauth/v2/authorization"
    return f"{base_url}?{urlencode(params)}"

def exchange_code_for_token(code):
    client_id = get_env_var("LINKEDIN_CLIENT_ID") or get_env_var("CLIENT_ID")
    client_secret = get_env_var("LINKEDIN_CLIENT_SECRET") or get_env_var("CLIENT_SECRET")
    redirect_uri = get_env_var("LINKEDIN_REDIRECT_URI") or get_env_var("REDIRECT_URI")

    url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    response = requests.post(url, data=data, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Error exchanging code: {response.status_code}")
        print(response.text)
        return None

if __name__ == "__main__":
    print("Visit this URL to authorize the app:")
    print(get_auth_url())
    code = input("Enter the code from the redirect URL: ")
    token_data = exchange_code_for_token(code)
    if token_data:
        print("Access Token details:")
        print(token_data)



