import os
import subprocess
import sys

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
):
    """
    TODO document
    """
    subproc_stdout = subprocess.DEVNULL
    subproc_stderr = subprocess.STDOUT
    def run_proc(prog: str, *args: str):
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

    # 1. Create a temporary looped middle segment trimmed to exact length
    mid_temp = "mid_temp.mp4"
    print("Generating looped middle segment...")
    run_proc(
        'ffmpeg',
        '-y',
        '-stream_loop', '-1', # loops infinitely
        '-i', mid_path,
        '-t', str(d_gap), # limits the total duration of the output
        '-c', 'copy', mid_temp)

    # 2. Create a concat list file for ffmpeg
    with open('concat_list.txt', 'w') as f:
        _ = f.write(f"file '{intro_path}'\n")
        _ = f.write(f"file '{mid_temp}'\n")
        _ = f.write(f"file '{outro_path}'\n")

    # 3. Concatenate videos and add the audio file
    print("Assembling final video...")
    run_proc(
        'ffmpeg', '-y',
        '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', # Video sequence
        '-i', audio_path,                                      # Audio track
        '-map', '0:v', '-map', '1:a',                          # Use video from concat, audio from file
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',    # Encode to ensure compatibility
        '-c:a', 'aac', '-shortest',                            # Audio codec and trim to shortest
        output_path)

    # Cleanup
    os.remove(mid_temp)
    os.remove('concat_list.txt')
    print(f"Done! Saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python audio_to_video.py <audio> <intro> <mid> <outro> <output>")
        sys.exit(1)
    create_video(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
