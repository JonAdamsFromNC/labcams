
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
import Image
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
    def initVariables(self,dtype=np.uint8):
        if dtype == np.uint8:
            self.frame = Array(ctypes.c_ubyte,np.zeros([self.h,self.w],dtype = dtype).flatten())
        else:
            self.frame = Array(ctypes.c_ushort,np.zeros([self.h,self.w],dtype = dtype).flatten())
    def stop_acquisition(self):
        self.stopTrigger.set()
        time.sleep(0.5)

    def stop(self):
        self.close.set()
        self.stopTrigger.set()
        
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
                 nFrameBuffers = 1,triggered = False,triggerSource = 'Line1'):
        super(AVTCam,self).__init__()
        if camId is None:
            display('Need to supply a camera ID.')
        self.camId = camId
        self.exposure = (1000000/int(frameRate)) - 150
        self.frameRate = frameRate
        self.gain = gain
        self.frameTimeout = frameTimeout
        self.nbuffers = nFrameBuffers
        self.queue = outQ
        self.dtype = np.uint8
        with Vimba() as vimba:
            system = vimba.getSystem()
            if system.GeVTLIsPresent:
                system.runFeatureCommand("GeVDiscoveryAllOnce")
            time.sleep(0.2)
            cam = vimba.getCamera(camId)
            cam.openCamera()
            names = cam.getFeatureNames()
            # get a frame
            cam.acquisitionMode = 'SingleFrame'
            cam.AcquisitionFrameRateAbs = self.frameRate
            cam.ExposureTimeAbs =  self.exposure
            cam.GainRaw = self.gain 
            cam.TriggerSource = 'FixedRate'
            cam.TriggerMode = 'Off'
            cam.TriggerSelector = 'FrameStart'
            frame = cam.getFrame()
            frame.announceFrame()
            cam.startCapture()
            frame.queueFrameCapture()
            cam.runFeatureCommand('AcquisitionStart')
            frame.waitFrameCapture()
            cam.runFeatureCommand('AcquisitionStop')
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
        self.triggered = triggered
        if self.triggered:
            display('Triggered mode ON.')
            self.triggerSource = triggerSource

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
#                    cam.EventSelector = 'FrameTrigger'
                    cam.EventNotification = 'On'
                    cam.PixelFormat = 'Mono8'
                    cameraFeatureNames = cam.getFeatureNames()
                    #display('\n'.join(cameraFeatureNames))
                    cam.AcquisitionMode = 'Continuous'
                    cam.AcquisitionFrameRateAbs = self.frameRate
                    cam.ExposureTimeAbs =  self.exposure
                    cam.GainRaw = self.gain 
                    if self.triggered :
                        cam.TriggerSource = 'Line1'#self.triggerSource
                        cam.TriggerMode = 'On'
                        cam.TriggerOverlap = 'Off'
                        cam.TriggerActivation = 'RisingEdge'
                        cam.TriggerSelector = 'FrameStart'
                    else:
                        cam.TriggerSource = 'FixedRate'
                        cam.TriggerMode = 'Off'
                        cam.TriggerSelector = 'FrameStart'
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
                    self.cameraReady.set()
                    self.nframes.value = 0
                # Wait for trigger
                while not self.startTrigger.is_set():
                    # limits resolution to 1 ms 
                    time.sleep(0.001)
                cam.runFeatureCommand("GevTimestampControlReset")
                cam.runFeatureCommand('AcquisitionStart')
                if self.triggered:
                    cam.TriggerMode = 'On'
                    cam.TriggerSelector = 'FrameStart'
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
                        newframe = frame.copy()
                        #display("Time {0} - {1}:".format(str(1./(time.time()-tstart)),self.nframes.value))
                        tstart = time.time()
                        try:
                            f.queueFrameCapture()
                        except:
                            display('Queue frame failed: '+ str(f) + 'Stopping!')
                            continue
                        if self.saving.is_set():
                            self.queue.put((frame.copy(),(frameID,timestamp)))
                        buf[:,:] = frame[:,:]
                
                cam.runFeatureCommand('AcquisitionStop')
                display('Stopped acquisition.')
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
                            self.queue.put((frame.copy(),(frameID,timestamp)))
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



import qimaging  as QCam

class QImagingCam(GenericCam):
    def __init__(self, camId = None,
                 outQ = None,
                 exposure = 100000,
                 gain = 3500,frameTimeout = 100,
                 nFrameBuffers = 1,
                 binning = 2,
                 triggerType = 0,
                 triggered = False):
        '''
        triggerType (0=freerun,1=hardware,5=software)
        '''
        
        super(QImagingCam,self).__init__()
        if camId is None:
            display('Need to supply a camera ID.')
            raise
        self.queue = outQ
        if triggered:
            self.triggerType = 1
        else:
            self.triggerType = 0
        self.camId = camId
        self.estimated_readout_lag = 1257 # microseconds
        self.binning = binning
        self.exposure = exposure
        self.gain = gain
        self.dtype = np.uint16
        self.frameRate = 1./(self.exposure/1000.)
        self.frameTimeout = frameTimeout
        self.nbuffers = nFrameBuffers
        QCam.ReleaseDriver()
        QCam.LoadDriver()
        cam = QCam.OpenCamera(QCam.ListCameras()[camId])
        if cam.settings.coolerActive:
            display('Qcam cooler active.')
        cam.settings.readoutSpeed=0 # 0=20MHz, 1=10MHz, 7=40MHz
        cam.settings.imageFormat = 'mono16'
        cam.settings.binning = self.binning
        cam.settings.emGain = gain
        cam.settings.triggerType = 0
        cam.settings.exposure = self.exposure - self.estimated_readout_lag
        cam.settings.blackoutMode=True
        cam.settings.Flush()
        cam.StartStreaming()
        frame = cam.GrabFrame()
        buf = np.frombuffer(frame.stringBuffer,dtype = np.uint16).reshape((frame.width,frame.height))
        self.h = frame.height
        self.w = frame.width

        cam.StopStreaming()
        cam.CloseCamera()
        QCam.ReleaseDriver()
        self.frame = Array(ctypes.c_ushort,np.zeros([self.w,self.h],dtype = np.uint16).flatten())

        framedata = np.ndarray(buffer = buf,
                               dtype = np.uint16,
                               shape = (self.w,
                                        self.h)).copy()
        buf[:,:] = framedata[:,:]
        #import pylab as plt
        #plt.imshow(buf)
        #plt.show()
        display("Got info from camera (name: {0})".format(camId))
        self.cameraReady = Event()

    def run(self):
        buf = np.frombuffer(self.frame.get_obj(),
                            dtype = np.uint16).reshape([self.w,self.h])
        QCam.ReleaseDriver()
        QCam.LoadDriver()
        while not self.close.is_set():
                time.sleep(0.2)
                if not self.cameraReady.is_set():
                    # prepare camera
                    cam = QCam.OpenCamera(QCam.ListCameras()[self.camId])
                    if cam.settings.coolerActive:
                        display('Qcam cooler active.')
                    cam.settings.readoutSpeed=0 # 0=20MHz, 1=10MHz, 7=40MHz
                    cam.settings.imageFormat = 'mono16'
                    cam.settings.binning = self.binning
                    cam.settings.emGain = self.gain
                    cam.settings.exposure = self.exposure - self.estimated_readout_lag
                    cam.settings.triggerType = self.triggerType

                    cam.settings.blackoutMode=True
                    cam.settings.Flush()
                    queue = QCam.CameraQueue(cam)
                    display('Camera ready!')
                    self.cameraReady.set()
                    self.nframes.value = 0
                # Wait for trigger
                while not self.startTrigger.is_set():
                    # limits resolution to 1 ms 
                    time.sleep(0.001)
                queue.start()
                tstart = time.time()
                display('Started acquisition.')

                while not self.stopTrigger.is_set():
                    # run and acquire frames
                    try:
                        f = queue.get(True, 1)
                    except queue.Empty:
                        continue
                    self.nframes.value += 1
                    frame = np.ndarray(buffer = f.stringBuffer,
                                        dtype = np.uint16,
                                        shape = (self.w,
                                                 self.h)).copy()
                    
                    #display("Time {0} - {1}:".format(str(1./(time.time()-tstart)),self.nframes.value))
                    tstart = time.time()
                    timestamp = f.timeStamp
                    frameID = f.frameNumber
                    if self.saving.is_set():
                        self.queue.put((frame.reshape([self.h,self.w]),(frameID,timestamp)))
                    buf[:,:] = frame[:,:]
                    queue.put(f)

                #cam.runFeatureCommand('AcquisitionStop')
                queue.stop()

                cam.StopStreaming()
                cam.CloseCamera()
                self.saving.clear()
                self.cameraReady.clear()
                self.startTrigger.clear()
                self.stopTrigger.clear()
                
                #cam.settings.blackoutMode=False
                #cam.settings.Flush()

                display('Stopped acquisition.')
        QCam.ReleaseDriver()

    def stop(self):
        self.close.set()
        self.stop_acquisition()
