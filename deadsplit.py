#!/usr/bin/env python
import signal
import sys
import time
import threading
from art import text2art
from datetime import datetime, timedelta
from pynput.keyboard import Listener, KeyCode, Key
from rich.text import Text
from rich.console import Console


def calculate_tabs(string, tab_size=8, column_size=2):
    tabs_needed = (column_size - len(string) // tab_size) + 1
    return "\t" * tabs_needed


def parse_splits(data_str):
    splits = []
    lines = data_str.strip().split("\n")
    for line in lines:
        name, pb, goal, info = line.split("\t")
        pb = datetime.strptime(pb.strip(), "%H:%M:%S.%f")
        pb = timedelta(
            hours=pb.hour,
            minutes=pb.minute,
            seconds=pb.second,
            microseconds=pb.microsecond,
        )
        splits.append(
            {
                "name": name,
                "pb": pb,
                "goal": goal,
                "info": info,
                "start_time": None,
                "end_time": None,
                "duration": timedelta(microseconds=0),
                "delta": None,
            }
        )
    return splits


def save_splits(splits):
    result = []
    for split in splits:
        seconds, ms = divmod(split["pb"] / timedelta(microseconds=1), 1000000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)

        main_time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
        ms_str = f".{int(ms):06}"
        pb_time = f"{main_time_str}{ms_str}"
        result.append(
            f"{split['name']}\t{pb_time}\t{split['goal']}\t{split['info']}"
        )
    return "\n".join(result)


def draw_splits(splits, elapsed_time, active_split, running_event):
    result = []
    for i, split in enumerate(splits):
        current_time = split["duration"]

        if split["delta"]:
            delta = split["delta"]
        else:
            delta = current_time - split["pb"]

        if not running_event.is_set() or i != active_split:
            color = "grey"
        else:
            color = "white"

        if active_split >= 0 and i <= active_split and delta < timedelta(seconds=-5):
            color = "yellow"
        elif active_split >= 0 and i <= active_split and delta < timedelta(seconds=0):
            color = "green"
        elif active_split >= 0 and i <= active_split and delta > timedelta(seconds=10):
            color = "red"

        color = " on black" if i == active_split and running_event.is_set() else color
        split_line = f"{split['name']}" + calculate_tabs(split["name"], column_size=4)
        split_line += f"Δ{delta.total_seconds():.2f}s" + calculate_tabs(
            f"Δ{delta.total_seconds():.2f}s"
        )
        split_line += f"{current_time.total_seconds():.2f}s\t(PB: {split['pb'].total_seconds():.2f})"

        result.append(Text(split_line, style=color))
    return result


def draw_time(millis):
    seconds, ms = divmod(millis, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)

    main_time_str = f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"
    ms_str = f".{int(ms):03}"

    main_art = text2art(main_time_str, font="tarty3")
    ms_art = text2art(ms_str, font="tarty2")

    main_lines = main_art.splitlines()
    ms_lines = ms_art.splitlines()

    for i in range(len(ms_lines)):
        main_lines[i] = "\t\t\t\t" + main_lines[i]
        if i == 0 or i == len(ms_lines) - 1:
            continue
        main_lines[i + 1] += " " + ms_lines[i]

    return "\n".join(main_lines)


def clear_rows(rows):
    for _ in range(rows):
        print("\033[F\033[K", end="")  # Clear the timer lines


def timer(splits, console, start_event, running_event, reset_event, quitting_event):
    start_time = datetime.now()
    elapsed_time = timedelta(microseconds=0)
    active_split = -1

    draw_height = len(splits) + 3

    print("\n" * draw_height)  # Make space for the timer

    while not quitting_event.is_set():
        if reset_event.is_set():
            start_time = datetime.now()
            elapsed_time = timedelta(microseconds=0)
            active_split = -1
            for split in splits:
                split["start_time"] = None
                split["end_time"] = None
                split["duration"] = timedelta(microseconds=0)
            running_event.clear()
            reset_event.clear()

        if running_event.is_set():
            current_time = datetime.now()
            if active_split >= 0:
                splits[active_split]["end_time"] = current_time
                splits[active_split]["duration"] = (
                    splits[active_split]["end_time"]
                    - splits[active_split]["start_time"]
                )
                splits[active_split]["delta"] = (
                    splits[active_split]["duration"] - splits[active_split]["pb"]
                )
            elapsed_time = current_time - start_time

        if start_event.is_set():
            if (
                active_split >= 0
                and active_split < len(splits)
                and (
                    splits[active_split]["duration"] < splits[active_split]["pb"]
                    or splits[active_split]["pb"] == timedelta(microseconds=0)
                )
            ):
                splits[active_split]["pb"] = splits[active_split]["duration"]

            if active_split + 1 < len(splits):
                active_split += 1
                splits[active_split]["start_time"] = datetime.now()
                running_event.set()

            elif active_split + 1 == len(splits):
                active_split += 1
                running_event.clear()

            elif active_split + 1 >= len(splits):
                reset_event.set()

            start_event.clear()

        splits_str = draw_splits(splits, elapsed_time, active_split, running_event)
        ascii_timer = draw_time(elapsed_time / timedelta(milliseconds=1))

        clear_rows(draw_height)

        console.print(*splits_str, sep="\n")
        console.print(ascii_timer, end="")  # Print the timer
        time.sleep(0.06)  # Adjust refresh rate


def write_splits(splits, file_path):
    with open(file_path, "w") as f:
        f.write(save_splits(splits))


def on_press(key, splits, start_event, running_event, reset_event, quitting_event):
    try:
        if key == Key.f9:  # Change this as needed for numpad '1'
            start_event.set()
        elif key == Key.f10:
            reset_event.set()
        elif key == Key.f12:
            print("\nQuitting...")
            quitting_event.set()
            file_path = datetime.now().strftime("%Y%m%d%H%M%S") + "_splits.txt"
            write_splits(splits, file_path)
    except AttributeError:
        pass


def on_release(key, start_event, running_event, reset_event, quitting_event):
    pass  # We don't need to handle key releases in this case


if __name__ == "__main__":
    start_event = threading.Event()
    running_event = threading.Event()
    reset_event = threading.Event()
    quitting_event = threading.Event()

    if not sys.stdin.isatty():
        splits_in = sys.stdin.read()
    else:
        splits_in = """Timer\t00:01:30.000000\t00:01:20.000000\tInfo1"""
    splits = parse_splits(splits_in)

    def signal_handler(sig, frame):
        print("\nQuitting...")
        quitting_event.set()
        file_path = datetime.now().strftime("%Y%m%d%H%M%S") + "_splits.txt"
        write_splits(splits, file_path)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    console = Console()

    timer_thread = threading.Thread(
        target=timer,
        args=(splits, console, start_event, running_event, reset_event, quitting_event),
    )

    with Listener(
        on_press=lambda key: on_press(
            key, splits, start_event, running_event, reset_event, quitting_event
        ),
        on_release=lambda key: on_release(
            key, start_event, running_event, reset_event, quitting_event
        ),
    ) as listener:
        timer_thread.start()

        timer_thread.join()
        listener.stop()
