import requests
import os
from dotenv import load_dotenv
import base64

load_dotenv()

class LinkedInPoster:
    def __init__(self, access_token=None):
        raw_token = access_token or os.getenv("LINKEDIN_ACCESS_TOKEN") or os.getenv("ACCESS_TOKEN")
        self.access_token = raw_token.strip().strip('"') if raw_token else None
        
        raw_urn = os.getenv("LINKEDIN_PERSON_URN") or os.getenv("PERSON_URN")
        self.person_urn = raw_urn.strip().strip('"') if raw_urn else None
        
        self.api_url = "https://api.linkedin.com/v2/ugcPosts"

    def get_me(self):
        if not self.access_token:
            print("Error: LinkedIn Access Token is missing.")
            return None
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0"
        }
        try:
            response = requests.get("https://api.linkedin.com/v2/me", headers=headers)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching LinkedIn profile: {e}")
            return None

    def upload_image(self, image_data):
        if not self.access_token:
            print("Error: LinkedIn Access Token is missing for image upload.")
            return None

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        # The correct action is registerUpload, not upload
        register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        register_payload = {
            "registerUploadRequest": {
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "owner": self.person_urn,
                "serviceRelationships": [
                    {
                        "relationshipType": "OWNER",
                        "identifier": "urn:li:userGeneratedContent"
                    }
                ]
            }
        }
        
        try:
            print(f"Registering image upload for owner: {self.person_urn}")
            response = requests.post(register_url, headers=headers, json=register_payload)
            response.raise_for_status()
            register_data = response.json()
            
            # Defensive check for nested keys
            try:
                if 'com.linkedin.digitalmedia.uploading.MultipartUpload' in register_data['value']['uploadMechanism']:
                    put_url = register_data['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MultipartUpload']['uploadUrl']
                elif 'com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest' in register_data['value']['uploadMechanism']:
                    put_url = register_data['value']['uploadMechanism']['com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest']['uploadUrl']
                else:
                    print(f"DEBUG: register_data structure: {register_data}")
                    raise KeyError("Unknown upload mechanism")
            except KeyError:
                print(f"DEBUG: register_data structure: {register_data}")
                raise
            
            asset_urn = register_data['value']['asset']

            # Upload the image bytes
            if image_data.startswith('data:image'):
                header, encoded = image_data.split(",", 1)
                image_bytes = base64.b64decode(encoded)
                content_type = header.split(';')[0].split(':')[1]
            elif os.path.exists(image_data):
                # Local file path
                with open(image_data, "rb") as f:
                    image_bytes = f.read()
                import mimetypes
                content_type = mimetypes.guess_type(image_data)[0] or 'image/jpeg'
                print(f"Reading local image: {image_data} ({content_type})")
            else:
                # Assume it's a URL
                image_response = requests.get(image_data)
                image_response.raise_for_status()
                image_bytes = image_response.content
                content_type = image_response.headers.get('Content-Type', 'image/jpeg')

            upload_headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": content_type
            }
            upload_response = requests.put(put_url, headers=upload_headers, data=image_bytes)
            upload_response.raise_for_status()
            
            print(f"Successfully uploaded image. Asset URN: {asset_urn}")
            return asset_urn
            
        except Exception as e:
            print(f"Error uploading image to LinkedIn: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response details: {e.response.text}")
            return None

    def post_text(self, text, title=None, original_url=None, uploaded_image_urn=None):
        if not self.access_token or not self.person_urn:
            print("Error: LinkedIn Access Token or Person URN is missing.")
            return None

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0"
        }

        share_content = {
            "author": self.person_urn,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {
                        "text": text
                    },
                    "shareMediaCategory": "IMAGE" if uploaded_image_urn else ("ARTICLE" if original_url else "NONE")
                }
            },
            "visibility": {
                "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
            }
        }

        if uploaded_image_urn:
            share_content["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                {
                    "status": "READY",
                    "description": {
                        "text": text[:200] + "..." if len(text) > 200 else text
                    },
                    "media": uploaded_image_urn,
                    "originalUrl": original_url,
                    "title": {
                        "text": title or "Shared Content"
                    }
                }
            ]
        elif original_url:
            share_content["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                {
                    "status": "READY",
                    "description": {
                        "text": text[:200] + "..." if len(text) > 200 else text
                    },
                    "originalUrl": original_url,
                    "title": {
                        "text": title or "Shared Content"
                    }
                }
            ]

        try:
            response = requests.post(self.api_url, headers=headers, json=share_content)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error posting to LinkedIn: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response details: {e.response.text}")
            return None

