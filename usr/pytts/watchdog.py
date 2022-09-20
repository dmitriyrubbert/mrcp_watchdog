#! /usr/bin/env python
# -*- coding: utf-8 -*-
# Dmitriy Lazarev 2022
# Script checks speech synthesis using the umrcp protocol and restarts the TTS service if necessary

import hashlib, os, sys, threading, subprocess, time, datetime
from UniMRCP import *
sys.path.append('/usr/pytts')

SERVICE='tts'
SLEEP=10

def healthcheck():
    pitch = '100'
    volume = '100'
    rate = 100
    text = 'hello world'
    text = "<speak><prosody pitch=\""+pitch+"\" volume=\""+volume+"\">"+text+"</prosody></speak>"
    hashname = hashlib.md5(text).hexdigest()

    vars = {
      'voice': 'aleksei',
      'text': text,
      'file': hashname
    }

    dir = 'cache/' + vars['file'][0:3]
    vars['file'] = dir + '/' + vars['file']

    if not os.path.exists(dir):
        os.mkdir(dir)
    result = generateVoice(vars,rate)

    # print(subprocess.call(['file', vars['file']+'.wav']))

    if result != True:
        print(datetime.datetime.now().isoformat() + ' - Restarting tts service....')
        subprocess.call(['systemctl', 'restart', SERVICE])
        return result


def generateVoice(vars,rate):

    outfile = vars['file'] + '.pcm'
    text = vars['text'].encode('utf-8')

    logger = UniSynthLogger()

    try:
        UniMRCPClient.StaticInitialize(logger, APT_PRIO_WARNING)
    except RuntimeError as ex:
        return "Unable to initialize platform: " + ex

    try:
        client = UniMRCPClient('/usr/local/unimrcp', True)
        sess = UniSynthSession(client, 'tts')
        term = UniSynthTermination(sess, outfile)
        term.AddCapability("LPCM", SAMPLE_RATE_8000)
        sem = threading.Semaphore(0)
        chan = UniSynthChannel(sess, term, sem, text, vars['voice'])
        sem.acquire()
    except RuntimeError as ex:
        return {'error':1,'message':"An error occured: " + ex}
    except:
        return {'error':1,'message':"Unknown error occured"}

    chan = None
    sess = None
    client = None

    UniMRCPClient.StaticDeinitialize()

    subprocess.call(['rm', '-f', vars['file']+'.wav'])
    subprocess.call(['sox', '-t', 'raw', '-r', '8000', '-b', '16', '-c', '1', '-L', '-e', 'signed', outfile, vars['file']+'.wav','tempo',str(round(float(rate)/100,2))])
    
    if os.path.exists(outfile) == True:
        os.unlink(outfile)

    if os.path.getsize(vars['file']+'.wav') < 1000:
        os.unlink(vars['file']+'.wav')

    if os.path.exists(vars['file']+'.wav') == False:
        return {'error':1,'message':"Wrong parameters"}

    return True


class UniSynthLogger(UniMRCPLogger):
    def __init__(self):
        super(UniSynthLogger, self).__init__()

    # Log messages go here
    def Log(self, file, line, prio, message):
        print("  %s\n" % message)  # Ensure atomic logging, do not intermix
        return True


class UniSynthSession(UniMRCPClientSession):
    def __init__(self, client, profile):
        super(UniSynthSession, self).__init__(client, profile)

    def OnTerminate(self, status):
        print("Session terminated with code", status)
        return True

    def OnTerminateEvent(self):
        print("Session terminated unexpectedly")
        return True


class UniSynthStream(UniMRCPStreamTx):
    def __init__(self, pcmFile):
        super(UniSynthStream, self).__init__()
        # Set to True upon SPEAK's IN-PROGRESS
        self.started = False
        # Output file descriptor
        self.f = open(pcmFile, 'wb')
        # Buffer to copy audio data to
        self.buf = None

    # Called when an audio frame arrives
    def WriteFrame(self):
        if not self.started:
            return False
        frameSize = self.GetDataSize()
        if frameSize:
            if not self.buf:
                self.buf = bytearray(frameSize)
            self.GetData(self.buf)
            self.f.write(self.buf)
        return True


class UniSynthTermination(UniMRCPAudioTermination):
    def __init__(self, sess, outfile):
        super(UniSynthTermination, self).__init__(sess)
        self.stream = UniSynthStream(outfile)

    def OnStreamOpenTx(self, enabled, payload_type, name, format, channels, freq):
        # Configure outgoing stream here
        return self.stream


class UniSynthChannel(UniMRCPSynthesizerChannel):
    def __init__(self, sess, term, sem, text, voice):
        super(UniSynthChannel, self).__init__(sess, term)
        self.sess = sess
        self.term = term
        self.sem = sem
        self.text = text
        self.voice = voice
        # print(text)

    # Shorthand for graceful fail: Write message, release semaphore and return False
    def Fail(self, msg):
        global err
        print(msg)
        err = 1
        self.sem.release()
        return False

    # MRCP connection established, start communication
    def OnAdd(self, status):
        if status != MRCP_SIG_STATUS_CODE_SUCCESS:
            return self.Fail("Failed to add channel: %d" % status)
        # Start processing here
        msg = self.CreateMessage(SYNTHESIZER_SPEAK)
        msg.content_type = "application/ssml+xml"
        msg.voice_name = self.voice
        msg.SetBody(self.text)
        return msg.Send()

    # Response or event from the server arrived
    def OnMessageReceive(self, message):
        # Analyze message, update your application state and reply messages here
        if message.GetMsgType() == MRCP_MESSAGE_TYPE_RESPONSE:
            if message.GetStatusCode() != MRCP_STATUS_CODE_SUCCESS:
                return self.Fail("SPEAK request failed: %d" % message.GetStatusCode())
            if message.GetRequestState() != MRCP_REQUEST_STATE_INPROGRESS:
                return self.Fail("Failed to start SPEAK processing")
            # Start writing audio to the file
            self.term.stream.started = True
            return True  # Does not actually matter
        if message.GetMsgType() != MRCP_MESSAGE_TYPE_EVENT:
            return self.Fail("Unexpected message from the server")
        if message.GetEventID() == SYNTHESIZER_SPEAK_COMPLETE:
            # print("Speak complete:", message.completion_cause, message.completion_reason)
            self.term.stream.started = False
            self.sem.release()
            return True  # Does not actually matter
        return self.Fail("Unknown message received")

if __name__ == '__main__':

    while True:
        healthcheck()
        time.sleep(SLEEP)