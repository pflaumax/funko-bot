"""Image handling for Funko product images.

This module handles downloading, resizing, and managing product images
for posting to Bluesky.
"""

import os
import logging
import time
from typing import Optional, Tuple
from pathlib import Path
from datetime import datetime, timedelta

import requests
from PIL import Image


logger = logging.getLogger("funko_bot.image_handler")

DEFAULT_MAX_SIZE = (1200, 1200)  # Larger max size for better quality
IMAGE_QUALITY = 95  # Higher quality JPEG compression
DOWNLOAD_TIMEOUT = 30


class ImageHandler:
    """Handler for downloading and processing product images.

    This class manages image downloads, resizing for optimal posting,
    and cleanup of old temporary files.
    """

    def __init__(self, images_dir: Path):
        """Initialize the image handler.

        Args:
            images_dir: Directory path for storing images.
        """
        self.images_dir = Path(images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Image handler initialized with directory: {images_dir}")

    def download_image(self, url: str, save_path: str) -> Optional[str]:
        """Download an image from URL to local path.

        Args:
            url: Image URL to download.
            save_path: Local path to save the image.

        Returns:
            Path to downloaded image, or None if download fails.
        """
        if not url:
            logger.warning("Empty image URL provided")
            return None

        try:
            logger.info(f"Downloading image from: {url}")

            response = requests.get(
                url,
                timeout=DOWNLOAD_TIMEOUT,
                stream=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            response.raise_for_status()

            # Save the image
            save_path = Path(save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            with open(save_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            logger.info(f"Image downloaded successfully: {save_path}")
            return str(save_path)

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download image from {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error downloading image: {e}", exc_info=True)
            return None

    def resize_image(
        self, image_path: str, max_size: Tuple[int, int] = DEFAULT_MAX_SIZE
    ) -> Optional[str]:
        """Resize image to fit within max dimensions while maintaining aspect ratio.

        Args:
            image_path: Path to the image file.
            max_size: Maximum (width, height) tuple.

        Returns:
            Path to resized image, or None if resize fails.
        """
        try:
            logger.info(f"Resizing image: {image_path}")

            with Image.open(image_path) as img:
                original_format = img.format
                original_mode = img.mode

                # Only resize if image is larger than max_size
                if img.size[0] <= max_size[0] and img.size[1] <= max_size[1]:
                    logger.info(f"Image already optimal size: {img.size}")
                    return image_path

                # Convert RGBA to RGB if saving as JPEG
                if img.mode == "RGBA" and original_format != "PNG":
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[3])
                    img = background

                # Calculate new size maintaining aspect ratio
                img.thumbnail(max_size, Image.Resampling.LANCZOS)

                # Save with high quality - keep PNG if original was PNG
                if original_format == "PNG" and original_mode == "RGBA":
                    img.save(image_path, "PNG", optimize=True)
                else:
                    img.save(image_path, "JPEG", quality=IMAGE_QUALITY, optimize=True)

                logger.info(f"Image resized to {img.size}")
                return image_path

        except Exception as e:
            logger.error(f"Failed to resize image {image_path}: {e}", exc_info=True)
            return None

    def generate_alt_text(self, product: dict) -> str:
        """Generate descriptive alt text for accessibility.

        Args:
            product: Product dictionary with name, fandom, currency, etc.

        Returns:
            Descriptive alt text string.
        """
        name = product.get("name", "Funko Pop")
        fandom = product.get("fandom", "")
        price = product.get("price", 0)
        currency = product.get("currency", "EUR")

        # Map currency to symbol
        currency_symbols = {
            "EUR": "€",
            "USD": "$",
            "GBP": "£",
        }
        symbol = currency_symbols.get(currency, currency)

        if price > 0:
            if fandom and fandom != "Other":
                alt_text = (
                    f"{fandom} Funko Pop figure: {name}, priced at {symbol}{price:.2f}"
                )
            else:
                alt_text = f"Funko Pop figure: {name}, priced at {symbol}{price:.2f}"
        else:
            # No price available (e.g., GitHub fallback)
            if fandom and fandom != "Other":
                alt_text = f"{fandom} Funko Pop figure: {name}"
            else:
                alt_text = f"Funko Pop figure: {name}"

        logger.debug(f"Generated alt text: {alt_text}")
        return alt_text

    def cleanup_old_images(self, max_age_hours: int = 24) -> int:
        """Remove image files older than specified hours.

        Args:
            max_age_hours: Maximum age in hours before deletion.

        Returns:
            Number of files deleted.
        """
        logger.info(f"Cleaning up images older than {max_age_hours} hours")

        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        deleted_count = 0

        try:
            for image_file in self.images_dir.glob("*"):
                if image_file.is_file():
                    file_mtime = datetime.fromtimestamp(image_file.stat().st_mtime)

                    if file_mtime < cutoff_time:
                        logger.debug(f"Deleting old image: {image_file}")
                        image_file.unlink()
                        deleted_count += 1

            logger.info(f"Cleaned up {deleted_count} old images")
            return deleted_count

        except Exception as e:
            logger.error(f"Error during image cleanup: {e}", exc_info=True)
            return deleted_count

    def download_and_prepare(self, product: dict) -> Optional[list]:
        """Download and prepare product images for posting.

        Args:
            product: Product dictionary with image_url and optionally image_url_alt.

        Returns:
            List of paths to prepared images, or None if all downloads fail.
        """
        image_urls = []

        # Main image
        main_url = product.get("image_url")
        if main_url:
            image_urls.append(main_url)

        # Alternate image (in-box or lifestyle shot)
        alt_url = product.get("image_url_alt")
        if alt_url:
            image_urls.append(alt_url)

        if not image_urls:
            logger.warning("No image URLs in product data")
            return None

        # Generate filename base from product ID
        product_id = product.get("id", "unknown")
        timestamp = int(time.time())

        downloaded_paths = []
        for i, url in enumerate(image_urls):
            filename = f"{product_id}_{timestamp}_{i}.jpg"
            save_path = self.images_dir / filename

            # Download image
            downloaded_path = self.download_image(url, str(save_path))
            if downloaded_path:
                # Resize image
                resized_path = self.resize_image(downloaded_path)
                if resized_path:
                    downloaded_paths.append(resized_path)

        if not downloaded_paths:
            logger.error("Failed to download any images")
            return None

        logger.info(f"Prepared {len(downloaded_paths)} images for posting")
        return downloaded_paths
