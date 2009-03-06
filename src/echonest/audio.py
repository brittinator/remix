"""
A module for manipulating audio files and their associated Echo Nest
Analyze API analyses.

AudioData, and getpieces by Robert Ochshorn
on 2008-06-06.  Some refactoring and everything else by Joshua Lifton
2008-09-07.  Refactoring by Ben Lacker 2009-02-11.
"""

__version__ = "$Revision: 0 $"
# $Source$

import aifc
import commands
import md5
import numpy
import os
import StringIO
import struct
import tempfile
import wave
import lame
import mad
import echonest.web.analyze as analyze;

import selection


class AudioAnalysis(object) :
    """
    This class wraps echonest.web to allow transparent caching of the
    audio analysis of an audio file.

    For example, the following script will display the bars of a track
    twice:
    
        from echonest import *
        a = audio.AudioAnalysis('YOUR_TRACK_ID_HERE')
        a.bars
        a.bars

    The first time a.bars is called, a network request is made of the
    Echo Nest anaylze API.  The second time time a.bars is called, the
    cached value is returned immediately.

    An AudioAnalysis object can be created using an existing ID, as in
    the example above, or by specifying the audio file to upload in
    order to create the ID, as in:

        a = audio.AudioAnalysis(filename='FULL_PATH_TO_AUDIO_FILE')
    """

    # Any variable in this listing is fetched over the network once
    # and then cached.  Calling refreshCachedVariables will force a
    # refresh.
    CACHED_VARIABLES = ( 'bars', 
                         'beats', 
                         'duration', 
                         'end_of_fade_in', 
                         'key',
                         'loudness',
                         'metadata',
                         'mode',
                         'sections',
                         'segments',
                         'start_of_fade_out',
                         'tatums',
                         'tempo',
                         'time_signature' )

    def __init__( self, audio, parsers=None ) :
        """
        Constructor.  If the argument is a valid local path or a URL,
        the track ID is generated by uploading the file to the Echo
        Nest Analyze API.  Otherwise, the argument is assumed to be
        the track ID.

        @param audio A string representing either a path to a local
        file, a valid URL, or the ID of a file that has already been
        uploaded for analysis.

        @param parsers A dictionary of keys consisting of cached
        variable names and values consisting of functions to be used
        to parse those variables as they are cached.  No parsing is
        done for variables without parsing functions or if the parsers
        argument is None.
        """

        if parsers is None :
            parsers = {}
        self.parsers = parsers

        if type(audio) is not str :
            # Argument is invalid.
            raise TypeError("Argument 'audio' must be a string representing either a filename, track ID, or MD5.")
        elif os.path.isfile(audio) or '.' in audio :
            # Argument is either a filename or URL.
            doc = analyze.upload(audio)
            self.id = doc.getElementsByTagName('thingID')[0].firstChild.data
        else:
            # Argument is a md5 or track ID.
            self.id = audio
            

        # Initialize cached variables to None.
        for cachedVar in AudioAnalysis.CACHED_VARIABLES : 
            self.__setattr__(cachedVar, None)



    def refreshCachedVariables( self ) :
        """
        Forces all cached variables to be updated over the network.
        """
        for cachedVar in AudioAnalysis.CACHED_VARIABLES : 
            self.__setattr__(cachedVar, None)
            self.__getattribute__(cachedVar)



    def __getattribute__( self, name ) :
        """
        This function has been modified to support caching of
        variables retrieved over the network.
        """
        if name in AudioAnalysis.CACHED_VARIABLES :
            if object.__getattribute__(self, name) is None :
                getter = analyze.__dict__[ 'get_' + name ]
                value = getter(object.__getattribute__(self, 'id'))
                parseFunction = object.__getattribute__(self, 'parsers').get(name)
                if parseFunction :
                    value = parseFunction(value)
                self.__setattr__(name, value)
                if type(object.__getattribute__(self, name)) == AudioQuantumList:
                    object.__getattribute__(self, name).attach(self)
        return object.__getattribute__(self, name)





class AudioData(object):

    def __init__(self, filename=None, ndarray = None, shape=None, sampleRate=None, numChannels=None):
        
        if (filename is not None) and (ndarray is None) :
            if sampleRate is None or numChannels is None:
                #force sampleRate and num numChannels to 44100 hz, 2
                sampleRate, numChannels = 44100, 2

            if filename.endswith('.mp3'):
                mf = mad.MadFile(filename)
                buf = StringIO.StringIO()
                data = True
                while data:
                    data = mf.read()
                    if data is not None:
                        buf.write(data)
                audiodata = numpy.fromstring(buf.getvalue(),dtype=numpy.int16)
            else:
                if filename.endswith('.wav'):
                    f = wave.open(filename, 'r')
                elif filename.endswith('.aiff'):
                    f = aifc.open(filename, 'r')
                numFrames = f.getnframes()
                raw = f.readframes(numFrames)
                numChannels = f.getnchannels()
                sampleSize = numFrames*numChannels
                audiodata = numpy.array(map(int,struct.unpack("%sh" %sampleSize,raw)), numpy.int16)
                ndarray = numpy.array(audiodata, dtype=numpy.int16)
            ndarray = audiodata.reshape(len(audiodata)/numChannels,numChannels)

        # Continue with the old __init__() function 
        self.filename = filename
        self.sampleRate = sampleRate
        self.numChannels = numChannels
        
        if shape is None and isinstance(ndarray, numpy.ndarray):
            self.data = numpy.zeros(ndarray.shape, dtype=numpy.int16)
        elif shape is not None:
            self.data = numpy.zeros(shape, dtype=numpy.int16)
        else:
            self.data = None
        self.endindex = 0
        if ndarray is not None:
            self.endindex = len(ndarray)
            self.data[0:self.endindex] = ndarray



    def __getitem__(self, index):
        "returns individual frame or the entire slice as an AudioData"
        if isinstance(index, float):
            index = int(index*self.sampleRate)
        elif hasattr(index, "start") and hasattr(index, "duration"):
            index =  slice(index.start, index.start+index.duration)

        if isinstance(index, slice):
            if ( hasattr(index.start, "start") and 
                 hasattr(index.stop, "duration") and 
                 hasattr(index.stop, "start") ) :
                index = slice(index.start.start, index.stop.start+index.stop.duration)

        if isinstance(index, slice):
            return self.getslice(index)
        else:
            return self.getsample(index)



    def getslice(self, index):
        if isinstance(index.start, float):
            index = slice(int(index.start*self.sampleRate), int(index.stop*self.sampleRate), index.step)
        return AudioData(None, self.data[index],sampleRate=self.sampleRate)



    def getsample(self, index):
        if isinstance(index, int):
            return self.data[index]
        else:
            #let the numpy array interface be clever
            return AudioData(None, self.data[index])



    def __add__(self, as2):
        if self.data is None:
            return AudioData(None, as2.data.copy())
        elif as2.data is None:
            return AudioData(None, self.data.copy())
        else:
            return AudioData(None, numpy.concatenate((self.data,as2.data)))



    def append(self, as2):
        "add as2 at the endpos of this AudioData"
        self.data[self.endindex:self.endindex+len(as2)] = as2.data[0:]
        self.endindex += len(as2)



    def __len__(self):
        if self.data is not None:
            return len(self.data)
        else:
            return 0


    def encode(self, mp3_path):
            sampwidth = 2
            num_channels = self.numChannels
            if num_channels == 1:
                #if it's a mono, force it to be stereo.
                # Can be removed when py-lame implements "encode" function
                num_channels = 2
                # make a new stereo array out of the mono array 
                data_stereo = numpy.column_stack((self.data[:,numpy.newaxis],self.data[:,numpy.newaxis]))
            nframes = len(self.data) / num_channels
            raw_size = num_channels * sampwidth * nframes 
            mp3_file = open(mp3_path, "wb+")
            mp3 = lame.init() 
            mp3.set_num_channels(num_channels)
            mp3.set_in_samplerate(self.sampleRate)
            mp3.set_num_samples(long(nframes)) 
            mp3.init_parameters()
            # 1 sample = 2 bytes
            num_samples_per_enc_run = self.sampleRate
            num_bytes_per_enc_run = num_channels * num_samples_per_enc_run * sampwidth
            start = 0
            while True:
                if self.numChannels == 1:
                    #if mono use the new stereo from dual mono array
                    frames = data_stereo[start:start+num_samples_per_enc_run].tostring()
                else:
                    #if not use the stereo array
                    frames = self.data[start:start+num_samples_per_enc_run].tostring()
                data = mp3.encode_interleaved(frames)
                mp3_file.write(data)
                start = start + num_samples_per_enc_run
                if start >= len(self.data): break
            mp3_file.write(mp3.flush_buffers())
            mp3.write_tags(mp3_file)
            mp3_file.close()
            mp3.delete()



    def save(self, filename=None):
        "save sound to a wave file"

        if filename is None:
            foo,filename = tempfile.mkstemp(".wav")

        ###BASED ON SCIPY SVN (http://projects.scipy.org/pipermail/scipy-svn/2007-August/001189.html)###
        fid = open(filename, 'wb')
        fid.write('RIFF')
        fid.write('\x00\x00\x00\x00')
        fid.write('WAVE')
        # fmt chunk
        fid.write('fmt ')
        if self.data.ndim == 1:
            noc = 1
        else:
            noc = self.data.shape[1]
        bits = self.data.dtype.itemsize * 8
        sbytes = self.sampleRate*(bits / 8)*noc
        ba = noc * (bits / 8)
        fid.write(struct.pack('lhHLLHH', 16, 1, noc, self.sampleRate, sbytes, ba, bits))
        # data chunk
        fid.write('data')
        fid.write(struct.pack('l', self.data.nbytes))
        self.data.tofile(fid)
        # Determine file size and place it in correct
        #  position at start of the file. 
        size = fid.tell()
        fid.seek(4)
        fid.write(struct.pack('l', size-8))
        fid.close()

        return filename



def getpieces(audioData, segs):
    "assembles a list of segments into one AudioData"
    #calculate length of new segment
    dur = 0
    for s in segs:
        dur += int(s.duration*audioData.sampleRate)

    dur += 100000 #another two seconds just for goodwill...

    #determine shape of new array
    if len(audioData.data.shape) > 1:
        newshape = (dur, audioData.data.shape[1])
        newchans = audioData.data.shape[1]
    else:
        newshape = (dur,)
        newchans = 1

    #make accumulator segment
    newAD = AudioData(shape=newshape,sampleRate=audioData.sampleRate, numChannels=newchans)

    #concatenate segs to the new segment
    for s in segs:
        newAD.append(audioData[s])

    return newAD

def mix(audioDataA,audioDataB,mix=0.5):
    """Mixes two AudioData objects. Assumes audios have same sample rate
    and number of channels.
    Mix takes a float 0-1 and determines the relative mix of two audios.
    i.e. mix=0.9 yields greater presence of audioDataA in the final mix.
    """
    audioDataA.data *= float(mix)
    audioDataB.data *= 1-float(mix)
    if audioDataA.endindex > audioDataB.endindex:
        audioDataA.data[:audioDataB.endindex] += audioDataB.data[0:]
        return audioDataA
    elif audioDataB.endindex > audioDataA.endindex:
        audioDataB.data[:audioDataA.endindex] += audioDataA.data[0:]
        return audioDataB
    elif audioDataA.endindex == audioDataA.endindex:
        audioDataA.data[:] += audioDataB.data[:]
        return audioDataA


class AudioFile(AudioData) :
    def __init__(self, filename) :
        # BAW doesn't want to init audio for this .analysis call
        AudioData.__init__(self, filename=filename)
        self.analysis = AudioAnalysis(filename, PARSERS)



class ExistingTrack():
    def __init__(self, trackID_or_Filename):
        if(os.path.isfile(trackID_or_Filename)):
            trackID = md5.new(file(trackID_or_Filename).read()).hexdigest()
            print "Computed MD5 of file is " + trackID
        else:
            trackID = trackID_or_Filename
        self.analysis = AudioAnalysis(trackID, PARSERS)

class LocalAudioFile(AudioData):
    def __init__(self, filename):
        trackID = md5.new(file(filename).read()).hexdigest()
        print "Computed MD5 of file is " + trackID
        try:
            print "Probing for existing analysis"
            tempanalysis = AudioAnalysis(trackID, {'duration': globalParserFloat})
            tempanalysis.duration
            self.analysis = AudioAnalysis(trackID, PARSERS)
            print "Analysis found. No upload needed."
        except:
            print "Analysis not found. Uploading..."
            self.analysis = AudioAnalysis(filename, PARSERS)
        AudioData.__init__(self, filename=filename)

# Try to accomodate BAW's desire for a simpler Analysis object sans audio
#  for jingler.py
class LocalAnalysis(object):
    def __init__(self, filename):
        trackID = md5.new(file(filename).read()).hexdigest()
        print "Computed MD5 of file is " + trackID
        try:
            print "Probing for existing analysis"
            tempanalysis = AudioAnalysis(trackID, {'duration': globalParserFloat})
            tempanalysis.duration
            self.analysis = AudioAnalysis(trackID, PARSERS)
            print "Analysis found. No upload needed."
        except:
            print "Analysis not found. Uploading..."
            self.analysis = AudioAnalysis(filename, PARSERS)
        # no AudioData.__init__()

class AudioQuantum(object) :
    def __init__(self, start=0, duration=0, kind=None, confidence=None) :
        self.start = start
        self.duration = duration
        self.kind = kind
        self.confidence = confidence
    
    def parent(self):
        "containing AudioQuantum in the rhythm hierarchy"
        pars = {'tatum': 'beats',
                'beat':  'bars',
                'bar':   'sections'}
        try:
            uppers = getattr(self.container.container, pars[self.kind])
        except:
            return self
        return uppers.that(selection.overlap(self))[0]
    
    def children(self):
        "AudioQuantumList of contained AudioQuanta"
        chils = {'beat':    'tatums',
                 'bar':     'beats',
                 'section': 'bars'}
        try:
            downers = getattr(self.container.container, chils[self.kind])
        except:
            return self
        return downers.that(selection.are_contained_by(self))
    
    def group(self):
        "The parent's children: 'siblings'"
        if self.kind in ['tatum', 'beat', 'bar']:
            return self.parent().children()
        else:
            return self.container
    
    def prev(self, step=1):
        "Step backwards in AudioQuantumList"
        group = self.container
        try:
            loc = group.index(self)
            new = max(loc - step, 0)
            return group[new]
        except:
            return self
    
    def next(self, step=1):
        "Step forward in AudioQuantumList"
        group = self.container
        try:
            loc = group.index(self)
            new = min(loc + step, len(group))
            return group[new]
        except:
            return self
    
    def __str__(self):
        return "%s (%.2f - %.2f)" % (self.kind, self.start, self.start + self.duration)
    
    def __repr__(self):
        if self.confidence is not None:
            return "AudioQuantum(kind='%s', start=%f, duration=%f, confidence=%f)" % (self.kind, self.start, self.duration, self.confidence)
        else:
            return "AudioQuantum(kind='%s', start=%f, duration=%f)" % (self.kind, self.start, self.duration)
    
    def local_context(self):
        "tuple of (index, length) within rhythm siblings"
        group = self.group()
        count = len(group)
        loc  = group.index(self)
        return (loc, count,)
        
    def absolute_context(self):
        "tuple of (index, length) within whole AudioQuantumList"
        group = self.container
        count = len(group)
        loc = group.index(self)
        return (loc, count,)
    
    def context_string(self):
        "one-indexed, human-readable version of context"
        if self.kind in ['bar', 'section']:
            return "%s %i" % (self.kind, self.absolute_context()[0] + 1)
        elif self.kind in ['beat', 'tatum']:
            return "%s, %s %i of %i" % (self.parent().context_string(),
                                  self.kind, self.local_context()[0] + 1,
                                  self.local_context()[1])
        else:
            return self.__str__

class AudioSegment(AudioQuantum):
    'For those who want feature-rich segments'
    # Not sure I like the stupid number of arguments in the init 
    #  function, but it's a one-off for now.
    def __init__(self, start=0., duration=0., pitches=[], timbre=[], 
                 loudness_begin=0., loudness_max=0., time_loudness_max=0., loudness_end=None, kind='segment'):
        self.start = start
        self.duration = duration
        self.pitches = pitches
        self.timbre = timbre
        self.loudness_begin = loudness_begin
        self.loudness_max = loudness_max
        self.time_loudness_max = time_loudness_max
        if loudness_end:
            self.loudness_end = loudness_end
        self.kind = kind
        self.confidence = None

class AudioQuantumList(list):
    "container that enables content-based selection"
    def __init__(self, kind = None, container = None):
        list.__init__(self)
        self.kind = kind
        self.container = container
    
    def that(self, filt):
        out = AudioQuantumList()
        out.extend(filter(None, map(filt, self)))
        return out
    
    def attach(self, container):
        self.container = container
        for i in self:
            i.container = self



def dataParser(tag, doc) :
    out = AudioQuantumList(tag)
    nodes = doc.getElementsByTagName(tag)
    for n in nodes :
        out.append(AudioQuantum(start=float(n.firstChild.data), kind=tag,
                    confidence=float(n.getAttributeNode('confidence').value)))
    if len(out) > 1:
        for i in range(len(out) - 1) :
            out[i].duration = out[i+1].start - out[i].start
        out[-1].duration = out[-2].duration
    #else:
    #    out[0].duration = ???
    return out



def attributeParser(tag, doc) :
    out = AudioQuantumList(tag)
    nodes = doc.getElementsByTagName(tag)
    for n in nodes :
        out.append( AudioQuantum(float(n.getAttribute('start')),
                                 float(n.getAttribute('duration')),
                                 tag) )
    return out



def globalParserFloat(doc) :
    d = doc.firstChild.childNodes[4].childNodes[0]
    if d.getAttributeNode('confidence'):
        return float(d.childNodes[0].data), float(d.getAttributeNode('confidence').value)
    else:
        return float(d.childNodes[0].data)



def globalParserInt(doc) :
    d = doc.firstChild.childNodes[4].childNodes[0]
    if d.getAttributeNode('confidence'):
        return int(d.childNodes[0].data), float(d.getAttributeNode('confidence').value)
    else:
        return int(d.childNodes[0].data)



def barsParser(doc) :
    return dataParser('bar', doc)



def beatsParser(doc) :
    return dataParser('beat', doc)



def tatumsParser(doc) :
    return dataParser('tatum', doc)



def sectionsParser(doc) :
    return attributeParser('section', doc)



def segmentsParser(doc) :
    return attributeParser('segment', doc)



def metadataParser(doc) :
    out = {}
    for node in doc.firstChild.childNodes[4].childNodes:
        out[node.nodeName] = node.firstChild.data
    return out



def fullSegmentsParser(doc):
    out = AudioQuantumList('segment')
    nodes = doc.getElementsByTagName('segment')
    for n in nodes:
        start = float(n.getAttribute('start'))
        duration = float(n.getAttribute('duration'))
        
        loudnessnodes = n.getElementsByTagName('dB')
        loudness_end = None
        for l in loudnessnodes:
            if l.hasAttribute('type'):
                time_loudness_max = float(l.getAttribute('time'))
                loudness_max = float(l.firstChild.data)
            else:
                if float(l.getAttribute('time'))!=0:
                    loudness_end = float(l.firstChild.data)
                else:
                    loudness_begin = float(l.firstChild.data)

        
        pitchnodes = n.getElementsByTagName('pitch')
        pitches=[]
        for p in pitchnodes:
            pitches.append(float(p.firstChild.data))
        
        timbrenodes = n.getElementsByTagName('coeff')
        timbre=[]
        for t in timbrenodes:
            timbre.append(float(t.firstChild.data))
        
        out.append(AudioSegment(start=start, duration=duration, pitches=pitches, 
                        timbre=timbre, loudness_begin=loudness_begin, 
                        loudness_max=loudness_max, time_loudness_max=time_loudness_max, loudness_end=loudness_end ))
    return out

#
PARSERS =  { 'bars' : barsParser, 
             'beats' : beatsParser,
             'sections' : sectionsParser,
             'segments' : fullSegmentsParser,
             'tatums' : tatumsParser,
             'metadata' : metadataParser,
             'tempo' : globalParserFloat,
             'duration' : globalParserFloat,
             'loudness' : globalParserFloat,
             'end_of_fade_in' : globalParserFloat,
             'start_of_fade_out' : globalParserFloat,
             'key' : globalParserInt,
             'mode' : globalParserInt,
             'time_signature' : globalParserInt,
             }

