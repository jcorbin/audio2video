'''
This tool assembles a video by combining an intro, a looping middle segment, and an outro,
synchronizing the total length to match a provided audio track.

**Example Usage**: audio/video inputs
    python audio_to_video.py audio.mp3 intro.mp4 loop.mp4 outro.mp4 output.mp4

**Example Usage**: still frame image intro/outros
    python audio_to_video.py audio.mp3 intro.png loop.mp4 outro.png output.mp4 \
        --intro-duration 5.0 --outro-duration 2.0

Run `python audio_to_video.py -h` codec and debugging options.

**AI Disclaimer**:
    This script was developed with the assistance the Gemma4:31B LLM (AI); all
    inference ran on local/personal hardware, no datacenters were used to
    generate these tokens.
'''

import os
import subprocess
import sys
import tempfile
from math import nan, isnan

def get_duration(file: str):
    """Returns the duration of a file in seconds."""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        file
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
    fade_duration: float = 0.0,
    work_dir: str = '',
    verbose: int = 0,
    audio_codec: str = 'aac',
    video_codec: str = 'libx264',
    ffmpeg_preset: str = 'fast',
    ffmpeg_crf: str = '23',
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
    - fade_duration: Duration in seconds for in/outro fade.
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
            '-y',                 # Overwrite output files without asking
            '-loop', '1',         # Loop the input image infinitely
            '-i', path,
            '-t', str(duration),  # Resolved clip duration
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
        '-y',                  # Overwrite output files without asking
        '-stream_loop', '-1',  # loops infinitely
        '-i', mid_path,
        '-t', str(d_gap),      # limits the total duration of the output
        '-pix_fmt', 'yuv420p', # Ensure YUV 4:2:0 pixel format for compatibility
        '-c:v', video_codec,
        '-preset', ffmpeg_preset,
        '-crf', ffmpeg_crf,
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

    ffmpeg_args = [
        '-y',               # Overwrite output files without asking
        '-f', 'concat',     # Use the concat demuxer to join files in a list
        '-safe', '0',       # Disable safe filename checks for absolute paths
        '-i', list_temp,    # Video sequence
        '-i', audio_path,   # Audio Track
        '-map', '0:v',      # Use video from concat
        '-map', '1:a',      # Use audio from file
        '-t', str(d_audio), # Hard limit to ensure output matches audio length
        '-shortest',        # Trim to shortest stream
    ]

    if fade_duration > 0:
        actual_fade_out = min(fade_duration, d_intro)
        actual_fade_in = min(fade_duration, d_outro)
        st_out = d_intro - actual_fade_out
        st_in = d_audio - d_outro

        vf_filter = f"fade=t=out:st={st_out}:d={actual_fade_out},fade=t=in:st={st_in}:d={actual_fade_in}"
        af_filter = f"afade=t=out:st={st_out}:d={actual_fade_out},afade=t=in:st={st_in}:d={actual_fade_in}"
        ffmpeg_args.extend(['-vf', vf_filter, '-af', af_filter])

    ffmpeg_args.extend([
        '-c:v', video_codec,
        '-c:a', audio_codec,
        '-preset', ffmpeg_preset,
        '-crf', ffmpeg_crf,
        output_path
    ])

    run_proc('ffmpeg', *ffmpeg_args)

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

    _ = parser.add_argument("--fade-duration", type=float, default=0.0,
                            help="Duration of fade-out for intro and fade-in for outro (default: 0.0s)")

    _ = parser.add_argument("--work-dir", type=str, default='',
                            help="Working directory to keep intermediate artifacts (deafult: temporary)")

    _ = parser.add_argument("--audio-codec", type=str, default='aac',
                            help="Audio codec to use (default: aac)")

    _ = parser.add_argument("--video-codec", type=str, default='libx264',
                            help="Video codec to use (default: libx264)")

    _ = parser.add_argument("--preset", type=str, default='fast',
                            help="FFmpeg preset for encoding speed/quality tradeoff (default: fast)")

    _ = parser.add_argument("--crf", type=str, default='23',
                            help="Constant Rate Factor for quality (default: 23)")

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
            fade_duration=cast(float, args.fade_duration),
            work_dir=work_dir,
            verbose=cast(int, args.verbose),
            audio_codec=cast(str, args.audio_codec),
            video_codec=cast(str, args.video_codec),
            ffmpeg_preset=cast(str, args.preset),
            ffmpeg_crf=cast(str, args.crf),
        )

    work_dir = cast(str, args.work_dir)
    if work_dir:
        run(work_dir)
    else:
        with tempfile.TemporaryDirectory() as tmpdir:
            run(tmpdir)
