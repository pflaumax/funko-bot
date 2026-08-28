"""Image handling for Funko product images.

This module handles downloading, resizing, and managing product images
for posting to Bluesky.
"""

import logging
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests
from PIL import Image

logger = logging.getLogger("funko_bot.image_handler")

DEFAULT_MAX_SIZE = (1200, 1200)  # Larger max size for better quality
IMAGE_QUALITY = 95  # Starting rung of the quality ladder
MIN_QUALITY = 40  # Below this, artefacts are worse than a bigger upload
MAX_UPLOAD_BYTES = 950_000  # Bluesky rejects blobs around 1MB
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

    def download_image(self, url: str, save_path: str) -> str | None:
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
            logger.exception(f"Unexpected error downloading image: {e}")
            return None

    def resize_image(
        self, image_path: str, max_size: tuple[int, int] = DEFAULT_MAX_SIZE
    ) -> str | None:
        """Normalise an image to a JPEG that Bluesky will accept.

        Every image is re-encoded, not just oversized ones. Funko serves
        800x800 PNGs, which sat below the resize threshold and were being
        uploaded byte-for-byte under a .jpg filename — ~590KB of PNG per
        image where JPEG costs well under a tenth of that.

        Args:
            image_path: Path to the image file. Rewritten in place.
            max_size: Maximum (width, height).

        Returns:
            Path to the prepared image, or None on failure.
        """
        try:
            with Image.open(image_path) as img:
                img.load()
                original_size = img.size

                # Flatten any transparency onto white: product shots are cut
                # out on alpha, and JPEG has no alpha channel to keep.
                if img.mode in ("RGBA", "LA", "P"):
                    img = img.convert("RGBA")
                    background = Image.new("RGB", img.size, (255, 255, 255))
                    background.paste(img, mask=img.split()[-1])
                    img = background
                elif img.mode != "RGB":
                    img = img.convert("RGB")

                if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)

                quality = IMAGE_QUALITY
                while True:
                    img.save(
                        image_path,
                        "JPEG",
                        quality=quality,
                        optimize=True,
                        subsampling=0,
                    )
                    written = Path(image_path).stat().st_size
                    if written <= MAX_UPLOAD_BYTES or quality <= MIN_QUALITY:
                        break
                    quality -= 10

                logger.info(
                    f"Prepared {original_size} -> {img.size} JPEG q{quality}, "
                    f"{written / 1024:.0f}KB"
                )
                if written > MAX_UPLOAD_BYTES:
                    logger.warning(
                        f"Image still {written / 1024:.0f}KB at q{quality}; "
                        f"upload may be rejected"
                    )
                return image_path

        except (OSError, ValueError) as e:
            logger.exception(f"Failed to prepare image {image_path}: {e}")
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
                # Skip dotfiles: .gitkeep keeps this directory in the repo
                # and is always older than the cutoff.
                if image_file.is_file() and not image_file.name.startswith("."):
                    file_mtime = datetime.fromtimestamp(image_file.stat().st_mtime)

                    if file_mtime < cutoff_time:
                        logger.debug(f"Deleting old image: {image_file}")
                        image_file.unlink()
                        deleted_count += 1

            logger.info(f"Cleaned up {deleted_count} old images")
            return deleted_count

        except Exception as e:
            logger.exception(f"Error during image cleanup: {e}")
            return deleted_count

    def download_and_prepare(self, product: dict) -> list | None:
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
