## Me

> Context:
> - <tool>web_search</tool>

@{web_search}

A thing that would save me time is a script that could read the length of an MP3 (well, or maybe FLAC) audio, and add video to it consisting of an intro, the right number of loops of a short middle video, and an outro. I have been doing this manually because I'm already doing other stuff in Resolve, but...

## CodeCompanion (Ollama)

### Reasoning

The user wants a script that:
1. Reads the length of an audio file (MP3 or FLAC).
2. Creates a video by combining:
    - An intro video clip.
    - A short middle video clip looped for the remaining duration.
    - An outro video clip.
3. The final video should match the total length of the audio.

This is a classic task for `ffmpeg`.

Plan:
1. Identify the tools needed: `ffprobe` to get audio duration, and `ffmpeg` to construct the video.
2. Logic for looping:
    - Total Audio Duration ($T_{audio}$)
    - Intro Duration ($T_{intro}$)
    - Outro Duration ($T_{outro}$)
    - Middle Clip Duration ($T_{mid}$)
    - Required Loop Count = $\lceil (T_{audio} - T_{intro} - T_{outro}) / T_{mid} \rceil$
    - The middle section needs to be trimmed/looped exactly to fit.

Actually, a better way with `ffmpeg` is to use the `-stream_loop` flag or create a filter complex that loops and then trims to the exact length of the audio.

Wait, I should provide a script (likely Python or Bash) that automates this. Since the user didn't specify a language, Python is usually a good choice for flexibility, but a Bash script using `ffmpeg` directly is very efficient.

I will propose a Python script that uses `ffprobe` and `ffmpeg`.

Steps for the script:
1. Get duration of audio file using `ffprobe`.
2. Get durations of intro, middle, and outro clips using `ffprobe`.
3. Calculate how many times the middle clip needs to be looped to fill the gap between intro and outro.
4. Use `ffmpeg` to concatenate these pieces and add the audio.

Actually, a simpler `ffmpeg` command might be:
- Construct a file list for concatenation.
- Or use the `filter_complex`.

Let's refine the logic:
1. $D_{audio} = \text{duration of audio}$
2. $D_{intro} = \text{duration of intro}$
3. $D_{outro} = \text{duration of outro}$
4. $D_{gap} = D_{audio} - (D_{intro} + D_{outro})$
5. Loop middle clip until it exceeds $D_{gap}$, then trim to exactly $D_{gap}$.

Implementation details:
- `ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 input.mp3` gets duration.
- To loop a clip and trim it: `-stream_loop -1 -i middle.mp4` then use `-t $D_{gap}`.
- Concatenate intro + looped\_middle + outro using `concat` filter or demuxer.

Since I am "CodeCompanion" in Neovim, I should probably write this script into a file for the user if they want, but first I'll describe the solution and provide the code.

Wait, the prompt says: "A thing that would save me time is a script...". It's a request for a tool.

I'll suggest a Python script because it handles the math and command execution more cleanly than Bash for some users.

Wait, I should check if `ffmpeg` and `ffprobe` are installed? The user is on Linux. They likely have them or can get them.

Let's write a Python script that:
1. Takes arguments: audio file, intro video, middle video, outro video, output name.
2. Uses `subprocess` to run `ffprobe` and `ffmpeg`.
3. Handles the looping logic.

Actually, a very elegant way is using the `concat` filter in ffmpeg:
`ffmpeg -i intro.mp4 -stream_loop -1 -i middle.mp4 -i outro.mp4 -i audio.mp3 -filter_complex "[1:v]trim=duration=GAP[mid]; [0:v][mid][2:v]concat=n=3:v=1:a=0[outv]" -map "[outv]" -map 3:a -shortest output.mp4`
Wait, `trim` might not work as expected with `-stream_loop`.
Better:
1. Loop middle clip to a temporary file or use the loop filter.
2. Use `-t` on the looped input.

Actually, the easiest way is:
1. Calculate $D_{gap}$.
2. Create a temporary segment for the looped middle part: `ffmpeg -stream_loop -1 -i middle.mp4 -t $D_{gap} -c copy mid_temp.mp4`.
3. Concatenate intro, mid_temp, and outro using the concat demuxer (fastest).

Let's refine the Python script approach.

### Response

To automate this process, the best tool for the job is `ffmpeg` combined with `ffprobe`. Since you need to perform calculations based on audio length, a Python script is the most reliable way to glue these commands together.

### Plan
1. **Extract Durations**: Use `ffprobe` to get the exact duration of the audio file and the intro/outro clips.
2. **Calculate Gap**: Subtract the intro and outro durations from the total audio length to find how much "middle" content is needed.
3. **Create Looped Segment**: Generate a temporary video clip of the middle asset, looped as many times as necessary and trimmed to the exact remaining duration.
4. **Concatenate**: Merge the intro, the generated middle segment, and the outro using the `ffmpeg` concat demuxer for speed.
5. **Add Audio**: Attach the original audio file to the final video stream.

Here is a complete script to achieve this.

````python {audio_to_video.py}
import subprocess
import sys
import os

def get_duration(file):
    """Returns the duration of a file in seconds."""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1', file
    ]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return float(result.stdout.strip())

def create_video(audio_path, intro_path, mid_path, outro_path, output_path):
    print("Analyzing files...")
    d_audio = get_duration(audio_path)
    d_intro = get_duration(intro_path)
    d_outro = get_duration(outro_path)
    
    d_gap = d_audio - (d_intro + d_outro)
    
    if d_gap < 0:
        print("Error: Intro and Outro are longer than the audio file.")
        sys.exit(1)

    print(f"Audio duration: {d_audio:.2f}s | Gap to fill: {d_gap:.2f}s")

    # 1. Create a temporary looped middle segment trimmed to exact length
    mid_temp = "mid_temp.mp4"
    print("Generating looped middle segment...")
    # -stream_loop -1 loops infinitely, -t limits the total duration of the output
    subprocess.run([
        'ffmpeg', '-y', '-stream_loop', '-1', '-i', mid_path,
        '-t', str(d_gap), '-c', 'copy', mid_temp
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # 2. Create a concat list file for ffmpeg
    with open('concat_list.txt', 'w') as f:
        f.write(f"file '{intro_path}'\n")
        f.write(f"file '{mid_temp}'\n")
        f.write(f"file '{outro_path}'\n")

    # 3. Concatenate videos and add the audio file
    print("Assembling final video...")
    subprocess.run([
        'ffmpeg', '-y', 
        '-f', 'concat', '-safe', '0', '-i', 'concat_list.txt', # Video sequence
        '-i', audio_path,                                     # Audio track
        '-map', '0:v', '-map', '1:a',                        # Use video from concat, audio from file
        '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',   # Encode to ensure compatibility
        '-c:a', 'aac', '-shortest',                           # Audio codec and trim to shortest
        output_path
    ], check=True)

    # Cleanup
    os.remove(mid_temp)
    os.remove('concat_list.txt')
    print(f"Done! Saved to {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 6:
        print("Usage: python audio_to_video.py <audio> <intro> <mid> <outro> <output>")
        sys.exit(1)
        
    create_video(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])
````

### Requirements
You must have `ffmpeg` and `ffprobe` installed on your Linux system:
```bash
sudo apt update && sudo apt install ffmpeg
```

### Usage
Run the script from your terminal passing the audio, intro, middle loop, outro, and desired output filename:

```bash
python3 audio_to_video.py music.mp3 intro.mp4 loop.mp4 outro.mp4 final_video.mp4
```

**Next suggestion:** Would you like me to add support for different video resolutions (automatic scaling) so that the clips match regardless of their original size?

## Me

> Context:
> - <tool>web_search</tool>


