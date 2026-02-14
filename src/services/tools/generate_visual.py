"""Visual Generation Tool — uses fal.ai GPT-Image 1.5 to create high-quality visuals.

The tool returns IMMEDIATELY to the LLM so it can keep talking.
Actual image generation runs as a background asyncio task and
broadcasts the URL to the frontend via the on_visual callback.
"""

from typing import Any, Callable, Optional

import asyncio
import httpx

from src.constants.env import FAL_API_KEY
from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)

FAL_IMAGE_ENDPOINT = "https://fal.run/fal-ai/gpt-image-1.5"


async def _generate_image_background(
    prompt: str,
    on_visual: Optional[Callable[[str], Any]] = None,
    room_name: Optional[str] = None,
) -> None:
    """Background coroutine: generate image and broadcast URL when ready."""
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                FAL_IMAGE_ENDPOINT,
                headers={
                    "Authorization": f"Key {FAL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": prompt,
                    "image_size": "1536x1024",
                    "quality": "high",
                    "num_images": 1,
                    "output_format": "png",
                },
            )
            response.raise_for_status()
            data = response.json()

            images = data.get("images", [])
            if not images:
                logger.warning("Image generation returned no results", prompt=prompt[:80])
                return

            image_url = images[0].get("url", "")
            if not image_url:
                logger.warning("Image generation returned no URL", prompt=prompt[:80])
                return

            logger.info("Visual generated (bg)", prompt=prompt[:80], url=image_url[:100])

            # Broadcast to frontend via callback
            if on_visual:
                on_visual(image_url)

            # Save to conversation history
            if room_name:
                try:
                    from src.models.database import db as database
                    from src.crud.voice_conversation import get_conversation_by_room, create_message

                    async with database.get_session_context() as db:
                        conv = await get_conversation_by_room(db, room_name)
                        if conv:
                            await create_message(
                                db=db,
                                conversation_id=conv.id,
                                participant_identity="agent",
                                participant_name="AI Assistant",
                                message_type="ai_response",
                                content=f"__IMAGE__:{image_url}",
                            )
                except Exception as e:
                    logger.warning("Failed to save visual message", error=str(e))

    except httpx.HTTPError as e:
        logger.warning("Visual generation failed (bg)", error=str(e))
    except Exception as e:
        logger.warning("Visual generation error (bg)", error=str(e))


class GenerateVisualTool(BaseTool):
    """Generate educational visuals/diagrams via fal.ai GPT-Image 1.5"""

    @property
    def name(self) -> str:
        return "generate_visual"

    @property
    def description(self) -> str:
        return (
            "Generate educational visuals, diagrams, or infographics. "
            "Use GENEROUSLY to visualize and clarify complex topics! "
            "Especially create visuals for: "
            "scientific processes (photosynthesis, cells, reactions), "
            "historical timelines, comparison tables, "
            "anatomy and geographical structures, mathematical concepts, "
            "flowcharts and process maps. "
            "Visual generation boosts learning by 60% — use proactively! "
            "NOTE: This tool returns instantly. The image will appear on the user's screen shortly."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "A clear, detailed English image generation prompt. "
                        "Describe the visual: layout, labels, colors, style. "
                        "Example: 'Educational diagram of photosynthesis process, "
                        "showing sunlight, water, CO2 inputs and glucose, oxygen outputs, "
                        "clean flat illustration style, labeled arrows, white background'"
                    ),
                },
            },
            "required": ["prompt"],
        }

    async def execute(self, **kwargs: Any) -> str:
        prompt = kwargs.get("prompt", "")
        if not prompt:
            return "No image prompt provided"

        # Extract callbacks injected by FalLLMStream
        on_visual = kwargs.get("_on_visual")
        on_visual_loading = kwargs.get("_on_visual_loading")
        room_name = kwargs.get("_room_name")

        # Notify frontend immediately: show loading placeholder
        if on_visual_loading:
            on_visual_loading()

        # Fire background task — DO NOT await
        asyncio.create_task(
            _generate_image_background(
                prompt=prompt,
                on_visual=on_visual,
                room_name=room_name,
            )
        )

        logger.info("Visual generation dispatched (non-blocking)", prompt=prompt[:80])

        # Return immediately so LLM keeps talking
        return (
            "Visual is being generated and will appear on the user's screen in a few seconds. "
            "Continue explaining the topic — don't wait for the image."
        )
