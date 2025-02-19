#!/usr/bin/env python3
f"""
{__file__}

This script accepts one or more files and/or directories as unnamed parameters.
It recursively finds media files (based on extension), probes each file with ffprobe to 
determine its streams (video, audio, subtitles) and associated metadata (including language and filesize),
and then—based on command‐line filtering options—builds an ffmpeg command that “cleans” the file by mapping 
only the streams that should be kept. The output file is written in the same directory with “.cleaned” added before 
the file extension.

Filtering options (each accepts a comma‐separated list of language codes or track numbers):
  -k,  --keep             => “keep” (i.e. remove all streams that do not match) for both audio and subtitles.
  -r,  --remove           => “remove” (i.e. drop streams that match) for both audio and subtitles.
  -ka, --keep-audio       => like -k but for audio only.
  -ra, --remove-audio     => like -r but for audio only.
  -ks, --keep-subtitles   => like -k but for subtitles only.
  -rs, --remove-subtitles => like -r but for subtitles only.
  --dry-run               => print ffmpeg command without executing it.

Notes:
 • You cannot combine -r with (-ra or -rs) nor -k with (-ka or -ks).
 • If an element appears in both the keep and remove lists for a given type, it is removed from the remove list and a warning is issued.
 • A generic -r is treated as both -ra and -rs; likewise -k is treated as both -ka and -ks.
 • For any list, items that are integers (e.g. “2”) refer to track numbers (1-based indexing).
 • For strings, a lookup table is used so that, for example, a user’s “en” will match “eng”, “English”, etc.
 • Before running ffmpeg the script prints to stderr which languages (tracks) will be removed.
 • While ffmpeg runs, the script polls the output file every second to estimate remaining time and current speed.
 • When ffmpeg finishes, the output file’s path is printed to stdout, and the remaining streams plus processing stats are printed to stderr.

Usage Examples:
  {__file__} -ra ru -ks en /folder/input.mkv
  {__file__} -ka en -rs ru,de /folder/input.mkv
  {__file__} -k en /folder/input.mkv
  {__file__} -r ru,de /folder/input.mkv

For help run:
  {__file__} -h
"""

import argparse
import os
import sys
import subprocess
import json
import time

# --- Language lookup table and helper functions ---

LANGUAGE_MAP = {
    #TODO: make less redundant even if at expense of efficiency
    "af": "Afrikaans", "afrikaans": "Afrikaans",
    "am": "Amharic", "amh": "Amharic", "amharic": "Amharic",
    "ar": "Arabic", "ara": "Arabic", "arabic": "Arabic",
    "az": "Azerbaijani", "aze": "Azerbaijani", "azerbaijani": "Azerbaijani",
    "be": "Belarusian", "bel": "Belarusian", "belarusian": "Belarusian",
    "bg": "Bulgarian", "bul": "Bulgarian", "bulgarian": "Bulgarian",
    "bn": "Bengali", "ben": "Bengali", "bengali": "Bengali",
    "bs": "Bosnian", "bos": "Bosnian", "bosnian": "Bosnian",
    "co": "Corsican", "cos": "Corsican", "corsican": "Corsican",
    "cs": "Czech", "cze": "Czech", "czech": "Czech",
    "da": "Danish", "dan": "Danish", "danish": "Danish",
    "de": "German", "deu": "German", "german": "German", "deutsch": "German",
    "el": "Greek", "gre": "Greek", "greek": "Greek",
    "en": "English", "eng": "English", "english": "English",
    "es": "Spanish", "spa": "Spanish", "spanish": "Spanish",
    "et": "Estonian", "est": "Estonian", "estonian": "Estonian",
    "eu": "Basque", "baq": "Basque", "basque": "Basque",
    "fa": "Persian", "per": "Persian", "persian": "Persian",
    "fi": "Finnish", "fin": "Finnish", "finnish": "Finnish",
    "fil": "Filipino", "filipino": "Filipino",
    "fr": "French", "fra": "French", "french": "French",
    "he": "Hebrew", "heb": "Hebrew", "hebrew": "Hebrew",
    "hi": "Hindi", "hin": "Hindi", "hindi": "Hindi",
    "hr": "Croatian", "hrv": "Croatian", "croatian": "Croatian",
    "hu": "Hungarian", "hun": "Hungarian", "hungarian": "Hungarian",
    "hy": "Armenian", "arm": "Armenian", "armenian": "Armenian",
    "id": "Indonesian", "ind": "Indonesian", "indonesian": "Indonesian",
    "it": "Italian", "ita": "Italian", "italian": "Italian",
    "ja": "Japanese", "jpn": "Japanese", "japanese": "Japanese",
    "ko": "Korean", "kor": "Korean", "korean": "Korean",
    "lt": "Lithuanian", "lit": "Lithuanian", "lithuanian": "Lithuanian",
    "lv": "Latvian", "lav": "Latvian", "latvian": "Latvian",
    "ms": "Malay", "may": "Malay", "malay": "Malay",
    "nl": "Dutch", "dut": "Dutch", "dutch": "Dutch",
    "no": "Norwegian", "nor": "Norwegian", "norwegian": "Norwegian",
    "ny": "Chichewa", "nya": "Chichewa", "chichewa": "Chichewa",
    "pl": "Polish", "pol": "Polish", "polish": "Polish",
    "pt": "Portuguese", "por": "Portuguese", "portuguese": "Portuguese",
    "ro": "Romanian", "rum": "Romanian", "romanian": "Romanian",
    "ru": "Russian", "rus": "Russian", "russian": "Russian",
    "sk": "Slovak", "slo": "Slovak", "slovak": "Slovak",
    "sl": "Slovenian", "slv": "Slovenian", "slovenian": "Slovenian",
    "sq": "Albanian", "alb": "Albanian", "albanian": "Albanian",
    "sr": "Serbian", "srb": "Serbian", "serbian": "Serbian",
    "sv": "Swedish", "swe": "Swedish", "swedish": "Swedish",
    "ta": "Tamil", "tam": "Tamil", "tamil": "Tamil",
    "th": "Thai", "tha": "Thai", "thai": "Thai",
    "tr": "Turkish", "tur": "Turkish", "turkish": "Turkish",
    "uk": "Ukrainian", "ukr": "Ukrainian", "ukrainian": "Ukrainian",
    "ur": "Urdu", "urd": "Urdu", "urdu": "Urdu",
    "vi": "Vietnamese", "vie": "Vietnamese", "vietnamese": "Vietnamese",
    "zh-cn": "Chinese (Simplified)", "zh-tw": "Chinese (Traditional)",
    "zh": "Chinese", "chi": "Chinese", "chinese": "Chinese"
}

def normalize_language(lang) -> str:
    """Return the long form for a language code if known; otherwise capitalize."""
    if not lang:
        return "Undetermined"
    
    key = lang.strip().lower()

    return LANGUAGE_MAP.get(key, lang.capitalize())

# --- Argument parsing ---

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Clean media files by removing unwanted audio/subtitle streams.",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", nargs="*", help="Files and/or directories to process")
    parser.add_argument("-k", "--keep", help="Keep only specified language(s) for both audio and subtitles (comma-separated)")
    parser.add_argument("-r", "--remove", help="Remove specified language(s) for both audio and subtitles (comma-separated)")
    parser.add_argument("-ka", "--keep-audio", help="Keep only specified audio stream(s) (languages or track numbers, comma-separated)")
    parser.add_argument("-ra", "--remove-audio", help="Remove specified audio stream(s) (languages or track numbers, comma-separated)")
    parser.add_argument("-ks", "--keep-subtitles", help="Keep only specified subtitle stream(s) (languages or track numbers, comma-separated)")
    parser.add_argument("-rs", "--remove-subtitles", help="Remove specified subtitle stream(s) (languages or track numbers, comma-separated)")
    parser.add_argument("--keep-subtitle", dest="keep_subtitles_alias", help=argparse.SUPPRESS)
    parser.add_argument("--remove-subtitle", dest="remove_subtitles_alias", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="Print the ffmpeg command without executing it")
    args = parser.parse_args()

    return args

def process_args(args) -> argparse.Namespace:
    # If alias options are provided, use them if the primary ones are not given.
    if args.keep_subtitles_alias and not args.keep_subtitles:
        args.keep_subtitles = args.keep_subtitles_alias
    if args.remove_subtitles_alias and not args.remove_subtitles:
        args.remove_subtitles = args.remove_subtitles_alias

    # Check for conflicts:
    # -r cannot be combined with -ra or -rs.
    if args.remove and (args.remove_audio or args.remove_subtitles):
        sys.stderr.write("Error: -r/--remove cannot be combined with -ra/--remove-audio or -rs/--remove-subtitles\n")
        sys.exit(1)
    # -k cannot be combined with -ka or -ks.
    if args.keep and (args.keep_audio or args.keep_subtitles):
        sys.stderr.write("Error: -k/--keep cannot be combined with -ka/--keep-audio or -ks/--keep-subtitles\n")
        sys.exit(1)

    return args

def parse_list(arg_str) -> tuple[list[int], list[str]]:
    """
    Parses a comma-separated list and returns a tuple: (list_of_ints, list_of_strings)
    Strings are sorted by descending length then alphabetically (case insensitive).
    """
    if not arg_str:
        return ([], [])
    
    items = [item.strip() for item in arg_str.split(",") if item.strip()]
    int_items = []
    str_items = []
    for item in items:
        try:
            int_items.append(int(item))
        except ValueError:
            str_items.append(item)
    str_items = sorted(str_items, key=lambda s: (-len(s), s.lower()))
    int_items = sorted(int_items)

    return (int_items, str_items)

def get_filters(args) -> dict[str, dict[str, tuple[list, list]]]:
    """
    Build a filters dictionary for both audio and subtitles.
    Each filter is a dict with keys "keep" and "remove", each holding a tuple: (list_of_ints, list_of_strings).
    A generic -r or -k is applied to both audio and subtitles.
    """
    filters = {
        "audio": {"keep": ([], []), "remove": ([], [])},
        "subtitles": {"keep": ([], []), "remove": ([], [])},
    }
    if args.keep:
        filters["audio"]["keep"] = parse_list(args.keep)
        filters["subtitles"]["keep"] = parse_list(args.keep)
    if args.remove:
        filters["audio"]["remove"] = parse_list(args.remove)
        filters["subtitles"]["remove"] = parse_list(args.remove)
    if args.keep_audio:
        filters["audio"]["keep"] = parse_list(args.keep_audio)
    if args.keep_subtitles:
        filters["subtitles"]["keep"] = parse_list(args.keep_subtitles)
    if args.remove_audio:
        filters["audio"]["remove"] = parse_list(args.remove_audio)
    if args.remove_subtitles:
        filters["subtitles"]["remove"] = parse_list(args.remove_subtitles)
    # If an element appears in both keep and remove lists for a given type, remove it from the remove list and warn.
    for typ in ["audio", "subtitles"]:
        keep_int, keep_str = filters[typ]["keep"]
        remove_int, remove_str = filters[typ]["remove"]
        new_remove_str = []
        for item in remove_str:
            if any(item.lower() == k.lower() for k in keep_str):
                sys.stderr.write(f"Warning: '{item}' appears in both keep and remove for {typ}; ignoring it in remove.\n")
            else:
                new_remove_str.append(item)
        filters[typ]["remove"] = (remove_int, new_remove_str)

    return filters

# --- File discovery and probing ---

def get_media_files(paths) -> list[str]:
    """
    Given a list of file or directory paths, return a list of absolute paths to media files.
    Media files are determined by their file extension.
    """
    media_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.flv', '.wmv', '.mpeg', '.mpg', '.m4v', '.webm', '.ts', '.ogm', 'ogv'}
    files = []
    for path in paths:
        if os.path.isfile(path):
            ext = os.path.splitext(path)[1].lower()
            if ext in media_extensions:
                files.append(os.path.abspath(path))
        elif os.path.isdir(path):
            for root, dirs, filenames in os.walk(path):
                for fname in filenames:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in media_extensions:
                        files.append(os.path.abspath(os.path.join(root, fname)))

    return files

def probe_file(file_path) -> dict[str, str|int|list]:
    """
    Uses ffprobe to get stream and format info for a given file.
    Returns a dict with:
      - file_path
      - size (in bytes)
      - video_tracks: list (each with an ffmpeg index)
      - audio_tracks: list (each with keys: ffmpeg_index, track_no, language, raw_language)
      - subtitle_tracks: similar to audio_tracks
    """
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", file_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        info = json.loads(result.stdout)
    except Exception as e:
        sys.stderr.write(f"Error probing file {file_path}: {e}\n")

        return None

    file_info = {"file_path": file_path}
    try:
        file_info["size"] = int(os.path.getsize(file_path))
    except Exception:
        file_info["size"] = 0

    file_info["video_tracks"] = []
    file_info["audio_tracks"] = []
    file_info["subtitle_tracks"] = []

    audio_count = 0
    subtitle_count = 0
    video_count = 0
    for stream in info.get("streams", []):
        ctype = stream.get("codec_type")
        tags = stream.get("tags", {})
        lang = normalize_language(tags.get("language", "und"))
        if ctype == "audio":
            file_info["audio_tracks"].append({
                "ffmpeg_index": audio_count,   # zero-based index within audio streams
                "track_no": audio_count + 1,   # 1-based track number
                "language": lang,
                "raw_language": tags.get("language", "und")
            })
            audio_count += 1
        elif ctype == "subtitle":
            file_info["subtitle_tracks"].append({
                "ffmpeg_index": subtitle_count,
                "track_no": subtitle_count + 1,
                "language": lang,
                "raw_language": tags.get("language", "und")
            })
            subtitle_count += 1
        elif ctype == "video":
            file_info["video_tracks"].append({
                "ffmpeg_index": video_count,
            })
            video_count += 1

    return file_info

# --- Filtering streams ---

def filter_tracks(tracks, keep_filter, remove_filter) -> tuple[list, list]:
    """
    Given a list of track dicts (each with 'track_no' and 'language'),
    and a keep filter (tuple of ints, strings) and remove filter,
    decide which tracks to keep.
    Returns (kept_tracks, removed_tracks).
    """
    kept = []
    removed = []
    keep_int, keep_str = keep_filter
    remove_int, remove_str = remove_filter
    # Normalize the language strings from filters.
    norm_keep = [normalize_language(s) for s in keep_str]
    norm_remove = [normalize_language(s) for s in remove_str]
    for track in tracks:
        lang = track["language"]
        tno = track["track_no"]
        decision = None
        if (keep_int, keep_str) != ([], []):
            # Only keep tracks that match one of the keep criteria.
            if tno in keep_int or lang in norm_keep:
                decision = True
            else:
                decision = False
        elif (remove_int, remove_str) != ([], []):
            # Remove tracks that match a remove criterion.
            if tno in remove_int or lang in norm_remove:
                decision = False
            else:
                decision = True
        else:
            decision = True  # No filtering → keep everything.
        if decision:
            kept.append(track)
        else:
            removed.append(track)

    return kept, removed

def apply_filters(file_info, filters):
    """Apply the audio and subtitle filters to a file's info."""
    audio_kept, audio_removed = filter_tracks(file_info["audio_tracks"],
                                                filters["audio"]["keep"],
                                                filters["audio"]["remove"])
    sub_kept, sub_removed = filter_tracks(file_info["subtitle_tracks"],
                                            filters["subtitles"]["keep"],
                                            filters["subtitles"]["remove"])
    file_info["audio_kept"] = audio_kept
    file_info["audio_removed"] = audio_removed
    file_info["subtitle_kept"] = sub_kept
    file_info["subtitle_removed"] = sub_removed

    return file_info

# --- Building the ffmpeg command ---

def build_ffmpeg_command(file_info) -> tuple[list[str], str]:
    """
    Constructs an ffmpeg command that copies the file's video stream(s) plus
    only the desired audio and subtitle streams. The output filename is the same as the
    input, but with ".cleaned" inserted before the extension.

    TODO: add argument to specify output directory
    TODO: add argument to overwrite existing files
    """
    input_file = file_info["file_path"]
    dir_name, base_name = os.path.split(input_file)
    name, ext = os.path.splitext(base_name)
    output_file = os.path.join(dir_name, f"{name}.cleaned{ext}")
    cmd = ["ffmpeg", "-i", input_file, "-c", "copy"]
    # Always map all video streams.
    cmd.extend(["-map", "0:v"])
    for a in file_info.get("audio_kept", []):
        cmd.extend(["-map", f"0:a:{a['ffmpeg_index']}"])
    for s in file_info.get("subtitle_kept", []):
        cmd.extend(["-map", f"0:s:{s['ffmpeg_index']}"])
    cmd.append(output_file)

    return cmd, output_file

# --- Informing user which streams will be removed ---

def report_removals(file_info) -> None:
    """
    Reports which audio/subtitle languages are being removed.
    """
    a_removed = {track["language"] for track in file_info.get("audio_removed", [])}
    s_removed = {track["language"] for track in file_info.get("subtitle_removed", [])}
    msgs = []
    if a_removed:
        msgs.append("Removing audio: " + ", ".join(sorted(a_removed)))
    if s_removed:
        msgs.append("Removing subtitles: " + ", ".join(sorted(s_removed)))
    if msgs:
        sys.stderr.write("; ".join(msgs) + "\n")

# --- Running ffmpeg with progress monitoring ---

def run_ffmpeg_with_progress(cmd, output_file, expected_size) -> float:
    """
    Runs the given ffmpeg command as a subprocess.
    While running, every second the script checks the size of the output file to estimate progress.
    Returns the total elapsed time.
    """
    expected_size_mib = expected_size / (1024 * 1024)
    start_time = time.time()
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    while process.poll() is None:
        if os.path.exists(output_file):
            current_size = os.path.getsize(output_file)
        else:
            current_size = 0
        current_size_mib =  0 if current_size == 0 else current_size / (1024 * 1024)
        elapsed = time.time() - start_time
        if elapsed > 0 and current_size > 0:
            rate = current_size / elapsed  # bytes per second
            remaining = max(expected_size - current_size, 0)
            est_time = remaining / rate if rate > 0 else float('inf')
            mib_rate = rate / (1024 * 1024)
            progress_percent = (current_size / expected_size) * 100
            sys.stderr.write(f"Progress: {progress_percent:.0f}% ({current_size_mib:.0f}/{expected_size_mib:.0f} MiB), Estimated time: {int(est_time)}s, Speed: {mib_rate:.2f} MiB/s\033[K\r")
            sys.stderr.flush()
        time.sleep(.03)
    # Capture any remaining output.
    process.communicate()
    total_time = time.time() - start_time
    sys.stderr.write(f"Progress: 100% ({current_size_mib:.0f} MiB), Speed: {mib_rate:.2f} MiB/s\r")
    sys.stderr.write("\n")

    return total_time

# --- Main ---

def main() -> int:
    args = parse_args()
    if (not args.paths) or ("-h" in sys.argv or "--help" in sys.argv):
        sys.stdout.write(f"Usage: {__file__} [options] file_or_directory ...\n")
        sys.stdout.write("Examples:\n")
        sys.stdout.write(f"  {__file__} -ra ru -ks en --dry-run /folder/input.mkv\n")
        sys.stdout.write(f"  {__file__} -ka en -rs ru,de /folder/input.mkv\n")
        sys.stdout.write(f"  {__file__} -k en /folder/input.mkv\n")
        sys.stdout.write(f"  {__file__} -r ru,de /folder/input.mkv\n")

        return 0

    args = process_args(args)
    media_files = get_media_files(args.paths)
    if not media_files:
        sys.stderr.write("No media files found.\n")

        return 1

    filters = get_filters(args)

    for file_path in media_files:
        sys.stderr.write(f"Processing file: {file_path}\n")
        file_info = probe_file(file_path)
        if not file_info:
            continue
        file_info = apply_filters(file_info, filters)
        ffmpeg_cmd, output_file = build_ffmpeg_command(file_info)
        report_removals(file_info)

        # Print the command if in dry-run mode.
        if args.dry_run:
            sys.stdout.write("Dry-run: " + " ".join(ffmpeg_cmd) + "\n")
            continue

        # Run ffmpeg and monitor progress.
        total_time = run_ffmpeg_with_progress(ffmpeg_cmd, output_file, file_info["size"])

        # Report remaining streams.
        remaining_audio = ", ".join([a["language"] for a in file_info.get("audio_kept", [])])
        remaining_subs = ", ".join([s["language"] for s in file_info.get("subtitle_kept", [])])
        sys.stderr.write("Remaining streams: ")
        if remaining_audio:
            sys.stderr.write("Audio: " + remaining_audio)
        if remaining_audio and remaining_subs:
            sys.stderr.write("; ")
        if remaining_subs:
            sys.stderr.write("Subtitles: " + remaining_subs)
        sys.stderr.write("\n")
        # Report processing stats.
        mib_processed = file_info["size"] / (1024 * 1024)
        speed = mib_processed / total_time if total_time > 0 else 0
        sys.stderr.write("File written to: ")
        sys.stderr.flush()
        sys.stdout.write(f"{output_file}\n")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
