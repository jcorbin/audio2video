# Looped video creation script

This tool assembles a video by combining an intro, a looping middle segment, and an outro, 
synchronizing the total length to match a provided audio track.

**Example Usage**: audio/video inputs
    python audio_to_video.py audio.mp3 intro.mp4 loop.mp4 outro.mp4 output.mp4

**Example Usage**: still frame image intro/outros
    python audio_to_video.py audio.mp3 intro.png loop.mp4 outro.png output.mp4 \
        --intro-duration 5.0 --outro-duration 2.0

Run `python audio_to_video.py -h` codec and debugging options.

**AI Disclaimer**:
- this script was developed with the assistance the Gemma4:31B LLM (AI)
- all inference ran on local/personal hardware
- no datacenters were used to generate these tokens
- all LLM session transcripts available in `llm_turns/` for inspection
