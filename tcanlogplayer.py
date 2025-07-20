#!/usr/bin/env python3
import argparse
import os
import sched
import socket
import struct
import sys
import time
from collections import defaultdict

'''
Create the virtual can port:
   sudo ip link add dev vcan0 type vcan
   sudo ip link set up vcan0
'''


def setup_parser():
    parser = argparse.ArgumentParser(
        description="Replay a CAN logfile in ASC format to the vcan0 interface")
    parser.add_argument('file', type=str, help='CAN logfile in ASC format')
    parser.add_argument('-filter', type=str, default='filterNone.txt',
                        help='filter for message id, default=filterNone.txt')
    parser.add_argument('--convert-only', action='store_true',
                        help='only convert the file without sending CAN frames')
    return parser.parse_args()


def valid_line(line):
    invalid_prefixes = ('*', 'Begin Triggerblock', 'base dec timestamps absolute',
                        'End Triggerblock', 'log trigger event Info:')
    return (not any(line.startswith(p) for p in invalid_prefixes) and
            "Errorframe" not in line and
            " Tx " not in line)


def to_can_frame(line):
    parts = line.split()
    ts = float(parts[0])
    ch = int(parts[1])
    can_id = int(parts[2]) if ch != 0 else 99999
    node_id = int(parts[5])
    data = bytearray(int(i) for i in parts[6:14])
    return ts, can_id, data, node_id


def send_frame(sock, can_id, data):
    ## https://docs.python.org/3/library/struct.html
    ## http://www.bencz.com/hacks/2016/07/10/python-and-socketcan/
    fmt = "<IB3x8s"
    can_pkt = struct.pack(fmt, can_id, len(data), data)
    sock.send(can_pkt)


def setup_socket(interface):
    try:
        sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
        sock.bind((interface,))
        return sock
    except OSError as e:
        sys.stderr.write(f"Could not bind to interface '{interface}': {e}\n")
        sys.exit(1)


def load_filter(filter_path):
    filter_can_ids = set()
    if os.path.isfile(filter_path):
        print(f"reading filter file {filter_path}")
        with open(filter_path) as fp:
            filter_can_ids.update(int(line.strip()) for line in fp if line.strip())
    return filter_can_ids

## stolen from: https://gist.github.com/vladignatyev/06860ec2040cb497f0f3
def progress(count, total, last_time):
    bar_len = 60
    filled_len = int(round(bar_len * count / float(total)))
    percents = round(100.0 * count / float(total), 1)
    bar = '=' * filled_len + '-' * (bar_len - filled_len)
    print(f'\r[{bar}] {percents}% ...{last_time}', end='', flush=True)


def main():
    args = setup_parser()
    interface = "vcan0"

    # Generate output filename by adding .can to input filename
    input_path = os.path.abspath(args.file)
    output_path = f"{input_path}.can"
    output_dir = os.path.dirname(output_path)

    # Create output directory if it doesn't exist
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    sock = None
    if not args.convert_only:
        sock = setup_socket(interface)
    filter_can_ids = load_filter(args.filter)

    scheduler = sched.scheduler(time.time, time.sleep)
    start_time = time.time()

    can_ids = defaultdict(int)
    node_ids = defaultdict(int)
    queue_max = 0

    with open(output_path, "w") as logfile, open(args.file) as fp:
        # Read and filter lines first
        valid_lines = []
        for line in fp:
            if valid_line(line):
                valid_lines.append(line)
        num_lines = len(valid_lines)

        print(
            f"start {'converting' if args.convert_only else 'sending to device'} {interface if not args.convert_only else ''} ...")
        print(f"writing output to {output_path}")
        last_time = 0

        for cnt, line in enumerate(valid_lines, 1):
            ts, can_id, data, node_id = to_can_frame(line)

            if cnt == 1:
                last_time = ts

            if not filter_can_ids or can_id in filter_can_ids:
                can_ids[can_id] += 1
                node_ids[node_id] += 1

                # write directly a file for canplayer
                # "1563281268.048045) vcan0 78A#0A0C343602490000"
                logfile.write(f"({start_time + ts:f}) {interface} {can_id:X}#{data.hex().upper()}\n")
                if not args.convert_only:
                    send_frame(sock, can_id, data)
                    scheduler.enterabs(start_time + ts, 1, send_frame, (sock, can_id, data))
                    queue_max = max(queue_max, len(scheduler.queue))
                    scheduler.run()
                last_time = ts

            if cnt % 100 == 0 or cnt == num_lines:  # Update progress every 100 lines or at end
                progress(cnt, num_lines, last_time)

    print(f'\nqueue_max: {queue_max}')
    print("canId statistics:")
    print("Sorted by ID:", sorted(can_ids.items()))
    print("Sorted by count:", sorted(can_ids.items(), key=lambda x: x[1], reverse=True))
    print("nodeId statistics:")
    print("Sorted by ID:", sorted(node_ids.items()))
    print("Sorted by count:", sorted(node_ids.items(), key=lambda x: x[1], reverse=True))


if __name__ == "__main__":
    main()
