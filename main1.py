#!/usr/bin/env python3
import sys
import os
import json

def get_file(argv):
    if "-file" in argv:
        idx = argv.index("-file")
        if idx + 1 < len(argv):
            return argv[idx + 1]
    return None

def extract_fields(line):
    # Try parsing as JSON first
    try:
        json_dict = json.loads(line)
        if all(k in json_dict for k in ["timestamp", "level", "message"]):
            return {
                "timestamp": json_dict["timestamp"], 
                "level": json_dict["level"].strip(), 
                "message": json_dict["message"].strip()
            }
    except ValueError:
        pass # Fallback to plain text parsing

    # Plain text parsing: "YYYY-MM-DD HH:MM:SS LEVEL Message content"
    try:
        # Split by whitespace up to 3 times to isolate Date, Time, Level, and Message
        parts = line.split(maxsplit=3)
        if len(parts) < 4:
            return None
        
        timestamp = f"{parts[0]} {parts[1]}"
        level = parts[2]
        message = parts[3]
        
        return {"timestamp": timestamp, "level": level, "message": message}
    except Exception:
        return None

def get_stats(entries):
    # Feature-3: Initialize counters
    stats = {"ERROR": 0, "WARNING": 0, "INFO": 0}
    groups = {}
    failure_timestamps = []

    for entry in entries:
        lvl = entry["level"].upper()
        msg = entry["message"]

        # Track log level counts
        if lvl in stats:
            stats[lvl] += 1
        else:
            stats[lvl] = 1 # Catch any non-standard levels if they exist

        # Track failure timestamps for the final output printout
        if lvl == "ERROR":
            # Extract just the HH:MM:SS component if it's a full timestamp
            time_part = entry["timestamp"].split()[-1]
            failure_timestamps.append(time_part)

        # Feature-4: Store error/message frequencies (errors only)
        if lvl == "ERROR":
            groups[msg] = groups.get(msg, 0) + 1

    return { "stats": stats, "groups": groups, "failures": failure_timestamps }

if __name__ == "__main__":
    file_name = get_file(sys.argv)
    
    if not file_name or not os.path.isfile(file_name):
        print(f"Error: Valid file path must be provided via '-file'.")
        sys.exit(1)

    entries = []
    with open(file_name, "r") as file:
        for line in file:
            line = line.strip()
            if not line:
                continue
            entry = extract_fields(line)
            if entry:
                entries.append(entry)

    # Process stats
    analysis = get_stats(entries)
    counts = analysis["stats"]
    msg_groups = analysis["groups"]
    failures = analysis["failures"]

    # Feature-4: Safely find the most frequent message
    most_frequent_err = "None"
    if msg_groups:
        most_frequent_err = max(msg_groups, key=msg_groups.get)

    # Final Output Formatting
    print(f"Total logs:           {len(entries)}")
    print(f"Errors:               {counts.get('ERROR', 0)}")
    print(f"Warnings:             {counts.get('WARNING', 0)}")
    print(f"Info:                 {counts.get('INFO', 0)}")
    print(f"Most frequent error:  \"{most_frequent_err}\"")
    print(f"Failure timestamps:   {', '.join(failures[:5])}{'...' if len(failures) > 5 else ''}" if failures else "Failure timestamps:   None")
