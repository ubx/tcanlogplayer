import socket, sys
import struct
import sched, time
import threading
from datetime import datetime
from pytimeparse.timeparse import timeparse

'''
   Create the virtual can port:
      sudo ip link add dev vcan0 type vcan
      sudo ip link set up vcan0
'''
interface = "vcan0"
filepath = 'PermanentLogging.ASC'
##filepath = 'shortlog.txt' ## for testing


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
    ts = timeparse("{}s".format(parts[0]))
    canId = int(parts[2])
    data = bytearray([int(i) for i in parts[6:14]])
    return ts, canId, data


def send(canId, data):
    ## https://docs.python.org/3/library/struct.html
    ## http://www.bencz.com/hacks/2016/07/10/python-and-socketcan/
    fmt = "<IB3x8s"
    can_pkt = struct.pack(fmt, canId, len(data), data)
    sock.send(can_pkt)


sock = socket.socket(socket.PF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
try:
    sock.bind((interface,))
except OSError:
    sys.stderr.write("Could not bind to interface '%s'\n" % interface)
    quit()

sched = sched.scheduler(time.time, time.sleep)
startTime = time.time()
with open(filepath) as fp:
    lastTime = startTime;
    for cnt, line in enumerate(fp):
        if validLine(line):
            ts, canId, data = toCanFrame(line)
            time = datetime.now().strftime("%H:%M:%S.%f")
            print("send at {}: canId={:04} data={}".format(time, canId, data.hex()))
            fun = lambda x, y: send(x, y)
            newTime = startTime + ts;
            assert newTime > lastTime, "Wrong time increment";
            lastTime = newTime;
            sched.enterabs(newTime, 1, fun, (canId, data,))

            # Start a thread to run the events
            threading.Thread(target=sched.run).start()