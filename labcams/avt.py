from .cams import *
# Allied Vision Technologies cameras
from pymba import *

def AVT_get_ids():
    with Vimba() as vimba:
        # get system object
        system = vimba.getSystem()
        # list available cameras (after enabling discovery for GigE cameras)
        if system.GeVTLIsPresent:
            system.runFeatureCommand("GeVDiscoveryAllOnce")
        #time.sleep(0.01)
        camsIds = vimba.getCameraIds()
        cams = [vimba.getCamera(id) for id in camsIds]
        camsModel = []
        for camid,cam in zip(camsIds,cams):
            try:
                cam.openCamera()
                
            except:
                camsModel.append('')
                continue
            camsModel.append('{0} {1} {2}'.format(cam.DeviceModelName,
                                                  cam.DevicePartNumber,
                                                  cam.DeviceID))
    return camsIds,camsModel

class AVTCam(GenericCam):    
    def __init__(self, camId = None, outQ = None,
                 exposure = 29000,
                 frameRate = 30., gain = 10,frameTimeout = 100,
                 nFrameBuffers = 10,
                 triggered = Event(),
                 triggerSource = 'Line1',
                 triggerMode = 'LevelHigh',
                 triggerSelector = 'FrameStart',
                 acquisitionMode = 'Continuous',
                 nTriggeredFrames = 1000,
                 frame_timeout = 100,
                 recorderpar = None):
        self.drivername = 'AVT'
        super(AVTCam,self).__init__(outQ=outQ,recorderpar=recorderpar)
        if camId is None:
            display('Need to supply a camera ID.')
        self.cam_id = camId
        self.exposure = ((1000000/int(frameRate)) - 150)/1000.
        self.frame_rate = frameRate
        self.gain = gain
        self.frameTimeout = frameTimeout
        self.triggerSource = triggerSource
        self.triggerSelector = triggerSelector
        self.acquisitionMode = acquisitionMode
        self.nTriggeredFrames = nTriggeredFrames 
        self.nbuffers = nFrameBuffers
        self.frame_timeout = frame_timeout
        self.triggerMode = triggerMode
        self.tickfreq = float(1.0)
        with Vimba() as vimba:
            system = vimba.getSystem()
            if system.GeVTLIsPresent:
                system.runFeatureCommand("GeVDiscoveryAllOnce")
            time.sleep(0.01)
            self.cam = vimba.getCamera(camId)
            self.cam.openCamera()
            names = self.cam.getFeatureNames()
            # get a frame
            self.cam.acquisitionMode = 'SingleFrame'
            self.set_exposure(self.exposure)
            self.set_framerate(self.frame_rate)
            self.set_gain(self.gain)
            self.tickfreq = float(self.cam.GevTimestampTickFrequency)
            self.cam.TriggerSource = 'FixedRate'
            self.cam.TriggerMode = 'Off'
            self.cam.TriggerSelector = 'FrameStart'
            frame = self.cam.getFrame()
            frame.announceFrame()
            self.cam.startCapture()
            frame.queueFrameCapture()
            self.cam.runFeatureCommand('AcquisitionStart')
            frame.waitFrameCapture()
            self.cam.runFeatureCommand('AcquisitionStop')
            self.h = frame.height
            self.w = frame.width
            self.dtype = np.uint8
            self._init_variables(dtype = self.dtype)
            framedata = np.ndarray(buffer = frame.getBufferByteData(),
                                   dtype = self.dtype,
                                   shape = (frame.height,
                                            frame.width)).copy()
            self.img[:] = np.reshape(framedata,self.img.shape)[:]
            display("AVT [{1}] = Got info from camera (name: {0})".format(
                self.cam.DeviceModelName,self.cam_id))
            self.cam.endCapture()
            self.cam.revokeAllFrames()
            self.cam = None
        self.triggered = triggered
        if self.triggered.is_set():
            display('AVT [{0}] - Triggered mode ON.'.format(self.cam_id))
            self.triggerSource = triggerSource
    def _init_controls(self):
        self.ctrevents = dict(
            exposure=dict(
                function = 'set_exposure',
                widget = 'float',
                variable = 'exposure',
                units = 'ms',
                type = 'float',
                min = 0.001,
                max = 100000,
                step = 10),
            gain = dict(
                function = 'set_gain',
                widget = 'float',
                variable = 'gain',
                units = 'ms',
                type = 'int',
                min = 0,
                max = 30,
                step = 1),
            framerate = dict(
                function = 'set_framerate',
                widget = 'float',
                type = 'float',
                variable = 'frame_rate',
                units = 'fps',
                min = 0.001,
                max = 1000,
                step = 1))
        
    def set_exposure(self,exposure = 30):
        '''Set the exposure time is in ms'''
        self.exposure = exposure
        if not self.cam is None:
            self.cam.ExposureTimeAbs =  int(self.exposure*1000)
            display('[AVT {0}] Setting exposure to {1} ms.'.format(
                self.cam_id, self.exposure))

    def set_framerate(self,frame_rate = 30):
        '''set the frame rate of the AVT camera.''' 
        self.frame_rate = frame_rate
        if not self.cam is None:
            self.cam.AcquisitionFrameRateAbs = self.frame_rate
            if self.cam_is_running:
                self.start_trigger.set()
                self.stop_trigger.set()
            display('[AVT {0}] Setting frame rate to {1} .'.format(
                self.cam_id, self.frame_rate))
    def set_gain(self,gain = 0):
        ''' Set the gain of the AVT camera'''
        self.gain = int(gain)
        if not self.cam is None:
            self.cam.GainRaw = self.gain
            display('[AVT {0}] Setting camera gain to {1} .'.format(
                self.cam_id, self.gain))
    
    def _cam_init(self):
        self.nframes.value = 0
        self.recorded_frames = []
        self.vimba = Vimba()
        self.vimba.startup()
        system = self.vimba.getSystem()
        if system.GeVTLIsPresent:
            system.runFeatureCommand("GeVDiscoveryAllOnce")
            time.sleep(0.1)
        # prepare camera
        self.cam = self.vimba.getCamera(self.cam_id)
        self.cam.openCamera()
        # cam.EventSelector = 'FrameTrigger'
        self.cam.EventNotification = 'On'
        self.cam.PixelFormat = 'Mono8'
        self.cameraFeatureNames = self.cam.getFeatureNames()
        #display('\n'.join(cameraFeatureNames))
        self.set_framerate(self.frame_rate)
        self.set_gain(self.gain)
        self.set_exposure(self.exposure)
        
        self.cam.SyncOutSelector = 'SyncOut1'
        self.cam.SyncOutSource = 'FrameReadout'#'Exposing'
        if self.triggered.is_set():
            self.cam.TriggerSource = self.triggerSource#'Line1'#self.triggerSource
            self.cam.TriggerMode = 'On'
            #cam.TriggerOverlap = 'Off'
            self.cam.TriggerActivation = self.triggerMode #'LevelHigh'##'RisingEdge'
            self.cam.AcquisitionMode = self.acquisitionMode
            self.cam.TriggerSelector = self.triggerSelector
            if self.acquisitionMode == 'MultiFrame':
                self.cam.AcquisitionFrameCount = self.nTriggeredFrames
                self.cam.TriggerActivation = self.triggerMode #'LevelHigh'##'RisingEdge'
        else:
            display('[Cam - {0}] Using no trigger.'.format(self.cam_id))
            self.cam.AcquisitionMode = 'Continuous'
            self.cam.TriggerSource = 'FixedRate'
            self.cam.TriggerMode = 'Off'
            self.cam.TriggerSelector = 'FrameStart'
        # create new frames for the camera
        self.frames = []
        for i in range(self.nbuffers):
            self.frames.append(self.cam.getFrame())    # creates a frame
            self.frames[i].announceFrame()
        self.cam.startCapture()
        for f,ff in enumerate(self.frames):
            try:
                ff.queueFrameCapture()
            except:
                display('Queue frame error while getting cam ready: '+ str(f))
                continue                    
        self.camera_ready.set()
        self.nframes.value = 0
        # Ready to wait for trigger
            
    def _cam_startacquisition(self):
        self.cam.runFeatureCommand("GevTimestampControlReset")
        self.cam.runFeatureCommand('AcquisitionStart')
        if self.triggered.is_set():
            self.cam.TriggerSelector = self.triggerSelector
            self.cam.TriggerMode = 'On'
        #tstart = time.time()
        self.lastframeid = [-1 for i in self.frames]

    def _cam_loop(self):
        # run and acquire frames
        #sortedfids = np.argsort([f._frame.frameID for f in frames])
        for ibuf in range(self.nbuffers):
            f = self.frames[ibuf]
            avterr = f.waitFrameCapture(timeout = self.frameTimeout)
            if avterr == 0:
                timestamp = f._frame.timestamp/self.tickfreq
                frameID = f._frame.frameID
                #print('Frame id:{0}'.format(frameID))
                if not frameID in self.recorded_frames:
                    self.recorded_frames.append(frameID)
                    frame = np.ndarray(buffer = f.getBufferByteData(),
                                       dtype = self.dtype,
                                       shape = (f.height,
                                                f.width)).copy()
                    #display("Time {0} - {1}:".format(str(1./(time.time()-tstart)),self.nframes.value))
                    #tstart = time.time()
                    try:
                        f.queueFrameCapture()
                    except:
                        display('Queue frame failed: '+ str(f))
                        return None,(None,None)
                    self.lastframeid[ibuf] = frameID
                    return frame,(frameID,timestamp)
            elif avterr == -12:
                #display('VimbaException: ' +  str(avterr))        
                return None,(None,None)

    def _cam_close(self):
        self.cam.runFeatureCommand('AcquisitionStop')
        display('[AVT] - Stopped acquisition.')
        # Check if all frames are done...
        for ibuf in range(self.nbuffers):
            f = self.frames[ibuf]
            try:
                f.waitFrameCapture(timeout = self.frame_timeout)
                timestamp = f._frame.timestamp/self.tickfreq
                frameID = f._frame.frameID
                frame = np.ndarray(buffer = f.getBufferByteData(),
                                   dtype = self.dtype,
                                   shape = (f.height,
                                            f.width)).copy()
                if self.saving.is_set():
                    self.was_saving = True
                    if not frameID in self.lastframeid :
                        self.queue.put((frame.copy(),(frameID,timestamp)))
                elif self.was_saving:
                    self.was_saving = False
                    self.queue.put(['STOP'])

                self.lastframeid[ibuf] = frameID
                self.nframes.value += 1
                self.frame = frame
            except VimbaException as err:
                #display('VimbaException: ' + str(err))
                pass
        display('{4} delivered:{0},dropped:{1},queued:{4},time:{2}'.format(
            self.cam.StatFrameDelivered,
            self.cam.StatFrameDropped,
            self.cam.StatTimeElapsed,
            self.cam.DeviceModelName,
            self.nframes.value))
        self.cam.runFeatureCommand('AcquisitionStop')
        self.cam.endCapture()
        try:
            self.cam.revokeAllFrames()
        except:
            display('Failed to revoke frames.')
        self.cam.closeCamera()
        display('AVT [{0}] - Close event: {1}'.format(
            self.cam_id,
            self.close_event.is_set()))
        self.vimba.shutdown()
