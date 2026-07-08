import os
import subprocess
import sys
import tempfile

def get_duration(file: str):
    """Returns the duration of a file in seconds."""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return float(result.stdout.strip())

def create_video(
    audio_path: str,
    intro_path: str,
    mid_path: str,
    outro_path: str,
    output_path: str,
    verbose: int = 0,
):
    """
    Creates a video by concatenating an intro, a looped middle segment (to fill the gap),
    and an outro, then overlays the provided audio file.

    Args:
    - audio_path: Path to the source audio file.
    - intro_path: Path to the intro video clip.
    - mid_path: Path to the background loop video clip.
    - outro_path: Path to the outro video clip.
    - output_path: Path where the final video will be saved.
    - verbose: Verbosity level (0: silent, 1: info, 2: debug).
    """
    subproc_stdout = subprocess.STDOUT if verbose > 0 else subprocess.DEVNULL
    subproc_stderr = subprocess.STDOUT
    def run_proc(prog: str, *args: str):
        if verbose > 0:
            print(f"Running $ {prog} {args}")
        _ = subprocess.run([prog, *args], check=True, stdout=subproc_stdout, stderr=subproc_stderr)

    print("Analyzing files...")
    d_audio = get_duration(audio_path)
    d_intro = get_duration(intro_path)
    d_outro = get_duration(outro_path)

    # Compute mid-fill gap and use it to validate intro/outro durations vs audio
    d_gap = d_audio - (d_intro + d_outro)
    if d_gap < 0:
        print("Error: Intro and Outro are longer than the audio file.")
        sys.exit(1)

    print(f"Audio duration: {d_audio:.2f}s | Gap to fill: {d_gap:.2f}s")

    with tempfile.TemporaryDirectory() as tmpdir:
        mid_temp = os.path.join(tmpdir, "mid_temp.mp4")
        list_temp = os.path.join(tmpdir, "concat_list.txt")

        # 1. Create a temporary looped middle segment trimmed to exact length
        print("Generating looped middle segment...")
        run_proc(
            'ffmpeg',
            '-y',
            '-stream_loop', '-1', # loops infinitely
            '-i', mid_path,
            '-t', str(d_gap), # limits the total duration of the output
            '-c', 'copy', mid_temp)

        # 2. Create a concat list file for ffmpeg
        with open(list_temp, 'w') as f:
            _ = f.write(f"file '{os.path.abspath(intro_path)}'\n")
            _ = f.write(f"file '{os.path.abspath(mid_temp)}'\n")
            _ = f.write(f"file '{os.path.abspath(outro_path)}'\n")

        if verbose > 1:
            with open(list_temp, 'r') as f:
                print(f"Debug - Concat list contents:")
                for n, line in enumerate(f, 1):
                    print(f"{n:3}> {line}")

        # 3. Concatenate videos and add the audio file
        print("Assembling final video...")
        run_proc(
            'ffmpeg', '-y',
            '-f', 'concat', '-safe', '0', '-i', list_temp,      # Video sequence
            '-i', audio_path,                                   # Audio track
            '-map', '0:v', '-map', '1:a',                       # Use video from concat, audio from file
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '23', # Encode to ensure compatibility
            '-c:a', 'aac', '-shortest',                         # Audio codec and trim to shortest
            output_path)

    print(f"Done! Saved to {output_path}")

if __name__ == "__main__":
    import argparse
    from typing import cast

    parser = argparse.ArgumentParser(
        description="Assemble a video from intro, mid-loop, and outro clips with an audio track.")

    _ = parser.add_argument("audio",
                            help="Path to the audio file")
    _ = parser.add_argument("intro",
                            help="Path to the intro video clip")
    _ = parser.add_argument("mid",
                            help="Path to the middle loop video clip")
    _ = parser.add_argument("outro",
                            help="Path to the outro video clip")
    _ = parser.add_argument("output",
                            help="Output video file path")
    _ = parser.add_argument("-v", "--verbose", default=0,
                            action='count',
                            help="Verbosity level (0: silent, 1: some, or 2: debug); or repeat to increment")

    args = parser.parse_args()
    create_video(
        cast(str, args.audio),
        cast(str, args.intro),
        cast(str, args.mid),
        cast(str, args.outro),
        cast(str, args.output),
        verbose=cast(int, args.verbose),
    )
