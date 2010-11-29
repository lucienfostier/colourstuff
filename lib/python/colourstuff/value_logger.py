import os
import time
import datetime
import pyspotread

spotread = pyspotread.Spotread(
    cmd = os.path.expanduser("~/Desktop/Argyll_V1.1.1/bin/spotread"),
    port = 1,
    lcd = True)

def doreading(log):
    XYZ = spotread.sample()
    log.write("%s, %.04f, %.04f, %.04f, %.00f\n" % (str(datetime.datetime.now()), XYZ.X, XYZ.Y, XYZ.Z, XYZ.cct()))
    log.flush()
    print str(XYZ)
    print "*"*70

log = open("logged_xyz.txt", "a")

while 1:
    try:
        doreading(log)
        time.sleep(5)
    except Exception, e:
        print "Exiting:"
        print e
        break
