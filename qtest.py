import csv
import math
import datetime
from euclid import *

################################################################################


################################################################################

class QEntry:

        def __init__(self, t, lat, lon, depth, mag, magType, nst, gap, dmin, rms, net, ID, updated, place, type):
                self._time = QEntry.toTime(t)
                self._latitude = float(lat)
                self._longitude = float(lon)
                self._p = QEntry.sphToEuc(self._latitude, self._longitude)
                self._depth = float(depth) / 6371   # normalize to earth radius
                self._magnitude = float(mag)
                self._magnitudeType = magType
                self._nst = nst
                self._gap = gap
                self._dmin = dmin
                self._rms = rms
                self._net = net
                self._id = ID
                self._updated = QEntry.toTime(updated)
                self._place = place
                self._type = type

        def Coords(self):
                return Vector2(self._latitude, self._longitude)


        @staticmethod
        def toTime(str):
                y = int(str[0:4])
                m = int(str[5:7])
                d = int(str[8:10])
                hr = int(str[11:13])
                min = int(str[14:16])
                sec = int(str[17:19])
                ts = datetime.datetime(y, m, d, hr, min, sec)
                return ts

        @staticmethod
        def sphToEuc(degLat, degLon):
                degLat = math.radians(degLat);
                degLon = math.radians(degLon);
                x = math.cos(degLat) * math.sin(degLon)
                y = math.sin(degLat)
                z = math.cos(degLat) * math.cos(degLon)
                point = Vector3(x, y, z)
                return point.normalized()

################################################################################

class QDB:

        timestamp = 0
        lat = 1
        lon = 2
        depth = 3
        mag = 4
        magType = 5
        nst = 6
        gap = 7
        dmin = 8
        rms = 9
        net = 10
        id = 11
        updated = 12
        place = 13
        type = 14


        def __init__(self, csvFilePath):
                self._qentries = []
                self._qsetFile = open(csvFilePath, "rb")

                # stats
                self.timeLow = datetime.datetime.now()
                self.timeHigh = datetime.datetime(1, 1, 1)
                self.depthLow = 99999
                self.depthHigh = 0
                self.magLow = 99999
                self.magHigh = 0

                # playback
                self._pos = 0
                self._date = datetime.date.today()


        def Parse(self):
                count = 0
                qreader = csv.reader(self._qsetFile)

                for r in qreader:
                        #print(r)
                        if (count == 0):
                                count = 1
                                continue

                        qentry = QEntry(r[0],
                                        r[1],
                                        r[2],
                                        r[3],
                                        r[4],
                                        r[5],
                                        r[6],
                                        r[7],
                                        r[8],
                                        r[9],
                                        r[10],
                                        r[11],
                                        r[12],
                                        r[13],
                                        r[14])

                        self._qentries.append(qentry)
                        self.updateStats(qentry)
                        count += 1


        def updateStats(self, qe):
                if qe._time < self.timeLow: self.timeLow = qe._time
                if qe._time > self.timeHigh: self.timeHigh = qe._time
                if qe._depth < self.depthLow: self.depthLow = qe._depth
                if qe._depth > self.depthHigh: self.depthHigh = qe._depth
                if qe._magnitude < self.magLow: self.magLow = qe._magnitude
                if qe._magnitude > self.magHigh: self.magHigh = qe._magnitude


        def QEntries(self):
                return self._qentries


        def queryCountry(self, strCountry):
                query = []
                for qentry in self._qentries:
                        if strCountry in qentry._place:
                                query.append(qentry)
                return query


        def queryByFilter(self, defFilter):
                query = []
                for qentry in self._qentries:
                        if defFilter.matches(qentry):
                                query.append(qentry)
                return query

        def initPlayback(self):
                self._pos = len(self._qentries) - 1
                self._date = self._qentries[self._pos]._time.date()

        def getNextDay(self):
                query = []

                while self._pos >= 0:
                        qentry = self._qentries[self._pos]

                        if self._date == qentry._time.date():
                                query.append(qentry)
                                self._pos -= 1
                        else:
                                self._date = qentry._time.date()
                                break

                return query






################################################################################


# class Bars:
# #
#         def __init__(self, qdb):
#                 self._qdb = qdb
# #
#         def Build(self, scale):
#                 #lineset = LineSet.create()
#                 thickness = 0.005
# #
#                 count = 0
#                 lstQEntries = self._qdb.QEntries()
#                 for entry in lstQEntries:
# #
#                         count += 1
# #
#                         p = entry._p.normalized()
#                         q = p * entry._magnitude * scale
#                         q += p
# #
#                         print(p)
#                         print(q)
#                         print("\n\n")
# #
#                         #line = lineset.addLine()
#                         #line.setStart(p)
#                         #line.setEnd(q)
#                         #line.setThickness(thickness)
# #
#                 #lineset.setEffect('colored -e red -C')
#                 #lineset.setPosition(Vector3(0, 0, -3))
#                 #lineset.setCullingActive(False)
#                 #return lineset
# #
# #
# ################################################################################
# #
#
# p1 = QEntry.sphToEuc(0, 0)
# p2 = QEntry.sphToEuc(0, -90)
# p3 = QEntry.sphToEuc(90, 0)
#
# qdb = QDB("data/query.csv")
# qdb.Parse()
# bars = Bars(qdb)
# bars.Build(1)


