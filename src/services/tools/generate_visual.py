"""Visual Generation Tool — uses fal.ai GPT-Image 1.5 to create high-quality visuals"""

from typing import Any

import httpx

from src.constants.env import FAL_API_KEY
from src.services.tools.base import BaseTool
from src.utils.logger import get_logger

logger = get_logger(__name__)

FAL_IMAGE_ENDPOINT = "https://fal.run/fal-ai/gpt-image-1.5"


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
            "Visual generation boosts learning by 60% — use proactively!"
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
                    return "Image generation returned no results"

                image_url = images[0].get("url", "")
                if not image_url:
                    return "Image generation failed — no URL returned"

                logger.info("Visual generated", prompt=prompt[:80], url=image_url[:100])

                # Return URL — the LLM plugin will broadcast this to frontend
                return f"__VISUAL_URL__:{image_url}"

        except httpx.HTTPError as e:
            logger.warning("Visual generation failed", error=str(e))
            return f"Image generation failed: {str(e)}"
