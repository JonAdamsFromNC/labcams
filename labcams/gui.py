# Qt imports
import sys
import os
from .utils import display,getPreferences
from .cams import *
from .io import *
import cv2
import ctypes
try:
    from mptracker import MPTracker
    from mptracker.widgets import MptrackerParameters
except:
    pass
try:
    from PyQt5.QtWidgets import (QWidget,
                                 QApplication,
                                 QGridLayout,
                                 QFormLayout,
                                 QVBoxLayout,
                                 QTabWidget,
                                 QCheckBox,
                                 QTextEdit,
                                 QLineEdit,
                                 QComboBox,
                                 QFileDialog,
                                 QSlider,
                                 QPushButton,
                                 QLabel,
                                 QAction,
                                 QMenuBar,
                                 QGraphicsView,
                                 QGraphicsScene,
                                 QGraphicsItem,
                                 QGraphicsLineItem,
                                 QGroupBox,
                                 QTableWidget,
                                 QMainWindow,
                                 QDockWidget,
                                 QFileDialog)
    from PyQt5.QtGui import QImage, QPixmap,QBrush,QPen,QColor
    from PyQt5.QtCore import Qt,QSize,QRectF,QLineF,QPointF,QTimer
except:
    from PyQt4.QtGui import (QWidget,
                             QApplication,
                             QAction,
                             QMainWindow,
                             QDockWidget,
                             QMenuBar,
                             QGridLayout,
                             QFormLayout,
                             QLineEdit,
                             QFileDialog,
                             QVBoxLayout,
                             QCheckBox,
                             QTextEdit,
                             QComboBox,
                             QSlider,
                             QLabel,
                             QPushButton,
                             QGraphicsView,
                             QGraphicsScene,
                             QGraphicsItem,
                             QGraphicsLineItem,
                             QGroupBox,
                             QTableWidget,
                             QFileDialog,
                             QImage,
                             QPixmap)
    from PyQt4.QtCore import Qt,QSize,QRectF,QLineF,QPointF,QTimer

from multiprocessing import Queue,Event
import zmq

class LabCamsGUI(QMainWindow):
    app = None
    cams = []
    def __init__(self,app = None, expName = 'test',
                 camDescriptions = [],
                 parameters = {},
                 server = True,
                 saveOnStart = False,
                 triggered = False,
                 updateFrequency = 50):
        super(LabCamsGUI,self).__init__()
        display('Starting labcams interface.')
        self.parameters = parameters
        self.app = app
        self.updateFrequency=updateFrequency
        self.saveOnStart = saveOnStart
        self.cam_descriptions = camDescriptions
        self.triggered = Event()
        if triggered:
            self.triggered.set()
        else:
            self.triggered.clear()
        # Init cameras
        camdrivers = [cam['driver'] for cam in camDescriptions]
        if 'AVT' in camdrivers:
            try:
                avtids,avtnames = AVT_get_ids()
            except:
                display('AVT camera error? Connections? Parameters?')
        self.camQueues = []
        self.writers = []
        connected_avt_cams = []
        for c,cam in enumerate(self.cam_descriptions):
            display("Connecting to camera [" + str(c) + '] : '+cam['name'])
            if not 'Save' in cam.keys():
                cam['Save'] = True
            if cam['driver'] == 'AVT':
                camids = [(camid,name) for (camid,name) in zip(avtids,avtnames) 
                          if cam['name'] in name]
                camids = [camid for camid in camids
                          if not camid[0] in connected_avt_cams]
                if len(camids) == 0:
                    display('Could not find or already connected to: '+cam['name'])
                    sys.exit()
                cam['name'] = camids[0][1]
                if not 'TriggerSource' in cam.keys():
                    cam['TriggerSource'] = 'Line1'
                if not 'TriggerMode' in cam.keys():
                    cam['TriggerMode'] = 'LevelHigh'
                if not 'TriggerSelector' in cam.keys():
                    cam['TriggerSelector'] = 'FrameStart'
                    print('Using FrameStart for triggering.')
                if not 'AcquisitionMode' in cam.keys():
                    cam['AcquisitionMode'] = 'Continuous'
                if not 'AcquisitionFrameCount' in cam.keys():
                    cam['AcquisitionFrameCount'] = 1000
                if not 'nFrameBuffers' in cam.keys():
                    cam['nFrameBuffers'] = 1
                    
                self.camQueues.append(Queue())
                if cam['Save']:
                    self.writers.append(TiffWriter(inQ = self.camQueues[-1],
                                                   dataFolder=self.parameters['recorder_path'],
                                                   framesPerFile=self.parameters['recorder_frames_per_file'],
                                                   sleepTime = self.parameters['recorder_sleep_time'],
                                                   filename = expName,
                                                   dataName = cam['description']))
                else:
                    self.writers.append(None)
                
                self.cams.append(AVTCam(camId=camids[0][0],
                                        outQ = self.camQueues[-1],
                                        frameRate=cam['frameRate'],
                                        gain=cam['gain'],
                                        triggered = self.triggered,
                                        triggerSource = cam['TriggerSource'],
                                        triggerMode = cam['TriggerMode'],
                                        triggerSelector = cam['TriggerSelector'],
                                        acquisitionMode = cam['AcquisitionMode'],
                                        nTriggeredFrames = cam['AcquisitionFrameCount'],
                                        nFrameBuffers = cam['nFrameBuffers']))
                connected_avt_cams.append(camids[0][0])
            elif cam['driver'] == 'QImaging':
                self.camQueues.append(Queue())
                if cam['Save']:
                    self.writers.append(
                        TiffWriter(inQ = self.camQueues[-1],
                                   dataFolder=self.parameters['recorder_path'],
                                   framesPerFile=self.parameters['recorder_frames_per_file'],
                                   sleepTime = self.parameters['recorder_sleep_time'],
                                   filename = expName,
                                   dataName = cam['description']))
                else:
                    self.writers.append(None)
                if not 'binning' in cam.keys():
                    cam['binning'] = 2
                self.cams.append(QImagingCam(camId=cam['id'],
                                             outQ = self.camQueues[-1],
                                             exposure=cam['exposure'],
                                             gain=cam['gain'],
                                             binning = cam['binning'],
                                             triggerType = cam['triggerType'],
                                             triggered = self.triggered))
            elif cam['driver'] == 'OpenCV':
                self.camQueues.append(Queue())
                if cam['Save']:
                    self.writers.append(
                        TiffWriter(inQ = self.camQueues[-1],
                                   dataFolder=self.parameters['recorder_path'],
                                   framesPerFile=self.parameters['recorder_frames_per_file'],
                                   sleepTime = self.parameters['recorder_sleep_time'],
                                   filename = expName,
                                   dataName = cam['description']))
                else:
                    self.writers.append(None)
                self.cams.append(OpenCVCam(camId=cam['id'],
                                           outQ = self.camQueues[-1],
                                           triggered = self.triggered))
            else:
            	display('Unknown camera driver' + cam['driver'])
            # Print parameteres
            print('\n\t Camera: {0}'.format(cam['name']))
            for k in np.sort(list(cam.keys())):
                if not k == 'name':
                    print('\t\t - {0} {1}'.format(k,cam[k]))
            if cam['Save']:
                self.writers[-1].daemon = True
            self.cams[-1].daemon = True
#        self.resize(500,700)

        self.initUI()
        
        if server:
            self.zmqContext = zmq.Context()
            self.zmqSocket = self.zmqContext.socket(zmq.REP)
            self.zmqSocket.bind('tcp://0.0.0.0:{0}'.format(self.parameters['server_port']))
            display('Listening to port: {0}'.format(self.parameters['server_port']))
        self.camerasRunning = False
        for cam,writer in zip(self.cams,self.writers):
            cam.start()
            if not writer is None:
                writer.start()
        camready = 0
        while camready != len(self.cams):
            camready = np.sum([cam.cameraReady.is_set() for cam in self.cams])
        display('Initialized cameras.')
        self.zmqTimer = QTimer()
        self.zmqTimer.timeout.connect(self.zmqActions)
        self.zmqTimer.start(500)
        self.triggerCams(save=self.saveOnStart)

    def setExperimentName(self,expname):
        # Makes sure that the experiment name has the right slashes.
        if os.path.sep == '/':
            expname = expname.replace('\\',os.path.sep)
        for writer in self.writers:
            if not writer is None:
                writer.setFilename(expname)
        time.sleep(0.5)
        self.recController.experimentNameEdit.setText(expname)
        
    def zmqActions(self):
        try:
            message = self.zmqSocket.recv_pyobj(flags=zmq.NOBLOCK)
        except zmq.error.Again:
            return
        self.zmqSocket.send_pyobj(dict(action='handshake'))
        if message['action'] == 'expName':
            self.setExperimentName(message['value'])
        elif message['action'] == 'trigger':
            for c,(cam,writer) in enumerate(zip(self.cams,self.writers)):
                if not writer is None:
                    cam.saving.clear()
                    writer.write.clear()
            # stop previous saves if there were any
            for cam in self.cams:
                cam.stop_acquisition()
            time.sleep(1.5)
            self.triggerCams(save = True)

    def triggerCams(self,save=False):
        display('Trigger cams pressed with save:{0}'.format(save))
        if save:
            for c,(cam,writer) in enumerate(zip(self.cams,self.writers)):
                if not writer is None:
                    cam.saving.set()
                    writer.write.set()
        else:
            for c,(cam,writer) in enumerate(zip(self.cams,self.writers)):
                if not writer is None:
                    cam.saving.clear()
                    writer.write.clear()
        #time.sleep(2)
        display("Starting software trigger for all cammeras.")
        for c,cam in enumerate(self.cams):
            while not cam.cameraReady.is_set():
                time.sleep(0.02)
            display('Camera {{0}} ready.'.format(c))
        for c,cam in enumerate(self.cams):
            cam.startTrigger.set()
        display('Software triggered cameras.')
        
    def experimentMenuTrigger(self,q):
        display(q.text()+ "clicked. ")
        
    def initUI(self):
        # Menu
        bar = self.menuBar()
        editmenu = bar.addMenu("Experiment")
        editmenu.addAction("New")
        editmenu.triggered[QAction].connect(self.experimentMenuTrigger)
        self.setWindowTitle("LabCams")
        self.tabs = []
        self.camwidgets = []
        for c,cam in enumerate(self.cams):
            self.tabs.append(QDockWidget("Camera: "+str(c),self))
            layout = QVBoxLayout()
            self.camwidgets.append(CamWidget(frame = np.zeros((cam.h,cam.w),
                                                              dtype=cam.dtype),
                                             iCam = c,
                                             parent = self,
                                             parameters = self.cam_descriptions[c]))
            self.tabs[-1].setWidget(self.camwidgets[-1])
            self.tabs[-1].setFloating(False)
            #if c < 1:
            #self.addDockWidget(
            #    Qt.RightDockWidgetArea and Qt.TopDockWidgetArea,
            #    self.tabs[-1])
            #else:
            self.addDockWidget(
                Qt.BottomDockWidgetArea,
                self.tabs[-1])
                
            self.tabs[-1].setFixedSize(cam.w,cam.h)
            display('Init view: ' + str(c))
        self.tabs.append(QDockWidget("Controller",self))
        self.recController = RecordingControlWidget(self)
        self.tabs[-1].setWidget(self.recController)
        self.tabs[-1].setFloating(False)
        self.addDockWidget(
            Qt.RightDockWidgetArea and Qt.TopDockWidgetArea,
            self.tabs[-1])
        self.timer = QTimer()
        self.timer.timeout.connect(self.timerUpdate)
        self.timer.start(self.updateFrequency)
        self.camframes = []
        for c,cam in enumerate(self.cams):
            self.camframes.append(cam.img)
            #if cam.dtype == np.uint8:
            #    self.camframes.append(np.frombuffer(
            #        cam.frame.get_obj(),
            #        dtype = ctypes.c_ubyte).reshape([cam.h,cam.w]))
            #else:
        	#self.camframes.append(np.frombuffer(
                #    cam.frame.get_obj(),
                #    dtype = ctypes.c_ushort).reshape([cam.h,cam.w]))
        self.move(0, 0)
        self.show()
            	
    def timerUpdate(self):
        for c,(cam,frame) in enumerate(zip(self.cams,self.camframes)):
            self.camwidgets[c].image(frame,cam.nframes.value)

    def closeEvent(self,event):
        for cam in self.cams:
            cam.stop_acquisition()
        display('Acquisition duration:')
        for c,(cam,writer) in enumerate(zip(self.cams,self.writers)):
            if not writer is None:
                cam.saving.clear()
                writer.write.clear()
                writer.stop()
            cam.stop()
        for c in self.cams:
            c.join()
        for c,(cam,writer) in enumerate(zip(self.cams,self.writers)):
            if not writer is None:
                display('   ' + self.cam_descriptions[c]['name']+
                        ' [ Acquired:'+
                        str(cam.nframes.value) + ' - Saved: ' + 
                        str(writer.frameCount.value) +']')
                writer.join()
        event.accept()

class RecordingControlWidget(QWidget):
    def __init__(self,parent):
        super(RecordingControlWidget,self).__init__()	
        self.parent = parent
        form = QFormLayout()

        self.experimentNameEdit = QLineEdit(' ')
        self.changeNameButton = QPushButton('Set name')
        form.addRow(self.experimentNameEdit,self.changeNameButton)
        self.changeNameButton.clicked.connect(self.setExpName)

        self.camTriggerToggle = QCheckBox()
        self.camTriggerToggle.setChecked(self.parent.triggered.is_set())
        self.camTriggerToggle.stateChanged.connect(self.toggleTriggered)
        form.addRow(QLabel("Trigger cams: "),self.camTriggerToggle)
        
        
        self.saveOnStartToggle = QCheckBox()
        self.saveOnStartToggle.setChecked(self.parent.saveOnStart)
        self.saveOnStartToggle.stateChanged.connect(self.toggleSaveOnStart)
        form.addRow(QLabel("Manual save: "),self.saveOnStartToggle)
        self.setLayout(form)

    def toggleTriggered(self,value):
        display('Toggle trigger mode pressed [{0}]'.format(value))
        if value:
            self.parent.triggered.set()
        else:
            #self.toggleSaveOnStart(False)
            # save button does not get unticked (this is a bug)
            if self.saveOnStartToggle.isChecked():
                self.saveOnStart = False
                self.saveOnStartToggle.setCheckState(Qt.Unchecked)
            self.parent.triggered.clear()
        for cam in self.parent.cams:
            cam.stop_acquisition()
        time.sleep(.5)
        self.parent.triggerCams(save = self.parent.saveOnStart)
        
    def setExpName(self):
        name = self.experimentNameEdit.text()
        if not self.saveOnStartToggle.isChecked():
            self.parent.setExperimentName(str(name))
        else:
            print('[Critical message] Disable manual save to change the filename!')

    def toggleSaveOnStart(self,state):
        display('Toggled ManualSave [{0}]'.format(state))
        self.parent.saveOnStart = state
        print('Warning: The save button is no longer restarting the cameras.')
        #for cam in self.parent.cams:
        #    cam.stop_acquisition()
        #time.sleep(.5) 
        self.parent.triggerCams(save = state)
        
class CamWidget(QWidget):
    def __init__(self,frame, iCam = 0, parent = None, parameters = None):
        super(CamWidget,self).__init__()
        self.parent = parent
        self.iCam = iCam
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        saveImg = QAction("Take camera shot",self)
        saveImg.triggered.connect(self.saveImageFromCamera)
        self.addAction(saveImg)
        toggleSubtract = QAction("Background subtraction",self)
        toggleSubtract.triggered.connect(self.toggleSubtract)
        self.addAction(toggleSubtract)
        tEq = QAction('Equalize histogram',self)
        tEq.triggered.connect(self.toggleEqualize)
        self.addAction(tEq)
        tEt = QAction('Eye tracker',self)
        tEt.triggered.connect(self.toggleEyeTracker)
        self.addAction(tEt)
        self.scene=QGraphicsScene(0,0,frame.shape[1],
                                  frame.shape[0],self)
        self.view = QGraphicsView(self.scene, self)
        self.lastnFrame = 0
        if not 'SubtractBackground' in parameters.keys():
            parameters['SubtractBackground'] = False
        if not 'Equalize' in parameters.keys():
            parameters['Equalize'] = False
        if not 'TrackEye' in parameters.keys():
            parameters['TrackEye'] = False
        self.parameters = parameters
        self.lastFrame = frame.copy().astype(np.float32)
        if not 'NBackgroundFrames' in parameters.keys():
            self.nAcum = 3.
        else:
            self.nAcum = float(parameters['NBackgroundFrames'])
        self.eyeTracker = None
        self.string = '{0}'
        if not self.parameters['Save']:
            self.string = 'no save -{0}'
        self.image(np.array(frame),-1)
        
        #self.show()
        
    def toggleSubtract(self):
        self.parameters['SubtractBackground'] = not self.parameters['SubtractBackground']
    def toggleEqualize(self):
        self.parameters['Equalize'] = not self.parameters['Equalize']
    def toggleEyeTracker(self):
        if self.parameters['TrackEye']:
            self.eyeTracker = None
            self.trackerpar.close()
            self.trackerTab.close()
        self.parameters['TrackEye'] = not self.parameters['TrackEye']
        
    def saveImageFromCamera(self):
        self.parent.timer.stop()
        frame = self.parent.camframes[self.iCam]
        filename = QFileDialog.getSaveFileName(self,
                                               'Select filename to save.')
        if type(filename) is tuple:
            filename = filename[0]
        if filename:
            from tifffile import imsave
            imsave(str(filename),
                   frame,
                   metadata = {
                       'Camera':str(self.iCam)})
            print('Saved camera frame for cam: {0}'.format(self.iCam))
        else:
            display('Aborted.')
        self.parent.timer.start()
        
    def _open_mptracker(self,image):
        self.eyeTracker = MPTracker(drawProcessedFrame=True)
        self.trackerTab = QDockWidget("MousePupilTRACKER",self.parent)
        self.eyeTracker.parameters['crTrack'] = True
        self.eyeTracker.parameters['sequentialCRMode'] = False
        self.eyeTracker.parameters['sequentialPupilMode'] = False
        self.trackerpar = MptrackerParameters(self.eyeTracker,image)
        self.trackerTab.setWidget(self.trackerpar)
        self.trackerTab.setFloating(False)
        self.trackerpar.resize(400,200)
        self.parent.addDockWidget(Qt.RightDockWidgetArea and
                                  Qt.BottomDockWidgetArea,
                                  self.trackerTab)
        
    def image(self,image,nframe):
        if self.lastnFrame != nframe:
            self.scene.clear()
            if self.parameters['TrackEye']:
                if self.eyeTracker is None:
                    self._open_mptracker(image.copy())
                img = self.eyeTracker.apply(image.copy()) 
                frame = self.eyeTracker.img
            else:
                tmp = image.copy()
                if self.parameters['Equalize']:
                    try: # In case the type is messed up..
                        tmp = cv2.equalizeHist(tmp)
                    except:
                        pass
                if self.parameters['SubtractBackground']:
                    tmp = tmp.astype(np.float32)
                    frame = (np.abs(tmp - self.lastFrame))*10.
                    self.lastFrame = ((1-1/self.nAcum)*(self.lastFrame.astype(np.float32)) +
                                      (1/self.nAcum)*tmp)
                else:
                    frame = tmp
            if self.parameters['driver'] == 'QImaging':
                frame = np.array((frame.astype(np.float32)/2.**14)*2.**8).astype(np.uint8)
            if len(frame.shape) == 2 :
                frame = cv2.cvtColor(frame.astype(np.uint8), cv2.COLOR_GRAY2BGR)
            cv2.putText(frame,self.string.format(nframe), (10,100), cv2.FONT_HERSHEY_SIMPLEX,
                        1, 105,2)
            self.qimage = QImage(frame, frame.shape[1], frame.shape[0], 
                                 frame.strides[0], QImage.Format_RGB888)
            self.scene.addPixmap(QPixmap.fromImage(self.qimage))
            #self.view.fitInView(QRectF(0,0,
            #                           frame.shape[1],
            #                           frame.shape[0]),
            #                    Qt.KeepAspectRatio)
            self.lastnFrame = nframe
            self.scene.update()


def main():
    from argparse import ArgumentParser
    import os
    import json
    
    parser = ArgumentParser(description='Script to control and record from cameras.')
    parser.add_argument('preffile',
                        metavar='configfile',
                        type=str,
                        default=None,
                        nargs="?")
    parser.add_argument('-d','--make-config',
                        type=str,
                        default = None,
                        action='store')
    parser.add_argument('--triggered',
                        default=False,
                        action='store_true')
    parser.add_argument('-c','--cam-select',
                        type=int,
                        nargs='+',
                        action='store')
    parser.add_argument('--no-server',
                        default=False,
                        action='store_true')
    parser.add_argument('-a','--analyse',
                        default=False,
                        action='store_true')
    opts = parser.parse_args()
    if not opts.make_config is None:
        fname = opts.make_config
        getPreferences(fname,create=True)
        sys.exit()
    parameters = getPreferences(opts.preffile)
    cams = parameters['cams']
    if not opts.cam_select is None:
        cams = [parameters['cams'][i] for i in opts.cam_select]

    if not opts.analyse:
        app = QApplication(sys.argv)
        w = LabCamsGUI(app = app,
                       camDescriptions = cams,
                       parameters = parameters,
                       server = not opts.no_server,
                       triggered = opts.triggered)
        sys.exit(app.exec_())
    else:
        app = QApplication(sys.argv)
        fname = os.path.abspath(str(QFileDialog.getExistingDirectory(None,"Select Directory of the run to process",
                                                     parameters['datapaths']['dataserverpaths'][0])))
        from .utils import cameraTimesFromVStimLog,findVStimLog
        from .io import parseCamLog,TiffStack
        from tqdm import tqdm
        import numpy as np
        from glob import glob
        import os
        from os.path import join as pjoin
        from pyvstim import parseVStimLog as parseVStimLog,parseProtocolFile,getStimuliTimesFromLog
        if not "linux" in sys.platform:
            fname = pjoin(*fname.split("/"))
        expname = fname.split(os.path.sep)[-2:]
        camlogext = '.camlog'
        camlogfile = glob(pjoin(fname,'*'+camlogext))
        if not len(camlogfile):
            print('Camera logfile not found in: {0}'.format(fname))
            import ipdb
            ipdb.set_trace()
            sys.exit()
        else:
            camlogfile = camlogfile[0]
        camlog = parseCamLog(camlogfile)[0]
        logfile = findVStimLog(expname)
        plog,pcomms = parseVStimLog(logfile)
        protopts,prot = parseProtocolFile(logfile.replace('.log','.prot'))
        camidx = 3
        camlog = cameraTimesFromVStimLog(camlog,plog,camidx = camidx)
        camdata = TiffStack(fname)
        (stimtimes,stimpars,stimoptions) = getStimuliTimesFromLog(logfile,plog)
        camtime = np.array(camlog['duinotime']/1000.)
        stimavgs = triggeredAverage(camdata,camtime,stimtimes)
        # remove loops if there
        for iStim in range(len(stimavgs)):
            nloops = 0
            for p in prot.iloc[iStim]:
                if isinstance(p, str):
                    if 'loop' in p:
                        nloops = int(p.strip(')').split(',')[-1])
            if nloops > 0:
                print('Handling loops for stim {0}.'.format(iStim))
                idx = np.where(stimavgs[iStim][:,0,0] > np.min(stimavgs[iStim][:,0,0]))[0]
                looplen = int(np.ceil(np.shape(stimavgs[iStim][idx])[0]/nloops))
                single_loop = np.zeros([looplen,
                                        stimavgs[iStim].shape[1],
                                        stimavgs[iStim].shape[2]],
                                       dtype = np.float32)
                for nloop in range(nloops):
                    single_loop += stimavgs[iStim][
                        idx[0] + nloop*looplen : idx[0] + (nloop+1)*looplen,:,:]
                single_loop /= float(nloops)
                stimavgs[iStim] = single_loop
        for iStim,savg in enumerate(stimavgs):
            fname = pjoin(parameters['datapaths']['dataserverpaths'][0],
                          parameters['datapaths']['analysispaths'],
                          expname[0],expname[1],'stimaverages_cam{0}'.format(camidx),
                          'stim{0}.tif'.format(iStim))
            if not os.path.isdir(os.path.dirname(fname)):
                os.makedirs(os.path.dirname(fname))
            from tifffile import imsave
            imsave(fname,savg)
        
        sys.exit()
if __name__ == '__main__':
    main()
