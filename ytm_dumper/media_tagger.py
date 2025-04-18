import argparse
import os
import subprocess
import tempfile

def add_metadata(input_file: str, title: str = None, artist: str = None, cover_image: str = None):
    """
    Adds title, artist, album, and cover art to an audio file in-place using ffmpeg.

    Args:
        input_file: Path to the input audio file.
        title: Title of the audio.
        artist: Artist of the audio.
        album: Album of the audio.
        cover_image: Path to the cover image file.
    """
    _, suffix = os.path.splitext(input_file)
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False, dir=os.path.dirname(input_file)) as temp_file:
        output_file = temp_file.name

        command = ['ffmpeg', '-i', input_file]

        if cover_image:
            command.extend(['-i', cover_image, '-map', '0:a', '-map', '1:v']) 

        command.extend(['-c:a', 'copy'])

        if title:
                command.extend(['-metadata:s:a', f'title={title}'])
        if artist:
                command.extend(['-metadata:s:a', f'artist={artist}'])

        if cover_image:
            command.extend(['-metadata:s:v', 'title="Album cover"'])

        command.extend(['-y', output_file])

        try:
            subprocess.run(command, check=True)
            os.replace(output_file, input_file)
        except subprocess.CalledProcessError as e:
            print(f"Error adding metadata: {e}")
            os.remove(output_file)    # Remove temporary file on error


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Add metadata to an audio file.")
    parser.add_argument("input_file", help="Path to the input audio file")
    parser.add_argument("-t", "--title", help="Title of the audio")
    parser.add_argument("-a", "--artist", help="Artist of the audio")
    parser.add_argument("--cover", help="Path to the cover image file")

    args = parser.parse_args()

    add_metadata(args.input_file, args.title, args.artist, args.cover)