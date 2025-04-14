#!/usr/bin/env python3

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

def detect_ffmpeg() -> bool:
    """Check if ffmpeg is available."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        return False

    return True

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
    parser.add_argument("-o", "--output-dir", nargs=1, help="Output directory for cleaned files")
    parser.add_argument("-O", "--output-dir-alias", dest="output_dir_alias", nargs=1, help=argparse.SUPPRESS)
    parser.add_argument("--keep-subtitle", dest="keep_subtitles_alias", help=argparse.SUPPRESS)
    parser.add_argument("--remove-subtitle", dest="remove_subtitles_alias", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true", help="Print the ffmpeg command without executing it")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite input files")
    parser.add_argument("--no-clean-metadata", action="store_true", 
                        help="Do not remove 'title' and 'comment' metadata (default is to remove them)")
    args = parser.parse_args()

    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
  
    if args.output_dir and args.output_dir[0] == '.':
        args.output_dir[0] = os.getcwd()

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

def apply_filters(file_info, filters) -> dict[str, str|int|list]:
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

def build_ffmpeg_command(file_info, output_dir, dry_run=False, clean_metadata=True) -> tuple[list[str], str]:
    """
    Constructs an ffmpeg command that copies the file's video stream(s) plus
    only the desired audio and subtitle streams. The output filename is the same as the
    input, but with ".cleaned" inserted before the extension.
    """
    input_file = file_info["file_path"]
    dir_name, base_name = os.path.split(input_file)
    name, ext = os.path.splitext(base_name)

    if output_dir:
        if not os.path.exists(output_dir[0]):
            try:
                os.makedirs(output_dir[0])
            except Exception as e:
                sys.stderr.write(f"Error creating output directory: {e}\n")
                if not dry_run:
                    return 2

        dir_name = output_dir[0]
    output_file = os.path.join(dir_name, f"{name}.cleaned{ext}")
    cmd = ["ffmpeg", "-y", "-i", input_file, "-c", "copy"]

    if clean_metadata:
        cmd.extend(["-metadata", "title=", "-metadata", "comment="])
        cmd.extend(["-metadata:s:v:0", "title=", "-metadata:s:v:0", "comment="])
        
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
    sys.stderr.write("Removing ")
    msgs = []
    if a_removed:
        msgs.append("audio: " + ", ".join(sorted(a_removed)))
    if s_removed:
        msgs.append("subtitles: " + ", ".join(sorted(s_removed)))
    if msgs:
        sys.stderr.write("; ".join(msgs) + "\n")

# --- Running ffmpeg with progress monitoring ---

def run_ffmpeg_with_progress(cmd, output_file, expected_size) -> tuple[float, bool]:
    """
    Runs the given ffmpeg command as a subprocess.
    While running, every second the script checks the size of the output file to estimate progress.
    If ffmpeg fails, outputs the ffmpeg command and error output from ffmpeg, then removes the output file.
    Returns the total elapsed time.
    """
    expected_size_mib = expected_size / (1024 * 1024)
    start_time = time.time()
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    mib_rate = 0.0
    while process.poll() is None:
        if os.path.exists(output_file):
            current_size = os.path.getsize(output_file)
        else:
            current_size = 0
        current_size_mib = 0 if current_size == 0 else current_size / (1024 * 1024)
        elapsed = time.time() - start_time
        if elapsed > 0 and current_size > 0:
            rate = current_size / elapsed  # bytes per second
            remaining = max(expected_size - current_size, 0)
            est_time = remaining / rate if rate > 0 else float('inf')
            mib_rate = rate / (1024 * 1024)
            progress_percent = (current_size / expected_size) * 100
            sys.stderr.write(f"Progress: {progress_percent:.0f}% ({current_size_mib:.0f}/{expected_size_mib:.0f} MiB), "
                             f"Estimated time: {int(est_time)}s, Speed: {mib_rate:.2f} MiB/s\033[K\r")
            sys.stderr.flush()
        time.sleep(0.03)
    stdout_data, stderr_data = process.communicate()
    total_time = time.time() - start_time
    retcode = process.returncode
    if retcode != 0:
        sys.stderr.write(f"\nFFmpeg command failed (exit code {retcode}): {' '.join(cmd)}\n")
        if stderr_data:
            sys.stderr.write("FFmpeg error output:\n" + str(stderr_data) + "\n")
        if os.path.exists(output_file):
            os.remove(output_file)
    else:
        sys.stderr.write(f"Progress: 100% ({current_size_mib:.0f} MiB), Speed: {mib_rate:.2f} MiB/s\033[K\r\n")
    return total_time, retcode==0

# --- Main ---

def main() -> int:
    args = parse_args()
    if not detect_ffmpeg():
        sys.stderr.write("Error: ffmpeg not found in PATH.\n")

        return 1
    
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
        ffmpeg_cmd, output_file = build_ffmpeg_command(file_info, args.output_dir, args.dry_run, clean_metadata=not args.no_clean_metadata)

        # Print the command if in dry-run mode.
        if args.dry_run:
            sys.stdout.write("FFMPEG command: " + " ".join(ffmpeg_cmd) + "\n")
            continue

        report_removals(file_info)        

        # Run ffmpeg and monitor progress.
        total_time, success = run_ffmpeg_with_progress(ffmpeg_cmd, output_file, file_info["size"])

        # Overwrite the input file if requested.
        if args.overwrite:
            os.replace(output_file, file_path)
            output_file = file_path

        # Report remaining streams.
        remaining_audio = ", ".join([a["language"] for a in file_info.get("audio_kept", [])])
        remaining_subs = ", ".join([s["language"] for s in file_info.get("subtitle_kept", [])])
        sys.stderr.write("Remaining ")
        if remaining_audio:
            sys.stderr.write("audio: " + remaining_audio)
        if remaining_audio and remaining_subs:
            sys.stderr.write("; ")
        if remaining_subs:
            sys.stderr.write("subtitles: " + remaining_subs)
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
