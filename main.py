import shapefile
import csv
import threading
from shptogeom import ShapeToGeom

from collections import deque
from math import *
from euclid import *
from omega import *
from cyclops import *
from omegaToolkit import *

from qtest import *


################################################################################
# ########################## Initial Setup #####################################
################################################################################

# Give a render hint to the OpenSceneGraph module (if loaded): create a depth partition at 1000. 
queueCommand(":depthpart on 1000")

screenR = getDisplayConfig().getCanvasRect()
print("screen is: " + str(screenR[2]) + "x" + str(screenR[3]))
screen = Vector2(1.0 / screenR[2], 1.0 / screenR[3])

sceneMgr = getSceneManager()
everything = SceneNode.create('everything')
cam = getDefaultCamera()
cam.setNearFarZ(0.1, 100000000)
ctrl = cam.getController()
cam.setControllerEnabled(False)
cam.setBackgroundColor(Color(0.0, 0.0, 0.0, 1.0))


################################################################################
# ############################# Utility ########################################
################################################################################

def colorLerp(vHigh, vLow, t):
        dt = 1 - t
        cv = (vHigh * t) + (vLow * dt)
        color = Color(cv.x, cv.y, cv.z, 1)
        return color

def cartToSph(v3Pos):
    lat = acos(v3Pos.y)
    lon = math.atan2(v3Pos.x, v3Pos.z)
    lat = 90 - degrees(lat)
    lon = degrees(lon)
    #print("(" + str(lat) + ", " + str(lon) + ")")
    return Vector2(lat, lon)


################################################################################
# ########################## Widget Wrpappers ##################################
################################################################################

class LabelUpdater:

        def __init__(self, label, strStatic, initVal, handleValCb=str):
                self._strStatic = strStatic
                self._label = label
                self._handleValCb = handleValCb
                self.update(initVal)

        def update(self, val):
                txt = self._strStatic + self._handleValCb(val)
                self._label.setText(txt)


class RangeSlider:

        _cb = {}

        @staticmethod
        def addUIcb(uiElement, instance):
                RangeSlider._cb[uiElement] = instance

        def setManageFunc(self, strManageFunc):
                self._container.setUIEventCommand(strManageFunc)

        def __init__(self, parent, name, getLimitsFunc, getInitValFunc, updateFunc):
                self._container = Container.create(ContainerLayout.LayoutVertical,
                                                   parent)
                label = Label.create(self._container)
                label.setFillEnabled(True)
                label.setFillColor(menuSpeColor)
                self._label = LabelUpdater(label, name + ": ", "")

                self._limits = getLimitsFunc()
                window = self._limits[1] - self._limits[0]
                self._sliderL = Slider.create(self._container)
                print(self._sliderL.getVerticalNextWidget())
                self._sliderL.setTicks(window + 1)
                self._sliderH = Slider.create(self._container)
                self._sliderH.setTicks(window + 1)

                init = getInitValFunc()
                self._sliderL.setValue(init[0] - self._limits[0])
                self._sliderH.setValue(init[1] - self._limits[0])
                self._label.update(str(init[0]) + "-" + str(init[1]))

                self._update = updateFunc


        def setPrevNextWidgets(self, prev, next):
                self._sliderL.setVerticalPrevWidget(prev)
                self._sliderH.setVerticalNextWidget(next)

        def getSliderLow(self):
                return self._sliderL

        def getSliderHigh(self):
                return self._sliderH

        def manage(self):
                v1 = self._sliderL.getValue() + self._limits[0]
                v2 = self._sliderH.getValue() + self._limits[0]

                vL = min(v1, v2)
                vH = max(v1, v2)

                self._label.update(str(vL) + "-" + str(vH))
                self._update(vL, vH)


################################################################################
# ########################## Filter Defs #######################################
################################################################################

class DefFilter:
        @classmethod
        def matches(cls, qentry):
                pass

        @classmethod
        def __str__(cls):
            return "Any"

class DefPassFilter(DefFilter):

        @classmethod
        def matches(cls, qentry):
                return True

        @classmethod
        def __str__(cls):
            return "Any"

class DefCompositeFilter(DefFilter):
        LOCATION = 0
        TIME = 1
        MAGNITUDE = 2
        _NUMENTRIES = 3

        def __init__(self,
                     locFilter=DefPassFilter(),
                     timeFilter=DefPassFilter(),
                     magFilter=DefPassFilter()):

                    self._filters = [locFilter, timeFilter, magFilter]

        @staticmethod
        def QuickByTime(timeFilter):
                return DefCompositeFilter(DefPassFilter,
                                          timeFilter,
                                          DefPassFilter)
        @staticmethod
        def QuickByLocation(locationFilter):
                return DefCompositeFilter(locationFilter)

        @staticmethod
        def QuickByMagnitude(magnitudeFilter):
                return DefCompositeFilter(DefPassFilter,
                                          DefPassFilter,
                                          magnitudeFilter)


        def matches(self, qentry):
                for filter in self._filters:
                        if not filter.matches(qentry):
                            return False
                return True

        def replace(self, idx, filter):
                newFilter = DefCompositeFilter(self._filters[0],
                                               self._filters[1],
                                               self._filters[2])
                newFilter._filters[idx] = filter
                return newFilter

        def getFilter(self, idx):
                return self._filters[idx]

class DefTimeFilter(DefFilter):

        def __init__(self, dtLow, dtHigh):
                self.dtL = dtLow
                self.dtH = dtHigh

        def matches(self, qentry):
                dt = qentry._time
                return self.dtL <= dt <= self.dtH

        def __str__(self):
            s = str(self.dtL.year) + "-" + str(self.dtH.year)
            return s

class DefLocationFilter(DefFilter):

        def __init__(self, strName, coords, prox):
                self._name = strName
                self._coords = coords
                self._proximity = prox

        def matches(self, qentry):
                dist = self._coords - qentry.Coords()
                magnitude = dist.magnitude()
                if (magnitude > 180):
                        # could be the case of (170 | 10) (close but far)
                        # need to shift so we can apply modulo arithmetic
                        coords = self._coords + Vector2(180, 360)
                        coords2 = qentry.Coords() + Vector2(180, 360)
                        coords.x = coords.x % 180
                        coords2.x = coords2.x % 180
                        coords.y = coords.y % 360
                        coords2.y = coords2.y % 360
                        dist = coords - coords2
                        magnitude = dist.magnitude()
                print(self)
                return magnitude <= self._proximity

        def __str__(self):
                s = self._name + \
                    " (" + str(self._coords.x) + ", " + str(self._coords.y) + ")" + \
                    " within " + str(self._proximity) + " degrees"
                return s

        def getCoords(self):
                return self._coords



# Locations
filterJapan = DefLocationFilter("Japan", Vector2(35, 135), 20)
filterIndonesia = DefLocationFilter("Indonesia", Vector2(0, 120), 25)
filterLatinAmerica = DefLocationFilter("Mexico & Latin America", Vector2(20, -100), 25)
filterChile = DefLocationFilter("Chile", Vector2(-33, -75), 20)
filterWestPolynesia = DefLocationFilter("West Polynesia", Vector2(-19.235, -177.935), 30)



class DefMagnitudeFilter(DefFilter):

        def __init__(self, mLow, mHigh):
                self.mL = mLow
                self.mH = mHigh

        def matches(self, qentry):
                m = qentry._magnitude
                return self.mL <= m <= self.mH

        def __str__(self):
                s = str(self.mL) + "-" + str(self.mH)
                return s


################################################################################
# ######################## Global Config Map ###################################
################################################################################

class GrandCfg:
        SCALE = 0
        ZOOM = 1
        FILTER = 2
        SHOWBYMAG = 3   # show by magnitude
        DEPTHMAX = 4
        DEPTHMIN = 5
        MAGMAX = 6
        MAGMIN = 7
        TIMEMAX = 8
        TIMEMIN = 9
        LOCATION = 10
        _valCount = 11

        # need reasonable defaults
        # some will get updated with actual values on startup
        values = [5,
                  1,
                  DefCompositeFilter(DefPassFilter(),
                                     DefTimeFilter(datetime.datetime(2010, 1, 1),
                                                   datetime.datetime(2014, 12, 31)),
                                     DefPassFilter()),
                  False,
                  500,
                  0,
                  9,
                  6,
                  datetime.datetime(2014, 12, 31),
                  datetime.datetime(2010, 1, 1),
                  Vector2(0, 0)]
        cbs = []

        @staticmethod
        def init():
                # insert blank lists for each callback category
                for idx in range(GrandCfg._valCount):
                        lstCB = []
                        GrandCfg.cbs.append(lstCB)

        @staticmethod
        def get(idx):
                return GrandCfg.values[idx]

        @staticmethod
        def set(idx, value):
                if GrandCfg.values[idx] == value:
                        return

                GrandCfg.values[idx] = value
                for cb in GrandCfg.cbs[idx]:
                        cb.update(value)

        @staticmethod
        def addCallback(idx, cb):
                GrandCfg.cbs[idx].append(cb)

GrandCfg.init()


################################################################################
# ########################## Earth Model Setup #################################
################################################################################

earthModel = ModelInfo()
earthModel.name = "earth"
earthModel.path = "MODELS/earth.fbx"
sceneMgr.loadModel(earthModel)
earthModel.generateNormals = True
earthModel.optimize = True

earth = StaticObject.create("earth")
earth.setSelectable(True)
earth.setEffect("colored")
earth.setEffect("textured -C")
earth.setPosition(0, 0.5, 2) ################# change 1 to 0
everything.addChild(earth)

def earthReset(lat, long):
        earth.resetOrientation()
        earth.yaw(radians(long))
        earth.pitch(radians(lat))
        GrandCfg.set(GrandCfg.LOCATION, Vector2(lat, long))

def earthGoTo(lat, long):
        pos = QEntry.sphToEuc(lat, long)
        earthGoToV(pos.normalized())
        GrandCfg.set(GrandCfg.LOCATION, Vector2(lat, long))

def earthGoToV(pos):
        target = earth.getPosition() + Vector3(0, 0, 1)
        target = earth.convertWorldToLocalPosition(target)
        target.normalize()
        cosAngle = pos.dot(target)
        print(cosAngle)
        angle = acos(cosAngle)
        axis = pos.cross(target)
        earth.rotate(axis.normalized(), angle, Space.Local)

def earthFixOrientation():
        target = earth.getPosition() + Vector3(0, 0, 1)
        axis = earth.convertWorldToLocalPosition(target)
        earthUp = earth.convertLocalToWorldPosition(Vector3(0, 1, 0)).normalized()
        angle = asin(earthUp.dot(Vector3(1, 0, 0)))
        earth.rotate(axis.normalized(), angle, Space.Local)

def earthWorldRoll(degAngle):
        #target = earth.getPosition() + Vector3(0, 0, 1)
        #axis = earth.convertWorldToLocalPosition(target)
        #earth.rotate(axis.normalized(), radians(degAngle), Space.Local)
        earth.rotate(Vector3(0, 0, 1), radians(degAngle), Space.World)

def earthRotate90():
        target = earth.getPosition() + Vector3(0, 1, 0)
        axis = earth.convertWorldToLocalPosition(target)
        earth.rotate(axis.normalized(), radians(90), Space.Local)


################################################################################
# ############################ World Borders ###################################
################################################################################


stg = ShapeToGeom("data/TM_WORLD_BORDERS_SIMPL/TM_WORLD_BORDERS_SIMPL.shp", \
                  "data/tst.shp")
lstBorders = stg.Borders()
thickness = 0.005

count = -1
name = "border" + str(count)
geom = ModelGeometry.create(name)
#geom.clear()
primitiveIdx = 0
cH = Vector3(115 / 255.0, 95 / 255.0, 34 / 255.0)
cL = Vector3(36 / 255.0, 33 / 255.0, 26 / 255.0)
for i in range(0, len(lstBorders), 1):
        count += 1

        border = lstBorders[i]
        color = colorLerp(cH, cL, (i % 10) * 0.1)
        size = len(border)

        for idx in range(0, size, 3):

                geom.addVertex(border[idx])
                geom.addColor(color)
                geom.addVertex(border[idx+1])
                geom.addColor(color)
                geom.addVertex(border[idx+2])
                geom.addColor(color)
                geom.addPrimitive(PrimitiveType.Triangles, primitiveIdx, 3)
                primitiveIdx += 3

sceneMgr.addModel(geom)

borders = StaticObject.create(name)
borders.setSelectable(False)
borders.getMaterial().setProgram("colored byvertex")
borders.getMaterial().setShininess(0.0)
earth.addChild(borders)



################################################################################
# ################################ Lights ######################################
################################################################################

everything.setPosition(Vector3(0, 0, 0))
cam.translate(0, -1.5, 3, Space.World)


light1 = Light.create()
light1.setColor(Color(1, 1, 1, 1))
light1.setAmbient(Color(1, 1, 1, 1))
light1.setPosition(Vector3(0, 5, 0))
light1.setEnabled(True)
sm1 = ShadowMap()
sm1.setTextureSize(2048, 2048)
light1.setShadow(sm1)
light1.setShadowRefreshMode(ShadowRefreshMode.OnLightMove)
everything.addChild(light1)


################################################################################
# ####################### Earthquake Representation ############################
################################################################################

class Bars:

        _cH = Vector3(1, 0, 0)
        _cL = Vector3(0, 1, 0)
        _qdb = None
        _models = []
        _obj = None
        _parent = None
        _scale = 10
        _name = "Geom_Bars"
        _lock = None
        _lstGeom = None
        _pollCount = 0

        class GeomModel:
                def __init__(self, geom):
                        self.timestamp = datetime.datetime.now().time()
                        self.geom = geom

                @staticmethod
                def Compare(x, y):
                        if x.timestamp < y.timestamp:
                                return - 1
                        elif x.timestamp == y.timestamp:
                                return 0
                        else:
                                return 1

        class DoBars(threading.Thread):
                # lstQEntries, scale, boolShowByMag
                def __init__(self, filter, scale, boolShowByMag):

                        super(Bars.DoBars, self).__init__()
                        self.filter = filter
                        self.scale = scale
                        self.showByMag = boolShowByMag

                def run(self):

                        query = Bars._qdb.queryByFilter(self.filter)
                        Bars._build(query, self.scale, self.showByMag)

        @staticmethod
        def init(Qdb, parent):
                Bars._qdb = Qdb
                Bars._parent = parent
                GrandCfg.addCallback(GrandCfg.SCALE, Bars)
                GrandCfg.addCallback(GrandCfg.FILTER, Bars)
                GrandCfg.addCallback(GrandCfg.SHOWBYMAG, Bars)

                Bars._lock = threading.Lock()
                Bars._lstGeom = []
                Bars._pollCount = 0

                if Bars._obj is None:
                        Bars.update(1)

        @staticmethod
        def addGeomCandidate(geomModel):
                # block
                Bars._lock.acquire(True)
                Bars._lstGeom.append(geomModel)
                Bars._lock.release()

        @staticmethod
        def _markCached(tuple):
                found = False
                for idx, model in enumerate(Bars._models):
                        if model[0] == tuple[0]:
                                # model located, update scale
                                Bars._models[idx] = tuple
                                found = True
                                break
                if not found:
                        Bars._models.append(tuple)

        @staticmethod
        def _hasModel(tuple):
                for model in Bars._models:
                        if model[0] == tuple[0] and model[1] == tuple[1]:
                                return True
                return False

        @staticmethod
        def pollInstantiate():

                Bars._pollCount += 1

                if Bars._pollCount < 100:
                        return

                if len(Bars._lstGeom) == 0:
                        return

                if not Bars._lock.acquire(False):
                        return

                Bars._pollCount = 0
                Bars._lstGeom.sort(cmp=Bars.GeomModel.Compare, reverse=True)

                geomModel = Bars._lstGeom.pop()
                Bars._lstGeom = []

                if Bars._obj is not None:
                        parent = Bars._obj.getParent()
                        parent.removeChildByRef(Bars._obj)
                        Bars._obj = None

                sceneMgr.addModel(geomModel.geom)
                Bars._obj = StaticObject.create(Bars._name)
                Bars._obj.setSelectable(False)
                Bars._obj.setCullingActive(True)
                Bars._obj.getMaterial().setProgram("colored byvertex")
                Bars._parent.addChild(Bars._obj)

                Bars._lock.release()


        @staticmethod
        def update(value):
                scale = GrandCfg.get(GrandCfg.SCALE)
                filter = GrandCfg.get(GrandCfg.FILTER)
                showByMag = GrandCfg.get(GrandCfg.SHOWBYMAG)

                # if showing by magnitude we need to influence the scaling
                # factor to normalize quantities to the highest magnitude
                # present in the dataset and further minimize the quantities for
                # proper viewing experience
                if showByMag:
                        maxmag = GrandCfg.get(GrandCfg.MAGMAX)
                        scale = float(scale) / maxmag * 0.1

                #Bars._build(filter, scale, showByMag)
                t = Bars.DoBars(filter, scale, showByMag)
                t.start()
                print("***** Returned ****")

        @staticmethod
        def _prep(filter, scale, boolShowByMag):

                query = Bars._qdb.queryByFilter(filter)
                Bars._build(query, scale, boolShowByMag)



        @staticmethod
        def _build(lstQEntries, scale, boolShowByMag):

                # if Bars._obj is not None:
                #         parent = Bars._obj.getParent()
                #         parent.removeChildByRef(Bars._obj)
                #         Bars._obj = None

                geom = ModelGeometry.create(Bars._name)
                geomModel = Bars.GeomModel(geom)

                thickness = 0.005

                t = thickness
                n = Vector3(0, 1, 0)
                mShift = GrandCfg.get(GrandCfg.MAGMIN)
                mRatio = 1.0 / (GrandCfg.get(GrandCfg.MAGMAX) - mShift)

                count = 0
                vcount = 0

                for entry in lstQEntries:

                        count += 1

                        p = entry._p.normalized()
                        axis = n.cross(p)
                        angle = acos(p.dot(n))

                        quantity = entry._depth
                        if boolShowByMag:
                            quantity = entry._magnitude

                        # prepare transformation matrix
                        m = Matrix4()
                        m.translate(p.x, p.y, p.z)
                        m.rotate_axis(angle, axis)
                        m.scale(1, quantity * scale, 1)

                        v0 = m.transform(Vector3(-t, 0, t))
                        v1 = m.transform(Vector3(-t, 1, t))
                        v2 = m.transform(Vector3(t, 0, t))
                        v3 = m.transform(Vector3(t, 1, t))
                        v4 = m.transform(Vector3(t, 0, -t))
                        v5 = m.transform(Vector3(t, 1, -t))
                        v6 = m.transform(Vector3(-t, 0, -t))
                        v7 = m.transform(Vector3(-t, 1, -t))
                        v8 = m.transform(Vector3(-t, 0, t))
                        v9 = m.transform(Vector3(-t, 1, t))

                        color = colorLerp(Bars._cH, Bars._cL, (entry._magnitude - mShift) * mRatio)

                        geom.addVertex(v0)
                        geom.addColor(color)
                        geom.addVertex(v1)
                        geom.addColor(color)
                        geom.addVertex(v6)
                        geom.addColor(color)
                        geom.addVertex(v7)
                        geom.addColor(color)
                        geom.addVertex(v4)
                        geom.addColor(color)
                        geom.addVertex(v5)
                        geom.addColor(color)
                        geom.addVertex(v2)
                        geom.addColor(color)
                        geom.addVertex(v3)
                        geom.addColor(color)
                        geom.addVertex(v0)
                        geom.addColor(color)
                        geom.addVertex(v1)
                        geom.addColor(color)
                        geom.addVertex(v7)
                        geom.addColor(color)
                        geom.addVertex(v5)
                        geom.addColor(color)
                        geom.addVertex(v3)
                        geom.addColor(color)
                        geom.addVertex(v1)
                        geom.addColor(color)

                        geom.addPrimitive(PrimitiveType.TriangleStrip, vcount, 14)
                        vcount += 14



                Bars.addGeomCandidate(geomModel)



################################################################################

qdb = QDB("data/query1950.csv")
qdb.Parse()
GrandCfg.set(GrandCfg.TIMEMAX, qdb.timeHigh)
GrandCfg.set(GrandCfg.TIMEMIN, qdb.timeLow)
GrandCfg.set(GrandCfg.DEPTHMAX, qdb.depthHigh)
GrandCfg.set(GrandCfg.DEPTHMIN, qdb.timeLow)
GrandCfg.set(GrandCfg.MAGMAX, qdb.magHigh)
GrandCfg.set(GrandCfg.MAGMIN, qdb.magLow)
Bars.init(qdb, earth)


################################################################################
# ############################       UI      ###################################
################################################################################

menuSpeColor = Color("#136624")
mm = MenuManager.createAndInitialize()
ui = UiModule.createAndInitialize()
wf = ui.getWidgetFactory()
uiRoot = ui.getUi()
#uiRoot.setLayout(ContainerLayout.LayoutHorizontal)
#uiRoot.setVerticalAlign(VAlign.AlignTop)
#uiRoot.setHorizontalAlign(HAlign.AlignCenter)

# Get the default menu (System menu)
menu = mm.getMainMenu()
adjmenu = menu.addSubMenu("Adjust")

adjmc = adjmenu.getContainer()
adjmc.setLayout(ContainerLayout.LayoutVertical)
adjmc.setHorizontalAlign(HAlign.AlignCenter)

### SCALE
lblScale = wf.createLabel("labelScale", adjmc, "")
lblScale.setFillEnabled(True)
lblScale.setFillColor(menuSpeColor)
GrandCfg.addCallback(GrandCfg.SCALE, LabelUpdater(lblScale, "Scale: ", GrandCfg.get(GrandCfg.SCALE)))
sliderScale = wf.createSlider("sliderScale", adjmc)
sliderScale.setTicks(20)
sliderScale.setValue(GrandCfg.get(GrandCfg.SCALE))
sliderScale.setUIEventCommand("onSliderScaleEvent()")



### YEAR
def getTimeLimits():
        lL = GrandCfg.get(GrandCfg.TIMEMIN).year
        lH = GrandCfg.get(GrandCfg.TIMEMAX).year
        return (lL, lH)

def getInitTime():
        filter = GrandCfg.get(GrandCfg.FILTER)
        tFilter = filter.getFilter(DefCompositeFilter.TIME)
        tL = tFilter.dtL.year
        tH = tFilter.dtH.year
        return (tL, tH)

def rsTimeUpdate(vL, vH):
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.TIME, DefTimeFilter(datetime.datetime(vL, 1, 1),
                                                                   datetime.datetime(vH, 12, 31)))
        GrandCfg.set(GrandCfg.FILTER, newf)

rsTime = RangeSlider(adjmc, "Time range", getTimeLimits, getInitTime, rsTimeUpdate)
def doRSTimeManage(): rsTime.manage()
rsTime.setManageFunc("doRSTimeManage()")



### MAGNITUDE
def getMagLimits():
        mL = GrandCfg.get(GrandCfg.MAGMIN)
        mH = GrandCfg.get(GrandCfg.MAGMAX)
        imL = int(mL)
        imH = int(mH)
        if mL > imL: imL += 1
        if mH > imH: imH += 1
        return imL, imH

def getInitMag():
        filter = GrandCfg.get(GrandCfg.FILTER)
        mFilter = filter.getFilter(DefCompositeFilter.MAGNITUDE)
        if (type(mFilter) is DefMagnitudeFilter):
                mL = mFilter.mL
                mH = mFilter.mH
                imL = int(mL)
                imH = int(mH)
                if mL > imL: imL += 1
                if mH > imH: imH += 1
                return imL, imH
        else:
                lL = GrandCfg.get(GrandCfg.MAGMIN)
                lH = GrandCfg.get(GrandCfg.MAGMAX)
                return getMagLimits()

def rsMagUpdate(vL, vH):
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.MAGNITUDE, DefMagnitudeFilter(vL, vH))
        GrandCfg.set(GrandCfg.FILTER, newf)

rsMag = RangeSlider(adjmc, "Magnitude", getMagLimits, getInitMag, rsMagUpdate)
def doRSMagManage(): rsMag.manage()
rsMag.setManageFunc("doRSMagManage()")

ckbtnShowByMag = wf.createCheckButton("Show By Magnitude", adjmc)
ckbtnShowByMag.setUIEventCommand("onCkBtnShowByMagEvent()")
ckbtnShowByMag.setChecked(GrandCfg.get(GrandCfg.SHOWBYMAG))
def onCkBtnShowByMagEvent():
        GrandCfg.set(GrandCfg.SHOWBYMAG, ckbtnShowByMag.isChecked())


rsTime.setPrevNextWidgets(sliderScale, rsMag.getSliderLow())
rsMag.setPrevNextWidgets(rsTime.getSliderHigh(), ckbtnShowByMag)
ckbtnShowByMag.setVerticalPrevWidget(rsMag.getSliderHigh())


### LOCATION
locmenu = menu.addSubMenu("Location")
locmc = locmenu.getContainer()
locmc.setLayout(ContainerLayout.LayoutVertical)
locmc.setHorizontalAlign(HAlign.AlignCenter)

## location input
def lblHandleLocation(loc):
        s = "(" + str(loc.x) + ", " + str(loc.y) + ")"
        return s

lblLoc = wf.createLabel("labelLocation", locmc, "")
lblLoc.setFillEnabled(True)
lblLoc.setFillColor(menuSpeColor)
GrandCfg.addCallback(GrandCfg.LOCATION,
                     LabelUpdater(lblLoc, "Location: ", GrandCfg.get(GrandCfg.LOCATION), lblHandleLocation))
sliderLat = wf.createSlider("sliderLat", locmc)
sliderLat.setTicks(180)
#sliderScale.setValue(GrandCfg.get(GrandCfg.SCALE))
sliderLat.setUIEventCommand("onSliderLatLonEvent()")
sliderLon = wf.createSlider("sliderLon", locmc)
sliderLon.setTicks(360)
#sliderScale.setValue(GrandCfg.get(GrandCfg.SCALE))
sliderLon.setUIEventCommand("onSliderLatLonEvent()")

### quick location
qlocmc = wf.createContainer("containerLocation", locmc, ContainerLayout.LayoutVertical)
qlblLoc = wf.createLabel("labelLocation", qlocmc, "Quick Locations:")
qlblLoc.setFillEnabled(True)
qlblLoc.setFillColor(menuSpeColor)
qlblLoc.setAutosize(True)
rbtnWorld = wf.createButton("World", qlocmc)
rbtnWorld.setRadio(True)
rbtnWorld.setUIEventCommand("onRadioWorldEvent()")
rbtnJapan = wf.createButton("Japan", qlocmc)
rbtnJapan.setRadio(True)
rbtnJapan.setUIEventCommand("onRadioJapanEvent()")
rbtnIndonesia = wf.createButton("Indonesia", qlocmc)
rbtnIndonesia.setRadio(True)
rbtnIndonesia.setUIEventCommand("onRadioIndonesiaEvent()")
rbtnChile = wf.createButton("Chile", qlocmc)
rbtnChile.setRadio(True)
rbtnChile.setUIEventCommand("onRadioChileEvent()")
rbtnLatinAmerica = wf.createButton("Mexico & Latin America", qlocmc)
rbtnLatinAmerica.setRadio(True)
rbtnLatinAmerica.setUIEventCommand("onRadioLatinAmericaEvent()")
rbtnPolynesia = wf.createButton("West Polynesia", qlocmc)
rbtnPolynesia.setRadio(True)
rbtnPolynesia.setUIEventCommand("onRadioWestPolynesiaEvent()")

rbtnWorld.setVerticalPrevWidget(sliderLon)


mibtnShowFromSide = menu.addButton("Show From the Side", "earthRotate90()")
mibtnReset = menu.addButton("Reset", "reset()")
def reset():
        earthReset(0, 0)
        earth.setScale(Vector3(1.0, 1.0, 1.0))
        GrandCfg.set(GrandCfg.ZOOM, 1)

class DoHistory(threading.Thread):
        def run(self):
                qdb.initPlayback()
                scale = GrandCfg.get(GrandCfg.SCALE)
                showByMag = GrandCfg.get((GrandCfg.SHOWBYMAG))

                lstQEntries = qdb.getNextDay()
                print(len(lstQEntries))
                while len(lstQEntries) > 0:

                        avgPos = Vector2(0, 0)
                        count = 0
                        for qentry in lstQEntries:
                                avgPos += Vector2(qentry._latitude, qentry._longitude)
                                count += 1

                        avgPos /= count

                        earthGoTo(avgPos.x, avgPos.y)

                        Bars._build(lstQEntries, scale, showByMag)

                        t = threading.currentThread()
                        cv = threading.Condition()
                        cv.acquire()
                        cv.wait(1.0)
                        cv.release()

                        lstQEntries = qdb.getNextDay()
                        print(len(lstQEntries))

def doHistoryTrampoline():

        t = DoHistory()
        t.start()
        print("Returned")



### ON_SCREEN HUD
#24588x3072
hud = wf.createContainer("HUD", uiRoot, ContainerLayout.LayoutHorizontal)
hud.setFillEnabled(True)
hud.setFillColor(Color(0.0, 0.0, 0.0, 0.85))

hudScaleZoomc = wf.createContainer("scaleZoom", hud, ContainerLayout.LayoutVertical)
hudScaleZoomc.setHorizontalAlign(HAlign.AlignLeft)
lblHudScale = wf.createLabel("displayScale", hudScaleZoomc, "Scale: ")
GrandCfg.addCallback(GrandCfg.SCALE, LabelUpdater(lblHudScale, "Scale: ", GrandCfg.get(GrandCfg.SCALE)))
lblHudZoom = wf.createLabel("displayZoom", hudScaleZoomc, "Zoom: ")
GrandCfg.addCallback(GrandCfg.ZOOM, LabelUpdater(lblHudZoom, "Zoom: ", GrandCfg.get(GrandCfg.ZOOM)))

hudFilterc = wf.createContainer("contFilter", hud, ContainerLayout.LayoutVertical)
hudFilterc.setHorizontalAlign(HAlign.AlignLeft)
lblHudLoc = wf.createLabel("lblHudLoc", hudFilterc, "Location: ")
lblHudTime = wf.createLabel("lblHudTime", hudFilterc, "Years: ")
lblHudMag = wf.createLabel("lblHudMag", hudFilterc, "Magnitude: ")

def lblHandleLocFilter(filter):
        lFilter = filter.getFilter(DefCompositeFilter.LOCATION)
        return str(lFilter)
def lblHandleTimeFilter(filter):
        tFilter = filter.getFilter(DefCompositeFilter.TIME)
        return str(tFilter)
def lblHandleMagFilter(filter):
        mFilter = filter.getFilter(DefCompositeFilter.MAGNITUDE)
        return str(mFilter)

GrandCfg.addCallback(GrandCfg.FILTER,
                     LabelUpdater(lblHudLoc, "Location: ", GrandCfg.get(GrandCfg.FILTER), lblHandleLocFilter))
GrandCfg.addCallback(GrandCfg.FILTER,
                     LabelUpdater(lblHudTime, "Years: ", GrandCfg.get(GrandCfg.FILTER), lblHandleTimeFilter))
GrandCfg.addCallback(GrandCfg.FILTER,
                     LabelUpdater(lblHudMag, "Magnitude: ", GrandCfg.get(GrandCfg.FILTER), lblHandleMagFilter))


hudCoordsc = wf.createContainer("hudCoordsc", hud, ContainerLayout.LayoutVertical)
hudCoordsc.setHorizontalAlign(HAlign.AlignLeft)
lblHudCoords = wf.createLabel("lblHudCoords", hudCoordsc, "Coords: ")
lblHudCoordsVal = wf.createLabel("lblHudCoordsVal", hudCoordsc, "")
GrandCfg.addCallback(GrandCfg.LOCATION,
                     LabelUpdater(lblHudCoordsVal, "", GrandCfg.get(GrandCfg.LOCATION), lblHandleLocation))

hud.setWidth(350)
#hud.setCenter(Vector2(screenR[2]/2.0, 300))
print(hud.getWidth())
hud.setPosition(Vector2(screenR[2]/2 - hud.getWidth()/2, 0))

def onSliderScaleEvent():
        GrandCfg.set(GrandCfg.SCALE, sliderScale.getValue() + 1)

def onSliderLatLonEvent():
        vLat = sliderLat.getValue() + 1
        vLon = sliderLon.getValue() + 1
        vLat -= 90
        vLon -= 180
        GrandCfg.set(GrandCfg.LOCATION, Vector2(vLat, vLon))
        earthGoTo(vLat, vLon)

def onRadioWorldEvent():
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.LOCATION, DefPassFilter())
        GrandCfg.set(GrandCfg.FILTER, newf)
        earthGoTo(0, 0)

def onRadioJapanEvent():
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.LOCATION, filterJapan)
        GrandCfg.set(GrandCfg.FILTER, newf)
        c = filterJapan.getCoords()
        earthGoTo(c.x, c.y)

def onRadioIndonesiaEvent():
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.LOCATION, filterIndonesia)
        GrandCfg.set(GrandCfg.FILTER, newf)
        c = filterIndonesia.getCoords()
        earthGoTo(c.x, c.y)

def onRadioLatinAmericaEvent():
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.LOCATION, filterLatinAmerica)
        GrandCfg.set(GrandCfg.FILTER, newf)
        c = filterLatinAmerica.getCoords()
        earthGoTo(c.x, c.y)

def onRadioChileEvent():
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.LOCATION, filterChile)
        GrandCfg.set(GrandCfg.FILTER, newf)
        c = filterChile.getCoords()
        earthGoTo(c.x, c.y)

def onRadioWestPolynesiaEvent():
        oldf = GrandCfg.get(GrandCfg.FILTER)
        newf = oldf.replace(DefCompositeFilter.LOCATION, filterWestPolynesia)
        GrandCfg.set(GrandCfg.FILTER, newf)
        c = filterWestPolynesia.getCoords()
        earthGoTo(c.x, c.y)


################################################################################
# ########################## Control Dispatch ##################################
################################################################################

class UniController:

        def __init__(self, node):
                self._node = node
                self._screen = Vector2()
                self._start = Vector2(0, 0);
                self._enabled = False
                self._targetDisp = Vector2(0, 0)
                self._targetZoom = 0.0
                self._targetRoll = 0.0

        def Enable(self, pos):
                self._enabled = True
                self._start.x = pos.x
                self._start.y = pos.y

        def Disable(self):
                self._enabled = False

        def Move(self, disp):

                if not self._enabled:
                        return

                # ugly filter
                uf = 0.3

                self._targetDisp = self._targetDisp * (1 - uf) + disp * uf


        def Zoom(self, s):

                self._targetZoom = s

        def Roll(self, r):
                uf = 0.8
                self._targetRoll = self._targetRoll * uf + r * (1.0 - uf)

        def Update(self, dt):

                if self._targetDisp.magnitude() > 0.0:

                        self._targetDisp *= 0.8

                        self._node.rotate(Vector3(0, 1, 0), radians(self._targetDisp.x), Space.World)
                        self._node.rotate(Vector3(1, 0, 0), radians(self._targetDisp.y), Space.World)

                        pos = self._node.getPosition() + Vector3(0, 0, 1)
                        pos = self._node.convertWorldToLocalPosition(pos)
                        pos.normalize()
                        pos = cartToSph(pos)
                        GrandCfg.set(GrandCfg.LOCATION, pos)

                if self._targetZoom != 0.0:

                        self._targetZoom *= 0.7

                        self._node.setScale(self._node.getScale() * (self._targetZoom + 1.0))
                        GrandCfg.set(GrandCfg.ZOOM, self._node.getScale().x)

                if self._targetRoll != 0.0:

                        self._targetRoll *= 0.6
                        earth.rotate(Vector3(0, 0, 1), radians(self._targetRoll), Space.World)



uctrl = UniController(earth)


################################################################################
# ######################### Main Event Handler #################################
################################################################################

screenR = getDisplayConfig().getCanvasRect()
print("screen is: " + str(screenR[2]) + "x" + str(screenR[3]))
screen = Vector2(1.0 / screenR[2], 1.0 / screenR[3])
dispStart = Vector2(0, 0)
dispTst = Vector2(0, 0)

def handleEvent():
        event = getEvent()

        # 0 on desktop
        sourceID = event.getSourceId()

        if (event.getServiceType() is ServiceType.Wand):
                # here handle wand
                if event.isButtonDown(EventFlags.Button5):
                        uctrl.Enable(event.getPosition())
                        print("Wand Btn5 down")
                if event.isButtonUp(EventFlags.Button5):
                        uctrl.Disable()
                        print("Wand Btn5 up")

                if event.isButtonDown(EventFlags.ButtonUp):
                        uctrl.Zoom(0.05)
                        print("Wand BtnUp down")
                if event.isButtonDown(EventFlags.ButtonDown):
                        uctrl.Zoom(-0.05)
                        print("Wand BtnUp down")

                if event.isButtonDown(EventFlags.ButtonLeft):
                        uctrl.Roll(-5)
                if event.isButtonDown(EventFlags.ButtonRight):
                        uctrl.Roll(5)

                analogUD = event.getAxis(1)
                analogLR = event.getAxis(0)
                if ((analogUD + analogLR) > 0.001 or (analogUD + analogLR) < -0.001):
                        disp = Vector2(analogLR, analogUD) * 3
                        if (disp.magnitude() > uctrl._targetDisp.magnitude()):
                                uctrl.Move(disp)
                        print("Wand Analog UD: " + str(disp))
        #elif (event.getServiceType() is ServiceType.Mocap):
        #        print("Wand pos: " + str(event.getOrientations()))
        #        uctrl.Move(event.getPosition())
        else:
                if event.isButtonDown(EventFlags.Left):
                        pos = event.getPosition()
                        pos.x *= screen.x
                        pos.y *= screen.y
                        uctrl.Enable(event.getPosition())
                        print("Left down")
                if event.isButtonUp(EventFlags.Left):
                        uctrl.Disable()
                        print("Left up")
                if event.getType() is EventType.Zoom:
                        zoom = event.getExtraDataInt(0)
                        s = -0.05
                        if zoom > 0: s = 0.05
                        uctrl.Zoom(s)
                
                if (event.getType() is EventType.Move):
                        pos = event.getPosition()

                        pos.x *= screen.y
                        pos.y *= screen.y
                        disp = Vector2(pos.x - dispStart.x, pos.y - dispStart.y)

                        dispStart.x = pos.x
                        dispStart.y = pos.y

                        uctrl.Move(disp * 500)

                if event.isButtonDown(EventFlags.ButtonLeft):
                        uctrl.Roll(-5)
                if event.isButtonDown(EventFlags.ButtonRight):
                        uctrl.Roll(5)



setEventFunction(handleEvent)

def onUpdate(frame, t, dt):

        uctrl.Update(dt)
        Bars.pollInstantiate()


setUpdateFunction(onUpdate)

print("********************** MADE IT *****************************************")
