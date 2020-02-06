#! /usr/bin/env python
# Classes to save files from a multiprocessing queue
import time
import sys
from multiprocessing import Process,Queue,Event,Array,Value
from ctypes import c_long, c_char_p
from datetime import datetime
import time
import sys
from .utils import display
import numpy as np
import os
from glob import glob
from os.path import join as pjoin
from tifffile import imread, TiffFile
from tifffile import TiffWriter as twriter
import pandas as pd

VERSION = '0.3'

class GenericWriter(Process):
    def __init__(self,
                 inQ = None,
                 loggerQ = None,
                 filename = pjoin('dummy','run'),
                 dataName = 'eyecam',
                 dataFolder=pjoin(os.path.expanduser('~'),'data'),
                 framesPerFile=0,
                 sleepTime = 1./30,
                 incrementRuns=True):
        Process.__init__(self)
        self.frameCount = Value(c_long,0)
        self.runs = Value('i',0)
        self.write = Event()
        self.close = Event()
        self.sleepTime = sleepTime # seconds
        self.framesPerFile = framesPerFile
        self.filename = Array('u',' ' * 1024)
        self.dataFolder = dataFolder
        self.dataName = dataName
        self.folderName = None
        self.fileName = None
        self.incrementRuns = incrementRuns
        self.runs.value = 0
        self.fd = None
        self.inQ = inQ
        self.parQ = Queue()
        self.today = datetime.today().strftime('%Y%m%d')
        self.logfile = None
        self.extension = 'nan'
        self.daemon = True

        
    def setFilename(self,filename):
        self.write.clear()
        for i in range(len(self.filename)):
            self.filename[i] = ' '
        for i in range(len(filename)):
            self.filename[i] = filename[i]
        display('Filename updated: ' + self.getFilename())
    
    def getFilename(self):
        return str(self.filename[:]).strip(' ')
        
    def stop(self):
        self.write.clear()
        self.close.set()
        self.join()
        
    def openFile(self,nfiles = None,frame = None):
        nfiles = self.nFiles
        folder = pjoin(self.dataFolder,self.dataName,self.getFilename())
        if not os.path.exists(folder):
            os.makedirs(folder)
        filename = pjoin(folder,'{0}_run{1:03d}_{2:08d}.{3}'.format(
            self.today,
            self.runs.value,
            nfiles,
            self.extension))
        if not self.fd is None:
            self.closeFile()
        self._open_file(filename,frame)
        # Create a log file
        if self.logfile is None:
            self.logfile = open(pjoin(folder,'{0}_run{1:03d}.camlog'.format(
                self.today,
                self.runs.value)),'w')
            self.logfile.write('# Camera: {0} log file'.format(
                self.dataName) + '\n')
            self.logfile.write('# Date: {0}'.format(
                datetime.today().strftime('%d-%m-%Y')) + '\n')
            self.logfile.write('# labcams version: {0}'.format(
                VERSION) + '\n')                
            self.logfile.write('# Log header:' + 'frame_id,timestamp' + '\n')
        self.nFiles += 1
        display('Opened: '+ filename)        
        self.logfile.write('# [' + datetime.today().strftime('%y-%m-%d %H:%M:%S')+'] - ' + filename + '\n')

    def _open_file(self,filename,frame):
        pass

    def _write(self,frame,frameid,timestamp):
        self.fd.save(frame,
                     compress=self.compression,
                     description='id:{0};timestamp:{1}'.format(frameid,
                                                               timestamp))

    
    def getFromQueueAndSave(self):
        buff = self.inQ.get()
        if buff[0] is None:
            # Then parameters were passed to the queue
            display('[Writer] - Received None...')
            return None,None
        if len(buff) == 1:
           # check message:
            msg = buff[0]
            if msg in ['STOP']:
                display('Stopping writer (end of queue).')
                self.write.clear()
            return None,msg
        else:
            frame,(frameid,timestamp,) = buff
            if ((self.framesPerFile == 0 and self.fd is None) or
                (self.framesPerFile > 0 and np.mod(self.frameCount.value,
                                                   self.framesPerFile)==0)):
                self.openFile(frame = frame)
                display('Queue size: {0}'.format(self.inQ.qsize()))
                self.logfile.write('# [' + datetime.today().strftime('%y-%m-%d %H:%M:%S')+'] - '
                                   + 'Queue: {0}'.format(self.inQ.qsize())
                                   + '\n')
            self._write(frame,frameid,timestamp)
            self.logfile.write('{0},{1}\n'.format(frameid,
                                                  timestamp))
            self.frameCount.value += 1
        return frameid,frame

    def run(self):
        while not self.close.is_set():
            self.frameCount.value = 0
            self.nFiles = 0
            if not self.parQ.empty():
                self.getFromParQueue()
            while self.write.is_set():
                if not self.inQ.empty():
                    frameid,frame = self.getFromQueueAndSave()
            # If queue is not empty, empty if to files.
            while not self.inQ.empty():
                frameid,frame = self.getFromQueueAndSave()
                display('Queue is empty. Proceding with close.')
            time.sleep(self.sleepTime)
            self.closeRun()
            # self.closeFile()
            # spare the processor just in case...
    
    def closeRun(self):
        if not self.logfile is None:
            self.closeFile()
            self.logfile.write('# [' +
                               datetime.today().strftime(
                                   '%y-%m-%d %H:%M:%S')+'] - ' +
                               "Wrote {0} frames on {1} ({2} files).".format(
                                   self.frameCount.value,
                                   self.dataName,
                                   self.nFiles) + '\n')
            self.logfile.close()
            self.logfile = None
            self.runs.value += 1
        if not self.frameCount.value == 0:
            display("Wrote {0} frames on {1} ({2} files).".format(
                self.frameCount.value,
                self.dataName,
                self.nFiles))
    
    def closeFile(self):
        pass

'''
        if self.trackerFlag.is_set():
            # MPTRACKER hack
            display('Running eye tracker.')
            if self.tracker is None:
                import cv2
                cv2.setNumThreads(1)
                from mptracker import MPTracker
                self.tracker = MPTracker()
                self._updateTrackerPar()
            if self.trackerfile is None:
                self.trackerfile = pjoin(folder,
                                         '{0}_run{1:03d}.eyetracker'.format(
                                             self.today,
                                             self.runs.value))
                display('[TiffWriter] Started eye tracker storing dict.')
                self._trackerres = dict(ellipsePix = [],
                                        pupilPix = [],
                                        crPix = [])
        else:
            self.tracker = None
            self._close_trackerfile()

  RUN:
                    if not frameid is None and not self.tracker is None:
                        try:
                            res = self.tracker.apply(frame)
                        except Exception as e:
                            print(e)
                            res = ((0,0),(np.nan,np.nan),
                                   (np.nan,np.nan),
                                   (np.nan,np.nan,np.nan))
                        self._storeTrackerResults(res)

    def _close_trackerfile(self):
        if not self.trackerfile is None:
            from mptracker.io import exportResultsToHDF5
            self.tracker.parameters['points'] = self.tracker.ROIpoints
            if len(self.tracker.parameters['points']) < 4:
                (x1,y1,w,h) = self.tracker.parameters['imagecropidx']
                self.tracker.parameters['points'] = [[y1+h/2,0],
                                                     [0,x1+w/2],
                                                     [y1+h/2,x1+w],
                                                     [y1+h,x1+w/2]]
            self._trackerres = dict(
                ellipsePix = np.array(self._trackerres['ellipsePix']),
                pupilPix = np.array(self._trackerres['pupilPix']),
                crPix = np.array(self._trackerres['crPix']),
                reference  = [self.tracker.parameters['points'][0],
                              self.tracker.parameters['points'][2]])
            res = exportResultsToHDF5(self.trackerfile,
                                      self.tracker.parameters,
                                      self._trackerres)
            if not res is None:
                if res:
                    display('[TiffWriter] Saving tracker results to {0}'.format(self.trackerfile))
            else:
                display('[TiffWriter] Could not save tracker results to {0}'.format(self.trackerfile))
            self._trackerres = None
            self.trackerfile = None
            
    def _updateTrackerPar(self):
        if not self.trackerpar is None and not self.tracker is None:
            print('Updating eye tracker parameters.')
            for k in self.trackerpar.keys():
                self.tracker.parameters[k] = self.trackerpar[k]
                display('\t\t {0}: {1}'.format(k,self.trackerpar[k]))
            self.tracker.setROI(self.trackerpar['points'])

    def getFromParQueue(self):
        buff = self.parQ.get()
        if buff[0] is None:
            # Then parameters were passed to the queue
            display('[TiffWriter] - Received tracker parameters.')
            self.trackerpar = buff[1]
            self._updateTrackerPar()
        
    def _storeTrackerResults(self,res):
        cr_pos,pupil_pos,pupil_radius,pupil_ellipse_par = res
        self._trackerres['ellipsePix'].append(
            np.hstack([pupil_radius,pupil_ellipse_par]))
        self._trackerres['pupilPix'].append(pupil_pos)
        self._trackerres['crPix'].append(cr_pos)

        if not self.trackerfile is None:
            try:
                self._close_trackerfile()
            except Exception as err:
                display("There was an error when trying to save the tracker results.")
                print(err)


'''

        
class TiffWriter(GenericWriter):
    def __init__(self,
                 inQ = None,
                 loggerQ = None,
                 filename = pjoin('dummy','run'),
                 dataName = 'eyecam',
                 dataFolder=pjoin(os.path.expanduser('~'),'data'),
                 framesPerFile=256,
                 sleepTime = 1./30,
                 incrementRuns=True,
                 compression=None):
        super(TiffWriter,self).__init__(inQ = inQ,
                                        loggerQ=loggerQ,
                                        filename=filename,
                                        dataName=dataName,
                                        framesPerFile=framesPerFile,
                                        sleepTime=sleepTime,
                                        incrementRuns=incrementRuns)
        self.compression = None
        if not compression is None:
            if compression > 0:
                self.compression = compression
        self.extension = 'tif'

        self.tracker = None
        self.trackerfile = None
        self.trackerFlag = Event()
        self.trackerpar = None

    def closeFile(self):
        if not self.fd is None:
            self.fd.close()
        self.fd = None

    def _open_file(self,filename,frame = None):
        self.fd = twriter(filename)

    def _write(self,frame,frameid,timestamp):
        self.fd.save(frame,
                     compress=self.compression,
                     description='id:{0};timestamp:{1}'.format(frameid,
                                                               timestamp))

################################################################################
################################################################################
################################################################################
import ffmpeg
class FFMPEGWriter(GenericWriter):
    def __init__(self,
                 inQ = None,
                 loggerQ = None,
                 filename = pjoin('dummy','run'),
                 dataName = 'eyecam',
                 dataFolder=pjoin(os.path.expanduser('~'),'data'),
                 framesPerFile=0,
                 sleepTime = 1./30,
                 frameRate = 100.,
                 incrementRuns=True,
                 compression=None):
        super(FFMPEGWriter,self).__init__(inQ = inQ,
                                          loggerQ=loggerQ,
                                          filename=filename,
                                          dataName=dataName,
                                          framesPerFile=framesPerFile,
                                          sleepTime=sleepTime,
                                          incrementRuns=incrementRuns)
        self.compression = 17
        if not compression is None:
            if compression > 0:
                self.compression = compression
        self.extension = 'avi'
        self.frame_rate = frameRate
        self.dinputs = dict(format='rawvideo',
                            pix_fmt='gray',
                            s='{}x{}')
        self.w = None
        self.h = None
        self.doutputs = dict(format='h264',
                             pix_fmt='yuv420p',#'gray',
                             vcodec='h264_qsv',#'libx264',
                             preset='veryfast',#'ultrafast',
                             threads = 1,
                             r = self.frame_rate,
                             crf=self.compression)
        
    def closeFile(self):
        if not self.fd is None:
            self.fd.stdin.close()
        self.fd = None

    def _open_file(self,filename,frame = None):
        self.w = frame.shape[1]
        self.h = frame.shape[0]
        indict = dict(**self.dinputs)
        if len(frame.shape)> 2:
            indict['pix_fmt'] = 'bgr24'
        indict['s'] = indict['s'].format(self.w,self.h)
        print(indict)
        print(self.doutputs)
        self.fd = (ffmpeg
                   .input('pipe:',**indict)
                   .output(filename,**self.doutputs)
                   .overwrite_output()
                   .run_async(pipe_stdin=True))

    def _write(self,frame,frameid,timestamp):
        self.fd.stdin.write(frame.tobytes())

################################################################################
################################################################################
################################################################################
import cv2

class OpenCVWriter(GenericWriter):
    def __init__(self,
                 inQ = None,
                 loggerQ = None,
                 filename = pjoin('dummy','run'),
                 dataName = 'eyecam',
                 dataFolder=pjoin(os.path.expanduser('~'),'data'),
                 framesPerFile=0,
                 sleepTime = 1./30,
                 incrementRuns=True,
                 compression=None,
                 frameRate = 100.,
                 fourcc = 'X264'):
        super(OpenCVWriter,self).__init__(inQ = inQ,
                                          loggerQ=loggerQ,
                                          filename=filename,
                                          dataName=dataName,
                                          framesPerFile=framesPerFile,
                                          sleepTime=sleepTime,
                                          incrementRuns=incrementRuns)
        cv2.setNumThreads(6)
        self.compression = 17
        if not compression is None:
            if compression > 0:
                self.compression = compression
        self.extension = 'avi'
        self.fourcc = cv2.VideoWriter_fourcc(*fourcc)
        self.w = None
        self.h = None
        
    def closeFile(self):
        if not self.fd is None:
            self.fd.release()
        self.fd = None

    def _open_file(self,filename,frame = None):
        self.w = frame.shape[1]
        self.h = frame.shape[0]
        self.isColor = False
        if len(frame.shape) < 2:
            self.isColor = True
        self.fd = cv2.VideoWriter(filename,
                                  cv2.CAP_FFMPEG,#cv2.CAP_DSHOW,#cv2.CAP_INTEL_MFX,
                                  self.fourcc,120,(self.w,self.h),self.isColor)

    def _write(self,frame,frameid,timestamp):
        if len(frame.shape) < 2:
            frame = cv2.cvtColor(frame,cv2.COLOR_GRAY2RGB)
        self.fd.write(frame)

        
################################################################################
################################################################################
################################################################################

class CamWriter():
    def __init__(self,
                 cam,
                 filename = pjoin('dummy','run'),
                 dataname = 'eyecam',
                 datafolder=pjoin(os.path.expanduser('~'),'data'),
                 framesperfile=0,
                 incrementruns=True):
        self.runs = 0
        self.iswriting = False
        self.framesPerFile = framesPerFile
        self.filename = filename
        self.datafolder = datafolder
        self.dataname = dataname
        self.foldername = None
        self.filename = None
        self.incrementruns = incrementruns
        self.runs = 0
        self.fd = None
        self.today = datetime.today().strftime('%Y%m%d')
        self.logfile = None
        self.extension = 'nan'
        
    def set_filename(self,filename):
        if self.iswriting:
            display('Filename changed while writing!!')
            # close file first
        self.filename = filename
        display('Filename updated: ' + self.getFilename())
    
    def get_filename(self):
        return self.filename
        
    def stop(self):
        self.iswriting = False
        
    def open_file(self,nfiles = None,frame = None):
        tstart = time.time()
        nfiles = self.nfiles
        folder = pjoin(self.datafolder,self.dataname,self.get_filename())
        if not os.path.exists(folder):
            os.makedirs(folder)
        filename = pjoin(folder,'{0}_run{1:03d}_{2:08d}.{3}'.format(
            self.today,
            self.runs,
            nfiles,
            self.extension))
        if not self.fd is None:
            self.close_file()
        self._open_file(filename,frame)
        # Create a log file
        if self.logfile is None:
            self.logfile = open(pjoin(folder,'{0}_run{1:03d}.camlog'.format(
                self.today,
                self.runs)),'w')
            self.logfile.write('# Camera: {0} log file'.format(
                self.dataName) + '\n')
            self.logfile.write('# Date: {0}'.format(
                datetime.today().strftime('%d-%m-%Y')) + '\n')
            self.logfile.write('# labcams version: {0}'.format(
                VERSION) + '\n')                
            self.logfile.write('# Log header:' + 'frame_id,timestamp' + '\n')
        self.nfiles += 1
        self.logfile.write('# [' + datetime.today().strftime('%y-%m-%d %H:%M:%S')+'] - ' + filename + '\n')
        display('Opened: '+ filename + ' in {0} s'.format(time.time()-tstart) )

    def _open_file(self,filename,frame):
        pass

    def _write(self,frame,frameid,timestamp):
        self.fd.save(frame,
                     compress=self.compression,
                     description='id:{0};timestamp:{1}'.format(frameid,
                                                               timestamp))    
    def _save(self,frame,metadata):
        if frame[0] is None:
            return None,None
        frameid,timestamp = frame
        if ((self.framesperfile == 0 and self.fd is None) or
            (self.framesperfile > 0 and np.mod(self.framecount,
                                               self.framesperfile)==0)):
            self.open_file(frame = frame)
            display('Queue size: {0}'.format(self.inQ.qsize()))
            self.logfile.write('# [' + datetime.today().strftime('%y-%m-%d %H:%M:%S')+'] - '
                               + 'Queue: {0}'.format(self.inQ.qsize())
                               + '\n')
        self._write(frame,frameid,timestamp)
        self.logfile.write('{0},{1}\n'.format(frameid,
                                              timestamp))
        self.framecount += 1
        return frameid,frame

    def close_run(self):
        if not self.logfile is None:
            self.close_file()
            self.logfile.write('# [' +
                               datetime.today().strftime(
                                   '%y-%m-%d %H:%M:%S')+'] - ' +
                               "Wrote {0} frames on {1} ({2} files).".format(
                                   self.framecount.value,
                                   self.dataname,
                                   self.nfiles) + '\n')
            self.logfile.close()
            self.logfile = None
            self.runs.value += 1
        if not self.framecount == 0:
            display("Wrote {0} frames on {1} ({2} files).".format(
                self.framecount,
                self.dataname,
                self.nfiles))
    
    def close_file(self):
        pass

class FFMPEGCamWriter(CamWriter):
    def __init__(self,
                 cam,
                 filename = pjoin('dummy','run'),
                 dataname = 'eyecam',
                 datafolder=pjoin(os.path.expanduser('~'),'data'),
                 framesperfile=0,
                 incrementruns=True,
                 crf=None):
        super(FFMPEGCamWriter,self).__init__(cam=cam,
                                             filename=filename,
                                             dataname=dataname,
                                             framesperfile=framesperfile,
                                             sleeptime=sleeptime,
                                             incrementruns=incrementruns)
        self.crf = 17
        if not crf is None:
            if crf > 0:
                self.crf = crf
        self.extension = 'avi'
        self.dinputs = dict(format='rawvideo',
                            pix_fmt='gray',
                            s='{}x{}')
        self.w = None
        self.h = None
        self.doutputs = dict(format='h264',
                             pix_fmt='yuv420p',#'gray',
                             vcodec='h264_qsv',#'libx264',
                             preset='veryfast',#'ultrafast',
                             threads = 1,
                             r = self.cam.frame_rate,
                             crf=self.compression)
        
    def close_file(self):
        if not self.fd is None:
            self.fd.stdin.close()
        self.fd = None

    def _open_file(self,filename):
        self.w = self.cam.w
        self.h = self.cam.h
        self.nchan = self.cam.nchan
        indict = dict(**self.dinputs)
        if len(self.nchan)> 2:
            indict['pix_fmt'] = 'bgr24'
        indict['s'] = indict['s'].format(self.w,self.h)
        self.fd = (ffmpeg
                   .input('pipe:',**indict)
                   .output(filename,**self.doutputs)
                   .overwrite_output()
                   .run_async(pipe_stdin=True))

    def _write(self,frame,frameid,timestamp):
        self.fd.stdin.write(frame.tobytes())

        
################################################################################
################################################################################
################################################################################

def parseCamLog(fname,convertToSeconds = True):
    logheaderkey = '# Log header:'
    comments = []
    with open(fname,'r') as fd:
        for line in fd:
            if line.startswith('#'):
                line = line.strip('\n').strip('\r')
                comments.append(line)
                if line.startswith(logheaderkey):
                    columns = line.strip(logheaderkey).strip(' ').split(',')

    logdata = pd.read_csv(fname,names = columns, 
                          delimiter=',',
                          header=None,
                          comment='#',
                          engine='c')
    if convertToSeconds and '1photon' in comments[0]:
        logdata['timestamp'] /= 10000.
    return logdata,comments


class TiffStack(object):
    def __init__(self,filenames):
        if type(filenames) is str:
            filenames = np.sort(glob(pjoin(filenames,'*.tif')))
        
        assert type(filenames) in [list,np.ndarray], 'Pass a list of filenames.'
        self.filenames = filenames
        for f in filenames:
            assert os.path.exists(f), f + ' not found.'
        # Get an estimate by opening only the first and last files
        framesPerFile = []
        self.files = []
        for i,fn in enumerate(self.filenames):
            if i == 0 or i == len(self.filenames)-1:
                self.files.append(TiffFile(fn))
            else:
                self.files.append(None)                
            f = self.files[-1]
            if i == 0:
                dims = f.series[0].shape
                self.shape = dims
            elif i == len(self.filenames)-1:
                dims = f.series[0].shape
            framesPerFile.append(np.int64(dims[0]))
        self.framesPerFile = np.array(framesPerFile, dtype=np.int64)
        self.framesOffset = np.hstack([0,np.cumsum(self.framesPerFile[:-1])])
        self.nFrames = np.sum(framesPerFile)
        self.curfile = 0
        self.curstack = self.files[self.curfile].asarray()
        N,self.h,self.w = self.curstack.shape[:3]
        self.dtype = self.curstack.dtype
        self.shape = (self.nFrames,self.shape[1],self.shape[2])
    def getFrameIndex(self,frame):
        '''Computes the frame index from multipage tiff files.'''
        fileidx = np.where(self.framesOffset <= frame)[0][-1]
        return fileidx,frame - self.framesOffset[fileidx]
    def __getitem__(self,*args):
        index  = args[0]
        if not type(index) is int:
            Z, X, Y = index
            if type(Z) is slice:
                index = range(Z.start, Z.stop, Z.step)
            else:
                index = Z
        else:
            index = [index]
        img = np.empty((len(index),self.h,self.w),dtype = self.dtype)
        for i,ind in enumerate(index):
            img[i,:,:] = self.getFrame(ind)
        return np.squeeze(img)
    def getFrame(self,frame):
        ''' Returns a single frame from the stack '''
        fileidx,frameidx = self.getFrameIndex(frame)
        if not fileidx == self.curfile:
            if self.files[fileidx] is None:
                self.files[fileidx] = TiffFile(self.filenames[fileidx])
            self.curstack = self.files[fileidx].asarray()
            self.curfile = fileidx
        return self.curstack[frameidx,:,:]
    def __len__(self):
        return self.nFrames
