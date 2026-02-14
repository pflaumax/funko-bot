"""Bluesky bot client for posting Funko Pop updates.

This module handles all interactions with the Bluesky API including
authentication, posting, and image uploads.
"""

import time
import logging
from typing import Optional, Dict
from pathlib import Path

from atproto import Client, models


logger = logging.getLogger("funko_bot.bot")

MAX_RETRIES = 3
INITIAL_BACKOFF = 1  # seconds


class FunkoBlueskyBot:
    """Bluesky bot client for posting Funko Pop product updates.

    This class manages authentication with Bluesky and provides methods
    for posting text and images with retry logic and error handling.
    """

    def __init__(self, handle: str, app_password: str):
        """Initialize the Bluesky bot client.

        Args:
            handle: Bluesky handle (e.g., yourbot.bsky.social).
            app_password: App-specific password from Bluesky settings.

        Raises:
            Exception: If authentication fails.
        """
        self.handle = handle
        self.app_password = app_password
        self.client = Client()
        self._authenticated = False

        logger.info(f"Initializing Bluesky bot for handle: {handle}")
        self._login()

    def _login(self) -> None:
        """Authenticate with Bluesky API.

        Raises:
            Exception: If login fails after retries.
        """
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Attempting login (attempt {attempt}/{MAX_RETRIES})")
                self.client.login(self.handle, self.app_password)
                self._authenticated = True
                logger.info("Successfully authenticated with Bluesky")
                return
            except Exception as e:
                logger.error(f"Login attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {backoff} seconds...")
                    time.sleep(backoff)
                else:
                    logger.critical("Failed to authenticate after all retries")
                    raise

    def upload_image(self, image_path: str) -> Optional[Dict]:
        """Upload an image to Bluesky and return blob reference.

        Args:
            image_path: Path to the image file to upload.

        Returns:
            Dict containing blob reference, or None if upload fails.
        """
        if not self._authenticated:
            logger.error("Cannot upload image: not authenticated")
            return None

        image_file = Path(image_path)
        if not image_file.exists():
            logger.error(f"Image file not found: {image_path}")
            return None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"Uploading image: {image_path} (attempt {attempt}/{MAX_RETRIES})"
                )

                with open(image_path, "rb") as f:
                    image_data = f.read()

                # Upload blob to Bluesky
                upload_response = self.client.upload_blob(image_data)
                logger.info(f"Image uploaded successfully: {upload_response.blob}")
                return upload_response.blob

            except Exception as e:
                logger.error(f"Image upload attempt {attempt} failed: {e}")
                if attempt < MAX_RETRIES:
                    backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
                    time.sleep(backoff)
                else:
                    logger.error("Failed to upload image after all retries")
                    return None

    def send_post(
        self,
        text: str,
        image_paths: Optional[list] = None,
        alt_texts: Optional[list] = None,
    ) -> bool:
        """Send a post to Bluesky with optional images (up to 4).

        Args:
            text: Post text content (max 300 characters).
            image_paths: Optional list of image file paths (max 4).
            alt_texts: Optional list of alt texts for each image.

        Returns:
            bool: True if post was successful, False otherwise.
        """
        if not self._authenticated:
            logger.error("Cannot send post: not authenticated")
            return False

        # Validate text length
        if len(text) > 300:
            logger.warning(
                f"Post text exceeds 300 characters ({len(text)}), truncating"
            )
            text = text[:297] + "..."

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(f"Sending post (attempt {attempt}/{MAX_RETRIES})")
                logger.debug(f"Post text: {text[:100]}...")

                # Prepare embed if images are provided
                embed = None
                if image_paths:
                    # Support both single image (string) and multiple (list)
                    if isinstance(image_paths, str):
                        image_paths = [image_paths]
                    if isinstance(alt_texts, str):
                        alt_texts = [alt_texts]

                    # Limit to 4 images (Bluesky max)
                    image_paths = image_paths[:4]

                    # Upload all images
                    image_embeds = []
                    for i, img_path in enumerate(image_paths):
                        blob = self.upload_image(img_path)
                        if blob:
                            alt = ""
                            if alt_texts and i < len(alt_texts):
                                alt = alt_texts[i] or ""
                            image_embeds.append(
                                models.AppBskyEmbedImages.Image(alt=alt, image=blob)
                            )

                    if image_embeds:
                        embed = models.AppBskyEmbedImages.Main(images=image_embeds)
                        logger.info(f"Created embed with {len(image_embeds)} images")
                    else:
                        logger.warning(
                            "All image uploads failed, posting without images"
                        )

                # Create facets for clickable links and hashtags
                facets = []
                import re

                # Find all URLs in the text
                url_pattern = r"https?://[^\s]+"
                for match in re.finditer(url_pattern, text):
                    url = match.group()
                    start = match.start()
                    end = match.end()

                    # Create a link facet
                    facets.append(
                        models.AppBskyRichtextFacet.Main(
                            features=[models.AppBskyRichtextFacet.Link(uri=url)],
                            index=models.AppBskyRichtextFacet.ByteSlice(
                                byte_start=len(text[:start].encode("utf-8")),
                                byte_end=len(text[:end].encode("utf-8")),
                            ),
                        )
                    )

                # Find all hashtags in the text
                hashtag_pattern = r"#\w+"
                for match in re.finditer(hashtag_pattern, text):
                    hashtag = match.group()
                    start = match.start()
                    end = match.end()

                    # Create a hashtag facet (tag without the # symbol)
                    tag = hashtag[1:]  # Remove the # symbol
                    facets.append(
                        models.AppBskyRichtextFacet.Main(
                            features=[models.AppBskyRichtextFacet.Tag(tag=tag)],
                            index=models.AppBskyRichtextFacet.ByteSlice(
                                byte_start=len(text[:start].encode("utf-8")),
                                byte_end=len(text[:end].encode("utf-8")),
                            ),
                        )
                    )

                # Send the post with facets
                if embed:
                    self.client.send_post(
                        text=text, embed=embed, facets=facets if facets else None
                    )
                else:
                    self.client.send_post(text=text, facets=facets if facets else None)

                logger.info("Post sent successfully")
                return True

            except Exception as e:
                logger.error(f"Post attempt {attempt} failed: {e}", exc_info=True)
                if attempt < MAX_RETRIES:
                    backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
                    logger.info(f"Retrying in {backoff} seconds...")
                    time.sleep(backoff)
                else:
                    logger.error("Failed to send post after all retries")
                    return False

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup."""
        logger.info("Cleaning up Bluesky bot client")
        self._authenticated = False
        # Client cleanup if needed
        return False
