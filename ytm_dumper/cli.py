import argparse
import base64
import datetime
import errno
import itertools
import glob
import hashlib
import os.path
import re
import subprocess
import sys

from . import adb_interface
from . import cache_parser
from . import database_parser
from . import exo_decrypt
from . import media_tagger

MIME_TO_EXT = re.compile('/(?P<ext>\w+)')

def find_file(pattern: str, dir: str) -> str:
    """Finds the first file matching a glob pattern within a directory."""
    results = os.path.join(dir, glob.glob(pattern, root_dir=dir)[0])
    if not results:
        raise FileNotFoundError(
            f"Error: Could not find any file matching pattern '{pattern}' in directory '{dir}'.")
    return results

def download_and_decrypt_video(video: database_parser.Video,
                  adb_device: adb_interface.Device,
                  cache_idx: cache_parser.CacheIdxParser,
                  key: bytes,
                  streams_dir: str) -> bytes:
    """Reads a remote cache file and decrypts its contents"""
    cache_id = cache_idx[video.cache_key]
    try:
        exo_file = adb_interface.read_remote_file(adb_device, f'{streams_dir}/*/streams/*/{cache_id}.0.*.v3.exo')
    except:
        print(f"Cannot find file '{cache_id}.0.*.v3.exo' for {video}", file=sys.stderr)
        raise
    return exo_decrypt.decrypt_media(exo_file, key, video.cache_key)

def construct_filename(video: database_parser.Video):
    filename = ''
    if video.artist:
        filename = f'{video.artist} - '
    if video.title:
        filename += video.title
    return filename

def find_filename(filename: str, ext: str, get_data_fn: callable, args: argparse.Namespace):
    while True:
        try:
            full_filename = os.path.join(args.dest, filename + ext)
            if os.path.exists(full_filename):
                print('Skipping', full_filename, file=sys.stderr)
                return None, full_filename
            return open(full_filename, 'wb'), full_filename
        except FileNotFoundError:
            # our filename may contain invalid characters.
            filename = re.sub(r'[^\w \-]', '_', filename)
        except OSError as oserr:
            if oserr.errno == errno.ENAMETOOLONG:
                # Shorten the filename and replace the end with a hash of the file contents
                if ext.startswith('.'):
                    # any stable hash-function will do
                    ext = base64.urlsafe_b64encode(hashlib.sha1(get_data_fn()).digest()[:3]).decode('ascii') + ext
                    filename = filename[:-5] + '-'
                else:
                    filename = filename[:-2] + '-'
                continue
            raise

def process_video(video: database_parser.Video,
                  args: argparse.Namespace,
                  adb_device: adb_interface.Device,
                  cache_idx: cache_parser.CacheIdxParser,
                  key: bytes):
    """Lists, decrypts and adds metadata to a single video."""
    filename = construct_filename(video)
    if not args.match.search(filename):
        return
    
    timestamp=''
    if video.timestamp:
        timestamp = datetime.datetime.fromtimestamp(video.timestamp / 1000).isoformat(sep=' ', timespec='seconds')

    print(timestamp, filename)
    if args.list:
        return

    ext = '.' + MIME_TO_EXT.search(video.mime).group('ext') if MIME_TO_EXT.search(video.mime) else ''
    # Decrypt the file only if we actually need it.
    data = []
    def get_data_fn():
        if not data:
            data.append(download_and_decrypt_video(video, adb_device, cache_idx, key, args.streamdir))
        return data[0]
    f, full_filename = find_filename(filename, ext, get_data_fn, args)
    if not f:
        return
    f.write(get_data_fn())
    f.close()

    if args.metadata:
        media_tagger.add_metadata(full_filename, video.title, video.artist, video.cover_url)

def main(args: argparse.Namespace) -> int:
    key = base64.b64decode(args.key + '==')
    adb_device = adb_interface.get_device()
    if adb_device is None:
        print("No ADB device found. Ensure a device is connected and authorized.", file=sys.stderr)
        return 1
    
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("Warning: ffmpeg not found or not working. Metadata tagging will be disabled.", file=sys.stderr)
        args.metadata = False

    print('Reading offline DB...', file=sys.stderr)
    offline_db_file = find_file('offline.*.db', args.databases)
    offline_db = database_parser.OfflineVideoDb(offline_db_file, since=args.since)

    print('Reading entity store...', file=sys.stderr)
    entity_store_file = find_file('*.entitystore', args.databases)
    entity_store = database_parser.EntityStore(entity_store_file, since=args.since)

    if args.list:
        cache_idx = None
    else:
        print('Reading cache_idx...', end='', flush=True, file=sys.stderr)
        cache_idx_data = adb_interface.read_remote_file(adb_device,
                                                        f'{args.streamdir}/*/streams/cached_content_index.exi')
        cache_idx = cache_parser.CacheIdxParser(cache_idx_data, key)
        print('done', file=sys.stderr)    

    videos = list(itertools.chain(offline_db, entity_store))
    for video in sorted(videos, key=lambda v: v.timestamp):
        process_video(video, args, adb_device, cache_idx, key)

def parse_since(arg: str) -> datetime.datetime:
    try:
        import dateparser
    except ImportError:
        print("dateparser module is required for '--since' argument. Please install it (e.g., 'pip install dateparser').", file=sys.stderr)
        raise
    date = dateparser.parse(arg)
    if not date:
        raise ValueError(f"Invalid dateparser format '{arg}', try '--since yesterday' instead.")
    return date

def parse_args():
    parser = argparse.ArgumentParser(description="Dump Youtube Music exo cache music/videos from a rooted Android phone.")
    parser.add_argument("databases",
                        help="Path to the SQLite databases directory containing the offline*.db and *.entitystore files.")
    parser.add_argument("key", help="Base64 encoded decryption key. See README.md on how to obtain it.")
    parser.add_argument("--dest", help="Output path for all the media files.", default=".")
    parser.add_argument("--no-metadata", action="store_false", dest="metadata", default=True,
                        help="Disable use of ffmpeg to write metadata (title, artist, cover art) to the decrypted files.")
    parser.add_argument("--streamdir",
                        help="Path to the offline/*/streams exo cache directory.",
                        default='/sdcard/Android/data/com.google.android.apps.youtube.music/files/offline')
    parser.add_argument("-m", "--match", default='', type=re.compile,
                        help="Only include files whose filename (based on artist and title) matches the given regular expression pattern.")
    parser.add_argument("-l", "--list", action="store_true",
                        help="Only list files, do not download them.")
    parser.add_argument("-s", "--since", type=parse_since,
                        help="Only query songs stored since the timestamp, e.g. '1h', 'yesterday' or 'Jan 1'")

    return parser.parse_args()

if __name__ == '__main__':
    exit(main(parse_args()))
   
