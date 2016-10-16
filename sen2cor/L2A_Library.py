#!/usr/bin/env python

from numpy import *
from scipy.signal import medfilt
from scipy.ndimage import map_coordinates
from scipy import interpolate as sp
from scipy.ndimage.filters import uniform_filter

import sys, os


def stdoutWrite(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def stderrWrite(s):
    sys.stderr.write(s)
    sys.stderr.flush()

def statistics(arr, comment = ''):
    if len(arr) == 0:
        return False
    s = 'object:' + str(comment) + '\n'
    s += '--------------------' + '\n'
    s += 'shape: ' + str(shape(arr)) + '\n'
    s += 'sum  : ' + str(arr.sum()) + '\n'
    s += 'mean : ' + str(arr.mean()) + '\n'
    s += 'std  : ' + str(arr.std())  + '\n'
    s += 'min  : ' + str(arr.min())  + '\n'
    s += 'max  : ' + str(arr.max())  + '\n'
    s += '-------------------' + '\n'
    return s


def showImage(arr):
    from PIL import Image
    if(arr.ndim) != 2:
        sys.stderr.write('Must be a two dimensional array.\n')
        return False

    arrmin = arr.mean() - 3*arr.std()
    arrmax = arr.mean() + 3*arr.std()
    arrlen = arrmax-arrmin
    arr = clip(arr, arrmin, arrmax)
    scale = 255.0
    scaledArr = (arr-arrmin).astype(float32) / float32(arrlen) * scale
    arr = (scaledArr.astype(uint8))
    img = Image.fromarray(arr)
    img.show()
    return True


def rectBivariateSpline(xIn, yIn, zIn):
    x = arange(zIn.shape[0], dtype=float32)
    y = arange(zIn.shape[1], dtype=float32)

    f = sp.RectBivariateSpline(x,y,zIn)
    return f(xIn,yIn)
