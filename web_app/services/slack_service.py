import os
import logging
import aiohttp
from typing import Optional, Dict, Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class SlackService:
    """Slack 알림 서비스"""

    def __init__(self):
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.default_channel = os.getenv("SLACK_DEFAULT_CHANNEL", "#general")
        self.notify_email = os.getenv("SLACK_NOTIFY_EMAIL", "tony@banya.ai")
        self.base_url = "https://slack.com/api"

    async def _get_user_id_by_email(self, email: str) -> Optional[str]:
        """이메일로 Slack 사용자 ID를 조회합니다."""
        if not self.bot_token:
            logger.warning("SLACK_BOT_TOKEN not configured")
            return None

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/users.lookupByEmail",
                    headers=headers,
                    params={"email": email}
                ) as response:
                    data = await response.json()
                    if data.get("ok"):
                        return data.get("user", {}).get("id")
                    else:
                        logger.warning(f"Failed to find Slack user: {data.get('error')}")
                        return None
        except Exception as e:
            logger.error(f"Error looking up Slack user: {e}")
            return None

    async def _open_dm_channel(self, user_id: str) -> Optional[str]:
        """사용자와의 DM 채널을 엽니다."""
        if not self.bot_token:
            return None

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/conversations.open",
                    headers=headers,
                    json={"users": user_id}
                ) as response:
                    data = await response.json()
                    if data.get("ok"):
                        return data.get("channel", {}).get("id")
                    else:
                        logger.warning(f"Failed to open DM channel: {data.get('error')}")
                        return None
        except Exception as e:
            logger.error(f"Error opening DM channel: {e}")
            return None

    async def send_dm(self, email: str, message: str, blocks: list = None) -> bool:
        """
        특정 사용자에게 DM을 보냅니다.

        Args:
            email: 사용자 이메일
            message: 메시지 텍스트
            blocks: Slack Block Kit 형식의 블록 (선택사항)

        Returns:
            성공 여부
        """
        if not self.bot_token:
            logger.warning("SLACK_BOT_TOKEN not configured, skipping notification")
            return False

        # 사용자 ID 조회
        user_id = await self._get_user_id_by_email(email)
        if not user_id:
            logger.warning(f"Could not find Slack user with email: {email}")
            return False

        # DM 채널 열기
        channel_id = await self._open_dm_channel(user_id)
        if not channel_id:
            return False

        # 메시지 전송
        return await self.send_message(channel_id, message, blocks)

    async def send_message(self, channel: str, message: str, blocks: list = None) -> bool:
        """
        채널에 메시지를 보냅니다.

        Args:
            channel: 채널 ID 또는 이름
            message: 메시지 텍스트
            blocks: Slack Block Kit 형식의 블록 (선택사항)

        Returns:
            성공 여부
        """
        if not self.bot_token:
            logger.warning("SLACK_BOT_TOKEN not configured")
            return False

        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "channel": channel,
            "text": message
        }

        if blocks:
            payload["blocks"] = blocks

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/chat.postMessage",
                    headers=headers,
                    json=payload
                ) as response:
                    data = await response.json()
                    if data.get("ok"):
                        logger.info(f"Slack message sent to {channel}")
                        return True
                    else:
                        logger.warning(f"Failed to send Slack message: {data.get('error')}")
                        return False
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
            return False

    async def notify_pipeline_complete(
        self,
        title: str,
        youtube_url: str = None,
        plan_id: str = None,
        video_filename: str = None,
        duration: str = None,
        category: str = None,
        error: str = None
    ) -> bool:
        """
        파이프라인 완료 알림을 보냅니다.

        Args:
            title: 콘텐츠 제목
            youtube_url: YouTube 업로드 URL (성공 시)
            plan_id: 기획안 ID
            video_filename: 생성된 비디오 파일명
            duration: 소요 시간
            category: 카테고리
            error: 에러 메시지 (실패 시)

        Returns:
            성공 여부
        """
        if error:
            # 실패 알림
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "❌ Auto Pipeline Failed",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Title:*\n{title}"},
                        {"type": "mrkdwn", "text": f"*Plan ID:*\n{plan_id or 'N/A'}"}
                    ]
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Error:*\n```{error}```"
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Duration: {duration or 'N/A'}"}
                    ]
                }
            ]
            message = f"❌ Auto Pipeline Failed: {title}\nError: {error}"
        else:
            # 성공 알림
            blocks = [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "✅ Auto Pipeline Complete!",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Title:*\n{title}"},
                        {"type": "mrkdwn", "text": f"*Category:*\n{category or 'N/A'}"}
                    ]
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*Plan ID:*\n{plan_id or 'N/A'}"},
                        {"type": "mrkdwn", "text": f"*Video:*\n{video_filename or 'N/A'}"}
                    ]
                }
            ]

            if youtube_url:
                blocks.append({
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*YouTube:*\n<{youtube_url}|Watch on YouTube>"
                    }
                })

            blocks.append({
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"⏱️ Duration: {duration or 'N/A'}"}
                ]
            })

            message = f"✅ Auto Pipeline Complete: {title}"
            if youtube_url:
                message += f"\nYouTube: {youtube_url}"

        return await self.send_dm(self.notify_email, message, blocks)


# 싱글톤 인스턴스
slack_service = SlackService()
