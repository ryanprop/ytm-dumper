# Backup your YouTube Music Cache / Offline data

**Important: This tool requires a rooted Android phone and ADB (Android Debug Bridge) to function. It will not work without root access!**

This comes without any warranty. Use it at your own risk and always respect local copyright laws.

## Description

This tool allows you to backup your downloaded YouTube Music content (both cache and offline downloads) from your rooted Android device.
It retrieves the necessary encryption key, database files containing metadata, and the encrypted media files.
The tool then decrypts these media files and optionally adds metadata (title, artist, cover art) to them.

## Preparation

These steps are generally needed only once to set up the environment.

1.  **Initialize the `blackboxprotobuf` submodule:** \
    This dependency is used for decoding protocol buffer messages found in the YouTube Music databases.
    ```sh
    git submodule init blackboxprotobuf
    git submodule update
    ```

2.  **Enable ADB and Root Access on your Android device:** \
    Ensure you have ADB installed on your computer and that you have enabled USB debugging on your Android device.
    You also need to have root access enabled on your device for the following commands to work.

3.  **Fetch the encryption key and database files:** \
    Connect your Android device to your computer via USB and run the following ADB commands:
    ```sh
    adb root
    adb shell cat /data/data/com.google.android.apps.youtube.music/shared_prefs/youtube.xml \
        | grep -oP 'downloads_encryption_key">([^& <]+)' \
        | cut -d'>' -f 2 > encryption_key.txt
    adb pull /data/data/com.google.android.apps.youtube.music/databases
    mkdir music
    ```
    *   `adb root`: Restarts the ADB daemon with root privileges.
        This is required to read files of non-debugable packages.
    *   The `adb shell cat` command retrieves the YouTube Music shared preferences file and extracts the decryption key, saving it to `encryption_key.txt`.
    *   `adb pull`: Downloads the database directory containing `offline*.db` and `*.entitystore` which store metadata about your downloaded music. \
        **Important: You will need to repeat the `adb pull` command after downloading new music in the app.**
    *   `mkdir music`: Creates a directory to store the decrypted music files (you can choose a different name).

## Usage

Once you have the database files, the encryption key, and the cache index, you can run the `ytm_dumper` script to extract and decrypt your music.

```sh
python3 -m ytm_dumper.cli databases/ $(cat encryption_key.txt) --dest music/
```

#### Command-line Arguments

```
$ python3 -m ytm_dumper.cli --help
usage: cli.py [-h] [--dest DEST] [--no-metadata] [--streamdir STREAMDIR] [-m MATCH] [-l] [-s SINCE] databases key

Dump Youtube Music exo cache music/videos from a rooted Android phone.

positional arguments:
  databases             Path to the SQLite databases directory containing the offline*.db and *.entitystore files.
  key                   Base64 encoded decryption key. See README.md on how to obtain it.

options:
  -h, --help            show this help message and exit
  --dest DEST           Output path for all the media files.
  --no-metadata         Disable use of ffmpeg to write metadata (title, artist, cover art) to the decrypted files.
  --streamdir STREAMDIR
                        Path to the offline/*/streams exo cache directory.
  -m MATCH, --match MATCH
                        Only include files whose filename (based on artist and title) matches the given regular expression pattern.
  -l, --list            Only list files, do not download them.
  -s SINCE, --since SINCE
                        Only query songs stored since the timestamp, e.g. '1h', 'yesterday' or 'Jan 1'
```

## Understanding the Offline Data Structure

YouTube Music's offline functionality relies on SQLite databases to manage metadata and encrypted media files in the exocache:

*   **Offline Database:** This database (`offline*.db`) stores metadata about your downloaded music and videos.
    It contains information such as the video ID and metadata from which a `cache_key` can be derived for each song.
    This `cache_key` acts as an internal identifier for the downloaded content.

*   **Entity Store Database:** The entity store database (`*.entitystore`) holds various types of data, including information about cached videos and the metadata required to construct a `cache_key` associated with a downloaded media item.

*   **`cached_content_index.exi`:** This file acts as an index that links the internal `cache_key` (derived from the metadata in the databases) to a **`cache_id`** which is part of the `[cache_id].0.*.v3.exo` cache filename.
    That `.exo` file contains the encrypted media.
    The index itself is also encrypted and needs the decryption key to be read.

## TODOs

Here's a list of potential improvements, respective pull requests are welcome.

*    **Album information**: Extract album information and add them to the metadata. The `offline*.db` contains the table `playlist_video` mapping each video id to a playlist id (and it seems like albums are just playlists). The table `playlistV13` contains an `offline_playlist_data_proto` that seems to contain the album information.
*    **Database copy in python**: Grab the database from python to avoid the manual `adb pull` command.
*    **Incremental updates**: Keep track of the database state and download only newly added songs. This should help to reduce the runtime. (This is partially addressed by the `--since` flag now.)
*    **UI automation**: Run uiautomator2 to download specific music in the app, then dump it from its cache.

