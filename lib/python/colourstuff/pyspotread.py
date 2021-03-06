"""Tools to get colour readings from a monitor probe.

Primarily an interface to ArgyllCMS's spotread command, using pexpect.

Requires http://www.argyllcms.com (was developed with version 1.3.2)
"""

import os
import re
import math
import subprocess

import pexpect

from colour_temp import correlated_colour_temp


def list_probes(cmd = "spotread"):
    """Parses the spotread command's help string which lists the connected probes
    """
    p = subprocess.Popen(cmd + " -h", shell = True, stdout = subprocess.PIPE, stderr = subprocess.PIPE)
    _, se = p.communicate()
    in_listing = False
    found = []
    for line in se.splitlines():
        if line.strip().startswith("-c listno"):
            in_listing = True
        elif line.strip().startswith("-t"):
            in_listing = False
        elif in_listing:
            found.append(line.strip())

    if len(found) == 1 and found[0] == "** No ports found **":
        return []
    else:
        import re
        dictfound = {}
        for x in found:
            probenum, probename = re.match("(\d+) = '.*? \((.*)\)'", x).groups()
            dictfound[int(probenum)] = probename
        return dictfound


class ColourMatrix(object):
    def __init__(self, *args):
        if len(args) != 9:
            raise ValueError("Should have 9 args, have %s" % len(args))
        self.matrix = args

    def transform(self, r, g, b):
        new_r = r*self.matrix[0] + g*self.matrix[1] + b*self.matrix[2]
        new_g = r*self.matrix[3] + g*self.matrix[4] + b*self.matrix[5]
        new_b = r*self.matrix[6] + g*self.matrix[7] + b*self.matrix[8]
        return (new_r, new_g, new_b)


REFWHITES = {
    # From http://www.brucelindbloom.com/index.html?Eqn_XYZ_to_Lab.html
    "D55": (0.95682, 1.00000, 0.92149),
    "D65": (0.95047, 1.00000, 1.08883),
}


class XYZ(object):
    def __init__(self, X, Y, Z):
        self.X = X
        self.Y = Y
        self.Z = Z

    def __repr__(self):
        return "XYZ(%s, %s, %s)" % tuple(str(a) for a in (self.X, self.Y, self.Z))

    def to_xyY(self):
        """
        http://en.wikipedia.org/wiki/CIE_1931_color_space#The_CIE_xy_chromaticity_diagram_and_the_CIE_xyY_color_space
        """
        X, Y, Z = self.X, self.Y, self.Z
        x = X / (X+Y+Z)
        y = Y / (X+Y+Z)
        return (x, y, Y)

    def cct(self):
        return correlated_colour_temp(self.X, self.Y, self.Z)

    def to_CIELAB(self, refwhite = "D65"):
        """
        http://en.wikipedia.org/wiki/L*a*b*
        """
        #FIXME: Not tested, probably not correct
        def f(t):
            if t > (6/29)**3:
                return t**1/3
            else:
                return 1/3 * (29/6)**2 * t + 4/29

        X, Y, Z = self.X, self.Y, self.Z

        Xn, Yn, Zn = REFWHITES[refwhite]
        Xn, Yn, Zn = [a*100 for a in (Xn, Yn, Zn)]

        L = 116 * f(Y/Yn) - 16
        a = 500 * (f(X/Xn) - (f(Y/Yn)))
        b = 200 * (f(Y/Yn) - f(Z/Zn))

        return (L, a, b)

    def to_srgb(self, space = "sRGB"):
        #FIXME: This method is probably not correct
        X, Y, Z = self.X, self.Y, self.Z

        #Normalise XYZ values to 0-1, based on max XYZ value. Not correct
        maxval = max(X, Y, Z)
        X = X/maxval
        Y = Y/maxval
        Z = Z/maxval

        lin_to_srgb = lambda v: (v * (v<=0.0031308)) + (((1.055 * v**1/2.4) - 0.055) * (v>0.0031308))

        m = ColourMatrix(
            3.2404542, -1.5371385, -0.4985314,
            -0.9692660, 1.8760108, 0.0415560,
            0.0556434, -0.2040259, 1.0572252)

        r, g, b = m.transform(X, Y, Z)

        sr, sg, sb = lin_to_srgb(r), lin_to_srgb(g), lin_to_srgb(b)

        return (sr, sg, sb)

    def __str__(self):
        def format_float(a):
            return ("%.04f" % a).rjust(7)

        X, Y, Z = self.X, self.Y, self.Z
        x, y, _ = self.to_xyY()
        try:
            cct = self.cct()
        except ValueError, e:
            cct = str(e)
        r, g, b = self.to_srgb()

        out_text = ""
        out_text += "X, Y, Z : %s, %s, %s" % tuple(format_float(a) for a in (X, Y, Z))
        out_text += "\n"
        out_text += "x, y, Y : %s, %s, %s" % tuple(format_float(a) for a in (x, y, Y))
        out_text += "\n"
        out_text += "CCT (K) : %s" % cct
        out_text += "\n"
        out_text += "sRGB    : %s, %s, %s" % tuple(format_float(a) for a in (r, g, b))

        return out_text


def deltaE(a, b):
    #FIXME: Overly basic and untested
    L1, a1, b1 = a.to_CIELAB()
    L2, a2, b2 = b.to_CIELAB()
    return math.sqrt((L2-L1)**2 + (a2-a1)**2 + (b2-b1)**2)


class Spotread(object):
    """Wrapper for the ArgyllCMS spotread command, which allows reading of
    values from various monitor probes.
    """

    def __init__(self, cmd = "spotread", port = 1, lcd = False, crt = False):
        if not (lcd or crt) and not (lcd and crt):
            raise ValueError("Either lcd or crt must be True")

        if lcd:
            display_type = "l"
        elif crt:
            display_type = "c"

        self.port = port

        self.cmd = "%s -y %s -c %s" % (cmd, display_type, port)
        self.proc = pexpect.spawn(self.cmd)

    def sample(self):
        """Read a colour sample from the probe
        """
        self.proc.expect(".*any other key to take a reading:")
        self.proc.send(" ")
        self.proc.expect("Result is XYZ: (-?\d+\.\d+) (-?\d+\.\d+) (-?\d+\.\d+),")
        X, Y, Z = [float(x) for x in self.proc.match.groups()]
        return XYZ(X, Y, Z)

    def quit(self):
        """Exit the spotread command nicely
        """
        self.proc.expect(".*any other key to take a reading:")
        self.proc.send("q")
        self.proc.send("q") # confirm quit


if __name__ == '__main__':
    print list_probes()
    sr = Spotread(
        port = 1,
        lcd = True)

    # Grab one sample from the probe, and quit the process
    sample = sr.sample()
    sr.quit()

    print str(sample)
