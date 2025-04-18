import errno
import os.path
from typing import Optional, Tuple, TYPE_CHECKING

import logging
import re
import hashlib

if TYPE_CHECKING:
    from . import database_parser # Or: import ytm_db

logger = logging.getLogger(__name__)

# Regex for sanitizing filenames (replace common invalid chars)
FILENAME_INVALID_CHARS = re.compile(r'[\/*?:"<>|]')
# Regex for more aggressive sanitization (allow only alphanumeric, space, hyphen, dot)
FILENAME_SANITIZE_CHARS = re.compile(r'[^\w \-.]')
# Max filename length (conservative estimate)
MAX_FILENAME_LEN = 240


def generate_filename(video: database_parser.Video) -> Optional[str]:
    """Generates a base filename from video metadata."""
    filename_parts = []
    if video.artist:
        filename_parts.append(video.artist)
    if video.title:
        filename_parts.append(video.title)
    elif video.id: # Fallback to video ID if title is missing
        filename_parts.append(f"video_{video.id}")
    else:
        logger.warning("Cannot generate filename for video without title or ID. Skipping.")
        return None

    filename = " - ".join(filename_parts)
    # Basic sanitization for initial filename construction
    filename = FILENAME_INVALID_CHARS.sub('_', filename)
    return filename

def _sanitize_and_shorten_filename(filename: str, original_filename: str, ext: str) -> str:
    """Attempts to sanitize and shorten a filename if it causes filesystem errors."""
    # Try replacing potentially problematic characters with underscores.
    sanitized_filename = FILENAME_SANITIZE_CHARS.sub('_', filename)
    if not sanitized_filename or sanitized_filename == filename:
        # If sanitization didn't change anything or resulted in empty, use a hash fallback
        hash_digest = hashlib.sha1(original_filename.encode()).hexdigest()[:8]
        new_filename = f"ytm_dump_{hash_digest}"
        logger.warning(f"  Filename sanitization failed or ineffective for '{original_filename}', using hash: {new_filename}")
        return new_filename
    else:
        logger.warning(f"  Sanitized filename due to invalid characters: {sanitized_filename}")
        # Check length after initial sanitization
        if len(sanitized_filename + ext) > MAX_FILENAME_LEN:
             return _shorten_filename(sanitized_filename, original_filename, ext)
        return sanitized_filename

def _shorten_filename(filename: str, original_filename: str, ext: str) -> str:
    """Shortens a filename that is too long."""
    logger.warning(f"  Filename too long: '{filename}{ext}', shortening...")
    hash_digest = hashlib.sha1(original_filename.encode()).hexdigest()[:8]
    # Estimate max length allowed (conservative) - adjust if needed for specific FS
    base_name_len = MAX_FILENAME_LEN - len(ext) - len(hash_digest) - 1 # -1 for the hyphen
    if base_name_len < 1:
        # Fallback if even hash + extension is too long
        new_filename = f"{hash_digest}"
        logger.warning(f"  Cannot shorten sufficiently, using hash only: {new_filename}")
    else:
        # Take a slice of the original filename
        new_filename = f"{filename[:base_name_len]}-{hash_digest}"
        logger.warning(f"  Shortened filename: {new_filename}")
    return new_filename

def get_media_filename(
    dest_dir: str,
    filename: str,
    ext: str,
) -> Tuple[bool, str]:
    """
    Attempts to save the media data to a file, handling potential filesystem errors.

    Args:
        dest_dir: The destination directory.
        filename: The base filename (without extension).
        ext: The file extension (including the dot).
        data: The media data in bytes.
        video: The video metadata object.
        add_metadata: Whether to add metadata tags.

    Returns:
        A tuple: (success_status, final_filename or error_message).
                 success_status is True if saved successfully, False otherwise.
    """
    original_filename = filename
    max_retries = 5 # Limit retries for sanitization/shortening
    retries = 0

    while retries < max_retries:
        full_filename = os.path.join(dest_dir, filename + ext)
        try:
            # Check if the file already exists to avoid re-downloading/overwriting.
            if os.path.exists(full_filename):
                logger.info(f"  Skipping existing file: {full_filename}")
                return True, "skipped_existing" # Indicate skipped

            # Ensure the destination directory exists.
            os.makedirs(dest_dir, exist_ok=True)

            # Write the decrypted data to the file.
            return open(full_filename, 'wb'), full_filename

        except FileNotFoundError:
            # Handle cases where the filename contains characters invalid for the filesystem.
            filename = _sanitize_and_shorten_filename(filename, original_filename, ext)
            retries += 1
            continue # Retry saving with the new name

        except OSError as oserr:
            # The computed name may be too long, in which case we need to shorten it.
            if oserr.errno == errno.ENAMETOOLONG:
                filename = _shorten_filename(filename, original_filename, ext)
                retries += 1
                continue # Retry saving with the shortened name
            else:
                # Handle other OS errors during file writing.
                err_msg = f"OSError writing file {filename + ext}: {oserr}"
                logger.error(f"  {err_msg}. Skipping this file.")
                return None, err_msg

        except Exception as e:
             # Catch any other unexpected errors during file writing or metadata tagging.
             err_msg = f"Unexpected error processing file {filename + ext}: {e}"
             logger.error(f"  {err_msg}. Skipping this file.")
             return None, err_msg

    # If loop finishes without success
    err_msg = f"Failed to save file '{original_filename}{ext}' after multiple retries."
    logger.error(f"  {err_msg}")
    return False, err_msg