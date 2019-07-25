#!/usr/bin/env python3
import os
import socket, sys
import struct
import sched, time
from datetime import datetime

'''
   Create the virtual can port:
      sudo ip link add dev vcan0 type vcan
      sudo ip link set up vcan0
'''
interface = "vcan0"
filepath = 'PermanentLogging.ASC'
## filepath = 'shortlog.txt' ## for testing

filterpath = 'filter.txt'


def validLine(line):
    try:
        return "Errorframe" not in line \
               and "Begin Triggerblock" not in line \
               and "base dec timestamps absolute" not in line \
               and "End Triggerblock" not in line \
               and " Tx " not in line \
               and "log trigger event Info:" not in line
    except OSError:
        return False

## 8672.21581 1  1930       Rx D 8  10  12  22 182 255 191 255 224
def toCanFrame(line):
    parts = (" ".join(line.split()).split())
    ts = float(parts[0])
    canId = int(parts[2])
    nodeId = int(parts[5])
    data = bytearray([int(i) for i in parts[6:14]])
    return ts, canId, data, nodeId

def send(canId, data):
    ## https://docs.python.org/3/library/struct.html
    ## http://www.bencz.com/hacks/2016/07/10/python-and-socketcan/
    fmt = "<IB3x8s"
    can_pkt = struct.pack(fmt, canId, len(data), data)
    sock.send(can_pkt)

def statistics(ids, id):
    if id not in ids:
        ids[id] = 1
    ids[id] = ids[id] + 1

sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
try:
    sock.bind((interface,))
except OSError:
    sys.stderr.write("Could not bind to interface '%s'\n" % interface)
    quit()

filterCanIds = set()

if os.path.isfile(filterpath):
    print("reading filter file {}".format(filterpath))
    with open(filterpath) as fp:
        for line in fp:
            filterCanIds.add(int(line))

#sched = sched.scheduler(time.time, time.sleep)
startTime = time.time()

skip_rows = 500000

canIds = {}
nodeIds = {}
lastTime = 0 
print("start sending to device {} ...".format(interface))
with open(filepath) as fp:
    for cnt, line in enumerate(fp):
        if cnt < skip_rows:
            continue
        if validLine(line):
            ts, canId, data, nodeId = toCanFrame(line)
            if cnt == skip_rows:
                lastTime = ts
            assert ts > 0.0, "Wrong time increment";
            if len(filterCanIds) == 0 or canId in filterCanIds:
                statistics(canIds, canId)
                statistics(nodeIds, nodeId)
                
                dt = ts - lastTime
                time.sleep(dt)
                time_now = datetime.now().strftime("%H:%M:%S.%f")
                print("send at {}: canId={:04} data={}".format(time_now, canId, data.hex()))
                send(canId, data)

                #sched.enterabs(startTime + ts, 1, lambda x, y: send(x, y), (canId, data,))
                #sched.run()
                lastTime = ts


print("canId statistics")
print(sorted(canIds.items(), key=lambda kv: kv[0], reverse=True))
print(sorted(canIds.items(), key=lambda kv: kv[1], reverse=True))
print("nodeId statistics")
print(sorted(nodeIds.items(), key=lambda kv: kv[0], reverse=True))
print(sorted(nodeIds.items(), key=lambda kv: kv[1], reverse=True))
