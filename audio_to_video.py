import os
import subprocess
import sys
import tempfile
from math import nan, isnan

def get_duration(file: str):
    """Returns the duration of a file in seconds."""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = result.stdout.strip()
    if out == 'N/A':
        return nan
    return float(out)

def get_resolution(file: str) -> tuple[int, int]|None:
    """Returns the resolution of a video file as."""
    cmd = [
        'ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height',
        '-of', 'csv=p=0', file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    out = result.stdout.strip() # "1920,1080"
    if not out:
        return None
    ws, hs = out.split(',')
    return (int(ws), int(hs))

def create_video(
    audio_path: str,
    intro_path: str,
    mid_path: str,
    outro_path: str,
    output_path: str,
    intro_duration: float = 3.0,
    outro_duration: float = 3.0,
    work_dir: str = '',
    verbose: int = 0,
):
    """
    Creates a video by concatenating an intro, a looped middle segment (to fill the gap),
    and an outro, then overlays the provided audio file.

    Args:
    - audio_path: Path to the source audio file.
    - intro_path: Path to the intro video clip or image.
    - mid_path: Path to the background loop video clip.
    - outro_path: Path to the outro video clip or image.
    - output_path: Path where the final video will be saved.
    - intro_duration: Duration in seconds if intro is a still image.
    - outro_duration: Duration in seconds if outro is a still image.
    - verbose: Verbosity level (0: silent, 1: info, 2: debug).
    """
    subproc_stdout = None if verbose > 0 else subprocess.DEVNULL
    subproc_stderr = subprocess.STDOUT
    def run_proc(prog: str, *args: str):
        if verbose > 0:
            print(f"Running $ {prog} {args}")
        _ = subprocess.run([prog, *args], check=True, stdout=subproc_stdout, stderr=subproc_stderr)

    print("Analyzing files...")
    d_audio = get_duration(audio_path)
    raw_d_intro = get_duration(intro_path)
    raw_d_outro = get_duration(outro_path)

    # Determine actual durations for gap calculation
    d_intro = intro_duration if isnan(raw_d_intro) else raw_d_intro
    d_outro = outro_duration if isnan(raw_d_outro) else raw_d_outro

    # Compute mid-fill gap and use it to validate intro/outro durations vs audio
    d_gap = d_audio - (d_intro + d_outro)
    if d_gap < 0:
        print("Error: Intro and Outro are longer than the audio file.")
        sys.exit(1)

    print(f"Audio duration: {d_audio:.2f}s | Gap to fill: {d_gap:.2f}s")

    mid_temp = os.path.join(work_dir, "mid_temp.mp4")
    list_temp = os.path.join(work_dir, "concat_list.txt")
    res = get_resolution(mid_path)

    # Helper to handle image-to-video conversion if necessary
    def resolve_clip(path: str, duration: float, name: str):
        if not isnan(get_duration(path)):
            return path

        temp_clip = os.path.join(work_dir, f"{name}_temp.mp4")
        print(f"Converting still image {path} to video clip...")
        args = [
            '-i', path,
            '-t', str(duration),
            '-y',                 # Overwrite output files without asking
            '-loop', '1',         # Loop the input image infinitely
            '-c:v', 'libx264',    # Use H.264 video codec
            '-preset', 'fast',    # Faster encoding speed/quality tradeoff
            '-crf', '23',         # Constant Rate Factor (lower is higher quality)
            '-pix_fmt', 'yuv420p' # Ensure YUV 4:2:0 pixel format for compatibility
        ]
        if res:
            args.extend(['-s', f"{res[0]}x{res[1]}"])
        args.append(temp_clip)

        run_proc('ffmpeg', *args)
        return temp_clip

    final_intro = resolve_clip(intro_path, d_intro, "intro")
    final_outro = resolve_clip(outro_path, d_outro, "outro")

    # 1. Create a temporary looped middle segment trimmed to exact length
    print("Generating looped middle segment...")
    run_proc(
        'ffmpeg',
        '-i', mid_path,
        '-y',                 # Overwrite output files without asking
        '-stream_loop', '-1', # loops infinitely
        '-t', str(d_gap),     # limits the total duration of the output
        '-c', 'copy',         # Copy streams without re-encoding
        mid_temp)

    # 2. Create a concat list file for ffmpeg
    with open(list_temp, 'w') as f:
        _ = f.write(f"file '{os.path.abspath(final_intro)}'\n")
        _ = f.write(f"file '{os.path.abspath(mid_temp)}'\n")
        _ = f.write(f"file '{os.path.abspath(final_outro)}'\n")

    if verbose > 1:
        with open(list_temp, 'r') as f:
            print(f"Debug - Concat list contents:")
            for n, line in enumerate(f, 1):
                print(f"{n:3}> {line}")

    # 3. Concatenate videos and add the audio file
    print("Assembling final video...")
    run_proc(
        'ffmpeg',
        '-i', audio_path,
        '-y',                                               # Overwrite output files without asking
        '-f', 'concat', '-safe', '0', '-i', list_temp,      # Video sequence
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

    _ = parser.add_argument("-v", "--verbose", default=0,
                            action='count',
                            help="Verbosity level (0: silent, 1: some, or 2: debug); or repeat to increment")

    _ = parser.add_argument("--intro-duration", type=float, default=3.0,
                            help="Duration of intro if it is a still image (default: 3.0s)")

    _ = parser.add_argument("--outro-duration", type=float, default=3.0,
                            help="Duration of outro if it is a still image (default: 3.0s)")

    _ = parser.add_argument("--work-dir", type=str, default='',
                            help="Working directory to keep intermediate artifacts (deafult: temporary)")

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

    args = parser.parse_args()

    def run(work_dir: str):
        create_video(
            cast(str, args.audio),
            cast(str, args.intro),
            cast(str, args.mid),
            cast(str, args.outro),
            cast(str, args.output),
            intro_duration=cast(float, args.intro_duration),
            outro_duration=cast(float, args.outro_duration),
            work_dir=work_dir,
            verbose=cast(int, args.verbose),
        )

    work_dir = cast(str, args.work_dir)
    if work_dir:
        run(work_dir)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            run(tmpdir)
