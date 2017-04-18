
#! /usr/bin/env python
# Camera classes for behavioral monitoring and single photon imaging.
# Creates separate processes for acquisition and saving to disk

import time
import sys
from multiprocessing import Process,Queue,Event,Array,Value
import numpy as np
from datetime import datetime
import time
import sys
from .io import TiffWriter
from .utils import *
import ctypes
# 
# Has last frame on multiprocessing array
# 
class GenericCam(Process):
    def __init__(self, outQ = None,lock = None):
        Process.__init__(self)
        self.name = ''
        self.h = None
        self.w = None
        self.close = Event()
        self.startTrigger = Event()
        self.stopTrigger = Event()
        self.saving = Event()
        self.nframes = Value('i',0)
        self.queue = outQ
    def initVariables(self):
        self.frame = Array(ctypes.c_ubyte,np.zeros([self.h,self.w],dtype = np.uint8).flatten())
    def stop_acquisition(self):
        self.close.set()
        self.stopTrigger.set()
        time.sleep(0.5)

class DummyCam(GenericCam):
    def __init__(self,outQ = None,lock = None):
        super(DummyCam,self).__init__()
        self.h = 600
        self.w = 900
        self.frame = Array(ctypes.c_ubyte,
                           np.zeros([self.h,self.w],dtype = np.uint8).flatten())
    def run(self):
        # Open camera and do all settings magic
        # Start and stop the process between runs?
        display('Set {0} camera properties'.format(self.name))
        self.nframes.value = 0
        buf = np.frombuffer(self.frame.get_obj(),
                            dtype = np.uint8).reshape([self.h,self.w])
        while not self.close.is_set(): 
            # Acquire a frame and place in queue
            #display('running dummy cam {0}'.format(self.nframes.value))
            frame = (np.ones([self.h,self.w],dtype = np.uint8)*np.mod(self.nframes.value,128)).astype(ctypes.c_ubyte)
            buf[:,:] = frame[:,:]
            self.nframes.value += 1
            time.sleep(1./30)
        display('Stopped...')


from pymba import *
def AVT_get_ids():
    with Vimba() as vimba:
        # get system object
        system = vimba.getSystem()
        # list available cameras (after enabling discovery for GigE cameras)
        if system.GeVTLIsPresent:
            system.runFeatureCommand("GeVDiscoveryAllOnce")
        time.sleep(0.2)
        camsIds = vimba.getCameraIds()
        cams = [vimba.getCamera(id) for id in camsIds]
        [cam.openCamera() for cam in cams]
        camsModel = [cam.DeviceModelName for cam in cams]
        
    return camsIds,camsModel

class AVTCam(GenericCam):
    def __init__(self, camId = None, outQ = None,exposure = 29000,
                 frameRate = 30., gain = 10,frameTimeout = 100,
                 nFrameBuffers = 1):
        super(AVTCam,self).__init__()
        if camId is None:
            display('Need to supply a camera ID.')
        self.camId = camId
        self.exposure = exposure
        self.frameRate = frameRate
        self.gain = gain
        self.frameTimeout = frameTimeout
        self.nbuffers = nFrameBuffers

        with Vimba() as vimba:
            system = vimba.getSystem()
            if system.GeVTLIsPresent:
                system.runFeatureCommand("GeVDiscoveryAllOnce")
            time.sleep(0.2)
            cam = vimba.getCamera(camId)
            cam.openCamera()
            names = cam.getFeatureNames()
            print(names)
            # get a frame
            cam.acquisitionMode = 'SingleFrame'
            frame = cam.getFrame()
            frame.announceFrame()
            cam.startCapture()
            frame.queueFrameCapture()
            cam.runFeatureCommand('AcquisitionStart')
            cam.runFeatureCommand('AcquisitionStop')
            frame.waitFrameCapture()
            self.h = frame.height
            self.w = frame.width
            self.initVariables()
            framedata = np.ndarray(buffer = frame.getBufferByteData(),
                                   dtype = np.uint8,
                                   shape = (frame.height,
                                            frame.width)).copy()
            buf = np.frombuffer(self.frame.get_obj(),
                                dtype = np.uint8).reshape([self.h,self.w])

            buf[:,:] = framedata[:,:]
            cam.endCapture()
            cam.revokeAllFrames()
            display("Got info from camera (name: {0})".format(
                cam.DeviceModelName))
        self.cameraReady = Event()
        
    def run(self):
        buf = np.frombuffer(self.frame.get_obj(),
                            dtype = np.uint8).reshape([self.h,self.w])
        while not self.close.is_set():

            with Vimba() as vimba:
                system = vimba.getSystem()
                if system.GeVTLIsPresent:
                    system.runFeatureCommand("GeVDiscoveryAllOnce")
                time.sleep(0.2)
                if not self.cameraReady.is_set():
                    # prepare camera
                    cam = vimba.getCamera(self.camId)
                    cam.openCamera()
                    cam.EventSelector = 'FrameTrigger'
                    cam.EventNotification = 'On'
                    cam.PixelFormat = 'Mono8'
                    cameraFeatureNames = cam.getFeatureNames()
                    cam.AcquisitionMode = 'Continuous'
                    cam.AcquisitionFrameRateAbs = self.frameRate
                    
#                    cam.ExposureTimeAbs =  
                    cam.GainRaw = self.gain 
                    cam.TriggerSource = 'FixedRate'
                    cam.TriggerMode = 'Off'
                    cam.TriggerSelector = 'AcquisitionStart'
                    # create new frames for the camera
                    frames = []
                    for i in range(self.nbuffers):
                        frames.append(cam.getFrame())    # creates a frame
                        frames[i].announceFrame()
                    cam.startCapture()
                    for f,ff in enumerate(frames):
                        try:
                            ff.queueFrameCapture()
                        except:
                            display('Queue frame error while getting cam ready: '+ str(f))
                            continue
                    display('Camera ready!')
                    self.cameraReady.set()
                    self.nframes.value = 0
                # Wait for trigger
                while not self.startTrigger.is_set():
                    # limits resolution to 1 ms 
                    time.sleep(0.001)
                cam.runFeatureCommand('AcquisitionStart')
                tstart = time.time()
                display('Started acquisition.')
                while not self.stopTrigger.is_set():
                    # run and acquire frames
                    for f in frames:
                        try:
                            f.waitFrameCapture(timeout = self.frameTimeout)
                        except VimbaException as err:
                            display('VimbaException: ' +  str(err))
                            continue
                        timestamp = f._frame.timestamp
                        frameID = f._frame.frameID
                        frame = np.ndarray(buffer = f.getBufferByteData(),
                                           dtype = np.uint8,
                                           shape = (f.height,
                                                    f.width)).copy()
                        self.nframes.value += 1
                        if self.saving.is_set():
                            self.outQ.put((frame.copy(),timestamp))
                        #display("Time {0} - {1}:".format(str(1./(time.time()-tstart)),self.nframes.value))
                        tstart = time.time()
                        try:
                            f.queueFrameCapture()
                        except:
                            display('Queue frame failed: '+ str(f))
                            pass
                        buf[:,:] = frame[:,:]
                
                cam.runFeatureCommand('AcquisitionStop')
                print('Stopped acquisition.')
                # Check if all frames are done...
                for f in frames:
                    try:
                        f.waitFrameCapture(timeout = 10)
                        timestamp = f._frame.timestamp
                        frameID = f._frame.frameID
                        frame = np.ndarray(buffer = f.getBufferByteData(),
                                           dtype = np.uint8,
                                           shape = (f.height,
                                                    f.width)).copy()
                        #f.queueFrameCapture()
                        if self.saving.is_set():
                            self.outQ.put(frame)
                        self.nframes.value += 1
                        self.frame = frame
                    except VimbaException as err:
                        display('VimbaException: ' + str(err))
                display('{4} delivered:{0},dropped:{1},queued:{4},time:{2}'.format(
                    cam.StatFrameDelivered,
                    cam.StatFrameDropped,
                    cam.StatTimeElapsed,
                    cam.DeviceModelName,
                    self.nframes.value))
                try:
                    cam.revokeAllFrames()
                except:
                    display('Failed to revoke frames.')
                cam.endCapture()
                self.saving.clear()
                self.cameraReady.clear()
                self.startTrigger.clear()
                self.stopTrigger.clear()

class QCam(GenericCam):
    def __init__(self, outQ = None):
        super(GenericCam,self).__init__()

