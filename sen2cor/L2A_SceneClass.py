#!/usr/bin/env python
from numpy import *
from scipy.ndimage.morphology import *
from scipy.ndimage.interpolation import *
from scipy.ndimage.filters import median_filter, gaussian_filter
from lxml import objectify
from sen2cor.L2A_Library import *
from sen2cor.L2A_XmlParser import L2A_XmlParser
from multiprocessing import Lock
import pickle
import os
l = Lock()
set_printoptions(precision = 7, suppress = True)
class L2A_SceneClass(object):
    def __init__(self, config, tables):
        self._notClassified = 100
        self._notSnow = 50
        self._config = config
        self._tables = tables
        self._logger = config.logger
        self.tables.acMode = False
        x,y,n = tables.getBandSize(self.tables.B02)
        self.classificationMask = ones([x,y], uint16) * self._notClassified
        self.confidenceMaskSnow = zeros_like(tables.getBand(self.tables.B02))
        self.confidenceMaskCloud = zeros_like(tables.getBand(self.tables.B02))
        self._meanShadowDistance = 0
        self.filter =  None
        self.LOWEST = 0.000001
        self._noData = self.config.noData
        self._saturatedDefective = self.config.saturatedDefective
        self._darkFeatures = self.config.darkFeatures
        self._cloudShadows = self.config.cloudShadows
        self._vegetation = self.config.vegetation
        self._bareSoils = self.config.bareSoils
        self._water = self.config.water
        self._lowProbaClouds = self.config.lowProbaClouds
        self._medProbaClouds = self.config.medProbaClouds
        self._highProbaClouds = self.config.highProbaClouds
        self._thinCirrus = self.config.thinCirrus
        self._snowIce = self.config.snowIce
        self.logger.debug('Module L2A_SceneClass initialized')
        self._processingStatus = True
        self._sumPercentage = 0.0
    def assignClassifcation(self, arr, treshold, classification):
        cm = self.classificationMask
        cm[(arr == treshold) & (cm == self._notClassified)] = classification
        self.confidenceMaskCloud[(cm == classification)] = 0
        return
    def get_logger(self):
        return self._logger
    def set_logger(self, value):
        self._logger = value
    def del_logger(self):
        del self._logger


    def get_config(self):
        return self._config
    def get_tables(self):
        return self._tables
    def set_config(self, value):
        self._config = value
    def set_tables(self, value):
        self._tables = value
    def del_config(self):
        del self._config
    def del_tables(self):
        del self._tables
    tables = property(get_tables, set_tables, del_tables, "tables's docstring")
    config = property(get_config, set_config, del_config, "config's docstring")
    logger = property(get_logger, set_logger, del_logger, "logger's docstring")
    def preprocess(self):
        B03 = self.tables.getBand(self.tables.B03)
        B8A = self.tables.getBand(self.tables.B8A)
        self.classificationMask[(B03==0) & (B8A==0)] = self._noData
        return
    def postprocess(self):
        if(self._processingStatus == False):
            return False
        CM = self.classificationMask
        #CM[(CM == self._notClassified)] = self._saturatedDefective
        CM[(CM == self._notClassified)] = self._lowProbaClouds # modification JL20151222
        value = self.config.medianFilter
        if(value > 0):
            CM = median_filter(CM, value)
            self.logger.debug('Filtering output with level: ' + str(value))

        self.logger.debug('Storing final Classification Mask')
        self.tables.setBand(self.tables.SCL,(CM).astype(uint8))
        self.logger.debug('Storing final Snow Confidence Mask')
        self.tables.setBand(self.tables.SNW,(self.confidenceMaskSnow*100+0.5).astype(uint8))
        self.logger.debug('Storing final Cloud Confidence Mask')
        self.tables.setBand(self.tables.CLD,(self.confidenceMaskCloud*100+0.5).astype(uint8))
        try:
            pass
            # add L2A quality info on tile level:
            #self.updateQualityIndicators(1, 'T2A')
            # add L2A quality info on user level:
            #xp = L2A_XmlParser(self.config, 'DS2A')
            #ti = xp.getTree('Image_Data_Info', 'Tiles_Information')
            #nrTilesProcessed = len(ti.Tile_List.Tile)
            #self.updateQualityIndicators(nrTilesProcessed, 'UP2A')
        except:
            stdoutWrite('error in updating quality indicators\n')
            self.logger.error('error in updating quality indicators')

        GRANULE = 'GRANULE'
        L2A_TILE_ID = os.path.join(self.config.L2A_UP_DIR, GRANULE, self.config.L2A_TILE_ID)
        picFn = os.path.join(L2A_TILE_ID,'configPic.p')
        self.config.logger = None
        try:
            #f = open(picFn, 'wb')
            #pickle.dump(self.config, f, 2)
            #f.close()
            self.config.logger = self.logger
        except:
            self.config.logger = self.logger
            self.logger.fatal('cannot update configuration' % picFn)
        return
    def __exit__(self):
        sys.exit(-1)
    def __del__(self):
        self.logger.debug('Module L2A_SceneClass deleted')
    def L2A_CSND_1_1(self):
        # Step 1a: Brightness threshold on red (Band 4)
        T1_B04 = self.config.T1_B04
        T2_B04 = self.config.T2_B04
        T1_B08 = 0.04
        T2_B08 = 0.15
        T1 = 0.1 # Check influence of T1 with test B04<T1
        B04 = self.tables.getBand(self.tables.B04)
        B08 = self.tables.getBand(self.tables.B8A)
        self.confidenceMaskCloud = clip(B04, T1_B04, T2_B04)
        self.confidenceMaskCloud = ((self.confidenceMaskCloud - T1_B04)/(T2_B04-T1_B04))**2
        #JL20151217 self.confidenceMaskCloud = ((self.confidenceMaskCloud - T1_B04)/(T2_B04-T1_B04))
        CM = self.classificationMask
        CM[(B04<T1) & (B08>T1_B08) & (B08<T2_B08) & (CM==self._notClassified)] = self._darkFeatures
        self.confidenceMaskCloud[(CM == self._darkFeatures)] = 0
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 1.1'))
        return
    def L2A_CSND_1_2(self):
        # Step 1b: Normalized Difference Snow Index (NDSI)
        T1_NDSI_CLD = self.config.T1_NDSI_CLD
        T2_NDSI_CLD = self.config.T2_NDSI_CLD
        #JL20151217 f1 = self.confidenceMaskCloud > 0
        B03 = self.tables.getBand(self.tables.B03)
        B11 = self.tables.getBand(self.tables.B11)
        NDSI = (B03 - B11) / maximum((B03 + B11), self.LOWEST)
        CMC = clip(NDSI, T1_NDSI_CLD, T2_NDSI_CLD)
        CMC = ((CMC - T1_NDSI_CLD)/(T2_NDSI_CLD-T1_NDSI_CLD))
        CM = self.classificationMask
        CM[(CMC==0)] = self._notClassified
        self.confidenceMaskCloud *= CMC
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 1.2'))
        return
    def L2A_CSND_2_0(self):
        return
    def L2A_CSND_2_1(self):
        # Snow filter 1: Normalized Difference Snow Index (NDSI)
        T1_NDSI_SNW = self.config.T1_NDSI_SNW
        T2_NDSI_SNW = self.config.T2_NDSI_SNW
        B03 = self.tables.getBand(self.tables.B03)
        B11 = self.tables.getBand(self.tables.B11)
        NDSI = (B03 - B11) / maximum((B03 + B11), self.LOWEST)
        CMS = clip(NDSI, T1_NDSI_SNW, T2_NDSI_SNW)
        CMS = ((CMS - T1_NDSI_SNW)/(T2_NDSI_SNW-T1_NDSI_SNW))

        #JL20151217 snow filter applied only on potential clouds
        CMC = self.confidenceMaskCloud
        CMS[(CMC==0)] = 0 # exclude non potential cloud from snow probability
        # end JL20151217 snow filter applied only on potential clouds

        CM = self.classificationMask
        CM[(CMS == 0) & (CM == self._notClassified)] = self._notSnow
        self.confidenceMaskSnow = CMS
        return


    def L2A_CSND_2_1bis(self):
        # New threshold using Band 5 and Band 8 to limit false snow detection
        T2_SNOW_R_B05_B8A = 1.0
        B05 = self.tables.getBand(self.tables.B05)
        B8A = self.tables.getBand(self.tables.B8A)
        Ratio_B05B8A = B05 / maximum(B8A, self.LOWEST)

        # Exclude potential snow pixels satisfying the condition
        self.confidenceMaskSnow[(Ratio_B05B8A<T2_SNOW_R_B05_B8A)]= 0

        CM = self.classificationMask
        CM[(self.confidenceMaskSnow == 0) & (CM == self._notClassified)] = self._notSnow
        return
    def L2A_CSND_2_2(self):
        # Snow filter 2: Band 8 thresholds
        T1_B8A = self.config.T1_B8A
        T2_B8A = self.config.T2_B8A
        B8A = self.tables.getBand(self.tables.B8A)
        CMS = clip(B8A, T1_B8A, T2_B8A)
        CMS = ((CMS - T1_B8A) / (T2_B8A - T1_B8A))
        CM = self.classificationMask
        CM[(CMS == 0) & (CM == self._notClassified)] = self._notSnow
        self.confidenceMaskSnow *= CMS
        return
    def L2A_CSND_2_3(self):
        # Snow filter 3: Band 2 thresholds
        T1_B02 = self.config.T1_B02
        T2_B02 = self.config.T2_B02
        B02 = self.tables.getBand(self.tables.B02)
        CMS = clip(B02, T1_B02, T2_B02)
        CMS = ((CMS - T1_B02) / (T2_B02 - T1_B02))
        CM = self.classificationMask
        CM[(CMS == 0) & (CM == self._notClassified)] = self._notSnow
        self.confidenceMaskSnow *= CMS
        return
    def L2A_CSND_2_4(self):
        # Snow filter 4: Ratio Band 2 / Band 4
        T1_R_B02_B04 = self.config.T1_R_B02_B04
        T2_R_B02_B04 = self.config.T2_R_B02_B04
        B02 = self.tables.getBand(self.tables.B02)
        B04 = self.tables.getBand(self.tables.B04)
        RB02_B04 = B02 / maximum(B04,self.LOWEST)
        CMS = clip(RB02_B04, T1_R_B02_B04, T2_R_B02_B04)
        CMS = ((CMS - T1_R_B02_B04) / (T2_R_B02_B04 - T1_R_B02_B04))
        CM = self.classificationMask
        CM[(CMS == 0) & (CM == self._notClassified)] = self._notSnow
        self.confidenceMaskSnow *= CMS
        CM = self.classificationMask
        return
    def L2A_CSND_2_5(self):
        # CHECK RING ALGORITHM THAT WAS NOT IMPLEMENTED BEFORE THIS VERSION.
        # Snow filter 5: snow boundary zones
        T1_SNOW = self.config.T1_SNOW
        T2_SNOW = self.config.T2_SNOW
        B12 = self.tables.getBand(self.tables.B12)
        CM = self.classificationMask
        CMS = self.confidenceMaskSnow
        snow_mask = (CMS >T1_SNOW)
        CM[snow_mask] = self._snowIce
        # Dilatation cross-shape operator (5x5)
        struct = iterate_structure(generate_binary_structure(2,1), 3)
        snow_mask_dil = binary_dilation(snow_mask, struct)
        ring = snow_mask_dil - snow_mask
        ring_no_clouds = (ring &  (B12 < T2_SNOW))
        # important, if classified as snow, this should not become cloud:
        self.confidenceMaskCloud[ring_no_clouds | (CM == self._snowIce)] = 0
        # release the lock for the non snow classification
        CM[CM == self._notSnow] = self._notClassified
        return
    def L2A_CSND_3(self):
        # Step 3: Normalized Difference Vegetation Index (NDVI)
        T1_NDVI = self.config.T1_NDVI
        T2_NDVI = self.config.T2_NDVI
        T1_B2T = 0.15
        B02 = self.tables.getBand(self.tables.B02)
        B04 = self.tables.getBand(self.tables.B04)
        B8A = self.tables.getBand(self.tables.B8A)
        NDVI = (B8A - B04) / maximum((B8A + B04), self.LOWEST)
        CMC = clip(NDVI, T1_NDVI, T2_NDVI)
        CMC = ((CMC - T1_NDVI)/(T2_NDVI-T1_NDVI))
        CM = self.classificationMask
        CM[(CMC==1) & (CM == self._notClassified) & (B02 < T1_B2T)] = self._vegetation
        CMC[(CM== self._vegetation)] = 0
        FLT = [(CMC>0) & (CMC < 1.0)]
        CMC[FLT] = CMC[FLT] * -1 + 1
        self.confidenceMaskCloud[FLT] *= CMC[FLT]
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 3'))
        return
    def L2A_CSND_4(self):
        # Step 4: Ratio Band 8 / Band 3 for senescing vegetation
        T1_R_B8A_B03 = self.config.T1_R_B8A_B03
        T2_R_B8A_B03 = self.config.T2_R_B8A_B03
        B03 = self.tables.getBand(self.tables.B03)
        B8A = self.tables.getBand(self.tables.B8A)
        rb8b3 = B8A/maximum(B03,self.LOWEST)
        CMC = clip(rb8b3, T1_R_B8A_B03 , T2_R_B8A_B03)
        CMC = (CMC - T1_R_B8A_B03 ) / (T2_R_B8A_B03 - T1_R_B8A_B03 )
        CM = self.classificationMask
        CM[(CMC==1) & (CM == self._notClassified)] = self._vegetation
        CMC[(CM== self._vegetation)] = 0
        FLT = [(CMC>0) & (CMC < 1.0)]
        CMC[FLT] = CMC[FLT] * -1 + 1
        self.confidenceMaskCloud[FLT] *= CMC[FLT]
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 4'))
        return
    def L2A_CSND_5_1(self):
        # Step 5.1: Ratio Band 2 / Band 11 for soils
        T11_B02 = self.config.T11_B02 # -0.40
        T12_B02 = self.config.T12_B02 #  0.46
        T11_R_B02_B11 = self.config.T11_R_B02_B11 # 0.55 # 0.70
        T12_R_B02_B11 = self.config.T12_R_B02_B11 # 0.80 # 1.0
        B02 = self.tables.getBand(self.tables.B02)
        B11 = self.tables.getBand(self.tables.B11)
        R_B02_B11 = clip((B02/maximum(B11,self.LOWEST)),0,100)
        B02_FT = clip(R_B02_B11*T11_B02+T12_B02, 0.15, 0.32)
        CM = self.classificationMask
        # Correction JL20151223: condition for bare_soils is on threshold T11_R_B02_B11
        CM[(B02 < B02_FT) & (R_B02_B11 < T11_R_B02_B11) & (CM == self._notClassified)] = self._bareSoils
        self.confidenceMaskCloud[CM == self._bareSoils] = 0
        CMC = clip(R_B02_B11, T11_R_B02_B11, T12_R_B02_B11)
        CMC = ((CMC - T11_R_B02_B11)/(T12_R_B02_B11-T11_R_B02_B11))
        FLT = (R_B02_B11 > T11_R_B02_B11) & (R_B02_B11 < T12_R_B02_B11) & (B02 < B02_FT) & (CM == self._notClassified)
        self.confidenceMaskCloud[FLT] *= CMC[FLT]
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 5.1'))
        return
    def L2A_CSND_5_2(self):
        # Step 5.2: Ratio Band 2 / Band 11 for water bodies, dependent on Band 12
        T21_B12 = self.config.T21_B12 # 0.1
        T22_B12 = self.config.T22_B12 # -0.09
        T21_R_B02_B11 = self.config.T21_R_B02_B11 # 2.0
        T22_R_B02_B11 = self.config.T22_R_B02_B11 # 4.0
        T_B02 = 0.2 # modif JL water TOA reflectance shall be less than 20%
        B02 = self.tables.getBand(self.tables.B02)
        B11 = self.tables.getBand(self.tables.B11)
        B12 = self.tables.getBand(self.tables.B12)
        B8A = self.tables.getBand(self.tables.B8A) # B8A used for additional condition
        B04 = self.tables.getBand(self.tables.B04) # B04 used for additional condition
        R_B02_B11 = B02 / maximum(B11,self.LOWEST)
        B12_FT = clip(R_B02_B11*T21_B12+T22_B12, 0.07, 0.21)
        # additional condition on B8A and B04 to restrict over detection of water
        R_B02_B11_GT_T22_R_B02_B11 = where((R_B02_B11 > T22_R_B02_B11) & (B12 < B12_FT) & (B8A < B04) & (B02 < T_B02), True, False)
        CM = self.classificationMask # this is a reference, no need to reassign
        CM[(R_B02_B11_GT_T22_R_B02_B11 == True) & (CM == self._notClassified)] = self._water #self._saturatedDefective #self._water (test only)
        self.confidenceMaskCloud[CM == self._water] = 0

        # additional condition on B8A and B04 to restrict over detection of water
        R15_AMB = (R_B02_B11 < T22_R_B02_B11) & (R_B02_B11 >= T21_R_B02_B11) & (B12 < B12_FT) & (B8A < B04) & (B02 < T_B02)
        if(R15_AMB.size > 0):
            a = -1 / (T22_R_B02_B11 - T21_R_B02_B11)
            b = -T21_R_B02_B11 * a + 1
            CMC = a * R_B02_B11[R15_AMB] + b
            self.confidenceMaskCloud[R15_AMB] *= CMC

        # second part, modification for improvement of water classification:
        T_24 = 0.034
        DIFF24_AMB = B02-B04
        #CM = self.classificationMask
        F1 = (DIFF24_AMB > T_24) & (B8A < B04) & (B02 < T_B02)
        #F2 = (DIFF24_AMB > T_24) & (B8A < B04) # potential topographic shadow over snow
        CM[F1 & (CM == self._notClassified)] = self._water
        self.confidenceMaskCloud[F1 & (CM == self._water)] = 0
        #self.confidenceMaskCloud[F2 & (CM == self._notClassified)] = 0 # potential topographic shadow over snow
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 5.2'))
        return
    def L2A_CSND_6(self):
        # Step 6: Ratio Band 8 / Band 11 for rocks and sands in deserts
        T1_R_B8A_B11 = self.config.T1_R_B8A_B11 #0.90
        T2_R_B8A_B11 = self.config.T2_R_B8A_B11 #1.10
        T1_B02 = -0.25
        T2_B02 = 0.475
        T_R_B02_B11 = 0.8
        B02 = self.tables.getBand(self.tables.B02)
        B8A = self.tables.getBand(self.tables.B8A)
        B11 = self.tables.getBand(self.tables.B11)
        R_B8A_B11 = B8A/maximum(B11,self.LOWEST)
        B02_FT = clip(R_B8A_B11*T1_B02+T2_B02, 0.16, 0.35)

        CM = self.classificationMask # this is a reference, no need to reassign
        # Correction JL20151223: condition for bare_soils is on threshold T1_R_B8A_B11 and B02 < T_R_B02_B11 * B11
        CM[(B02 < B02_FT) & (R_B8A_B11 < T1_R_B8A_B11) & (B02 < T_R_B02_B11*B11) & (CM == self._notClassified)] = self._bareSoils
        self.confidenceMaskCloud[CM == self._bareSoils] = 0
        CMC = clip(R_B8A_B11, T1_R_B8A_B11, T2_R_B8A_B11)
        CMC = ((CMC - T1_R_B8A_B11)/(T2_R_B8A_B11-T1_R_B8A_B11))
        FLT = (R_B8A_B11 > T1_R_B8A_B11) & (R_B8A_B11 < T2_R_B8A_B11) & (B02 < B02_FT) & (CM == self._notClassified)
        self.confidenceMaskCloud[FLT] *= CMC[FLT]
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 6'))
        return
    def L2A_CSND_6bis(self):
        # Step 6bis: Ratio Band 4 / Band 11 do discard cloud pixels with very high ratio B4/B11
        T1_R_B04_B11 = 3.0 #self.config.T1_R_B04_B11
        T2_R_B04_B11 = 6.0 #self.config.T2_R_B04_B11
        B04 = self.tables.getBand(self.tables.B04)
        B11 = self.tables.getBand(self.tables.B11)
        rb4b11 = B04/maximum(B11,self.LOWEST)
        CMC = clip(rb4b11, T1_R_B04_B11 , T2_R_B04_B11)
        CMC = (CMC - T1_R_B04_B11 ) / (T2_R_B04_B11 - T1_R_B04_B11 )
        CM = self.classificationMask
        FLT = [(CMC>0) & (CMC < 1.0)]
        CMC[FLT] = CMC[FLT] * -1 + 1
        self.confidenceMaskCloud[(CMC==1) & (CM == self._notClassified)] = 0 # set cloud probability to 0 for CM ==1 e.g. B4/B11 > T2_R_B04_B11
        self.confidenceMaskCloud[FLT] *= CMC[FLT]
        self.logger.debug(statistics(self.confidenceMaskCloud, 'CM Cloud step 6bis'))
        return
    def L2A_CSND_7(self):
        T_CLOUD_LP = self.config.T_CLOUD_LP
        T_CLOUD_MP = self.config.T_CLOUD_MP
        T_CLOUD_HP = self.config.T_CLOUD_HP
        T1_B10 = self.config.T1_B10
        T2_B10 = self.config.T2_B10
        B02 = self.tables.getBand(self.tables.B02)
        B10 = self.tables.getBand(self.tables.B10)
        LPC = self._lowProbaClouds
        MPC = self._medProbaClouds
        HPC = self._highProbaClouds
        CIR = self._thinCirrus
        CM = self.classificationMask
        CMC = self.confidenceMaskCloud

        REFL_BLUE_MAX = 0.50
        CM[(CMC > T_CLOUD_LP) & (CMC < T_CLOUD_MP) & (CM == self._notClassified)] = LPC
        self.logger.debug(statistics(CMC[(CM == LPC)], 'CM LOW_PROBA_CLOUDS'))
        CM[(CMC >= T_CLOUD_MP) & (CMC < T_CLOUD_HP) & (CM == self._notClassified)] = MPC
        self.logger.debug(statistics(CMC[(CM == MPC)], 'CM MEDIUM_PROBA_CLOUDS'))
        CM[(CMC >= T_CLOUD_HP) & (CM == self._notClassified)] = HPC
        self.logger.debug(statistics(CMC[(CM == HPC)], 'CM HIGH_PROBA_CLOUDS'))
        # Cirrus updated + DEM condition if available:
        if (self.tables.hasBand(self.tables.DEM) == True):
            dem = self.tables.getBand(self.tables.DEM)
            T_dem = 1500 # cirrus detection is switched off above 1500m
            CM[(B10 > T1_B10) & (B10 < T2_B10) & (B02 < REFL_BLUE_MAX) & (dem < T_dem) & (CMC < T_CLOUD_MP)] = CIR
        else:
            CM[(B10 > T1_B10) & (B10 < T2_B10) & (B02 < REFL_BLUE_MAX) & (CMC < T_CLOUD_MP)] = CIR

        self.logger.debug(statistics(CMC[(CM == CIR)], 'CM THIN_CIRRUS'))
        #CM[(B10 >= T2_B10) & (CM == self._notClassified)]= MPC
        CM[(B10 >= T2_B10) & (CMC < T_CLOUD_HP)]= MPC # assign medium probability clouds class to Thick cirrus >= T2_B10
        self.logger.debug(statistics(CMC[(CM == MPC)], 'CM MEDIUM_PROBA_CLOUDS, step2'))
        return
    def L2A_SHD(self):
        csd1 = self.L2A_CSHD_1()
        csd2 = self.L2A_CSHD_2()
        CSP = (csd1 * csd2 > 0.05)
        CM = self.classificationMask

        CM[(CSP == True)] = self._cloudShadows
        return
#        if(self.tables.hasBand(self.tables.SDW)):
#            T_SDW = self.config.getFloat('Scene_Classification/Thresholds', 'T_SDW')
#            T_SDW = 0
#            shadow = self.tables.getBand(self.tables.SDW, uint8)
#            tShadow = array(shadow, float32) / 255.0
#            CM[(CM == self._darkFeatures) & (tShadow > T_SDW) & (CSP == True)] = self._cloudShadows
#            CM[(CM == self._water) & (CSP == True)] = self._cloudShadows
#        else:
#            CM[(CM == self._darkFeatures) & (CSP == True)] = self._cloudShadows
#            CM[(CM == self._water) & (CSP == True)] = self._cloudShadows
#        return


    def L2A_CSHD_2(self):
        # Part2: radiometric input:
        x,y,n = self.tables.getBandSize(2)
        BX = zeros((6,x,y), float32)
        BX[0,:,:] = self.tables.getBand(self.tables.B02)
        BX[1,:,:] = self.tables.getBand(self.tables.B03)
        BX[2,:,:] = self.tables.getBand(self.tables.B04)
        BX[3,:,:] = self.tables.getBand(self.tables.B8A)
        BX[4,:,:] = self.tables.getBand(self.tables.B11)
        BX[5,:,:] = self.tables.getBand(self.tables.B12)
        #RV_MEAN = array([0.0696000, 0.0526667, 0.0537708, 0.0752000, 0.0545000, 0.0255000], dtype=float32)
        RV_MEAN = array([0.12000, 0.08, 0.06, 0.10000, 0.0545000, 0.0255000], dtype=float32)
        # Modification JL 20160216
        distance = zeros((6,x,y), float32)
        for i in range(0,6):
            distance[i,:,:] = (BX[i,:,:] - RV_MEAN[i])
        T_B02_B12 = self.config.T_B02_B12

        msd_dark = mean(distance<0, axis=0)      # check if pixel spectrum is always under the reference shadow curve
        msd_dark = median_filter(msd_dark, 3)
        T_water = 6.0
        water = (BX[0,:,:]/BX[4,:,:])>T_water   # identify water pixels with B2/B11 > T_water

        msd = mean(abs(distance), axis=0)
        msd = median_filter(msd, 3)
        msd = 1.0 - msd
        T0 = 1.0 - T_B02_B12
        msd[msd < T0] = 0.0

        msd[msd_dark == 1.0] = 1.0    # add very dark pixel to potential cloud shadow
        msd[water == True] = 0.0      # remove water pixels with B2/B11 > T_water

        return msd
    def L2A_CSHD_1(self):
        def reverse(a): return a[::-1]
        #Part1 geometric input:
        y = self.confidenceMaskCloud.shape[0]
        x = self.confidenceMaskCloud.shape[1]
        y_aa = y*1.5 # +50% to avoid FFT aliasing
        x_aa = x*1.5 # +50% to avoid FFT aliasing

        cloud_mask = self.confidenceMaskCloud
        filt_b = zeros([y_aa,x_aa], float32)
        cloud_mask_aa = zeros([y_aa,x_aa], float32) # to avoid FFT aliasing
        #mask_shadow = zeros([y,x], float32)
        # Read azimuth and elevation solar angles
        #solar_azimuth = -int(self.config.solaz + 0.5)
        solar_azimuth = int(self.config.solaz + 0.5) # modif JL20160208 original sun azimuth value
        solar_elevation = int(90.0 - self.config.solze + 0.5)

        # Median Filter
        #cloud_mask = median_filter(cloud_mask, (7,7))
        cloud_mask = median_filter(cloud_mask, (3,3)) # modif JL20160216
        # Dilatation cross-shape operator
        shape = generate_binary_structure(2,1)
        cloud_mask = binary_dilation(cloud_mask > 0.33, shape).astype(cloud_mask.dtype)
        # Create generic cloud height distribution for 30m pixel resolution and adapt it to 20m or 60m resolution (zoom)
        resolution = self.config.resolution
        distr_clouds = concatenate([reverse(1. / (1.0 + (arange(51) / 30.0) ** (2 * 5))), 1 / (1.0 + (arange(150) / 90.0) ** (2 * 5))])
        distr_clouds = zoom(distr_clouds,30./float(resolution))
        # Create projected cloud shadow distribution
        npts_shad = distr_clouds.size / tan(solar_elevation * pi / 180.)
        factor = npts_shad/distr_clouds.size
        # SIITBX-46: to suppress unwanted user warning for zoom:
        import warnings
        warnings.filterwarnings('ignore')
        distr_shad = zoom(distr_clouds, factor)
        # Create filter for convolution (4 cases)
        filt_b[0:distr_shad.size,0] = distr_shad

        ys = float(y_aa/2.0)
        xs = float(x_aa/2.0)

        # Place into center for rotation:
        filt_b = roll(filt_b, int(ys), axis=0)
        filt_b = roll(filt_b, int(xs), axis=1)
        rot_angle = -solar_azimuth
        filt_b = rotate(filt_b, rot_angle, reshape=False, order=0)

        # case A:
        if (solar_azimuth >= 0) & (solar_azimuth < 90):
            filt_b = roll(filt_b, int(-ys), axis=0)
            filt_b = roll(filt_b, int(xs), axis=1)
        # case B:
        if (solar_azimuth >= 90) & (solar_azimuth < 180):
            filt_b = roll(filt_b, int(ys), axis=0)
            filt_b = roll(filt_b, int(xs), axis=1)

        # case C:
        if (solar_azimuth >= 180) & (solar_azimuth < 270):
            filt_b = roll(filt_b, int(ys), axis=0)
            filt_b = roll(filt_b, int(-xs), axis=1)

        # case D:
        if (solar_azimuth >= 270) & (solar_azimuth < 360):
            filt_b = roll(filt_b, int(-ys), axis=0)
            filt_b = roll(filt_b, int(-xs), axis=1)
        #Fill cloud_mask_aa with cloud_mask for the FFT computation
        cloud_mask_aa[0:y, 0:x] = copy(cloud_mask[:,:])
        # Now perform the convolution:
        fft1 = fft.rfft2(cloud_mask_aa)
        fft2 = fft.rfft2(filt_b)
        shadow_prob_aa = fft.irfft2(fft1 * fft2)
        shadow_prob = copy(shadow_prob_aa[0:y, 0:x])

        # Remove data outside of interest:
        CM = self.classificationMask
        shadow_prob[CM == self._noData] = 0
        # Normalisation:
        #shadow_prob = shadow_prob * (1.0 / maximum(shadow_prob.max(), 1.0))
        shadow_prob = clip(shadow_prob,0.0,1.0)
        # Remove cloud_mask from Shadow probability:
        shadow_prob = maximum((shadow_prob - cloud_mask), 0)
        # Gaussian smoothing of Shadow probability
        value = 3
        shadow_prob = gaussian_filter(shadow_prob, value)
        return shadow_prob
    def L2A_DarkVegetationRecovery(self):
        B04 = self.tables.getBand(self.tables.B04)
        B8A = self.tables.getBand(self.tables.B8A)
        NDVI = (B8A - B04) / maximum((B8A + B04), self.LOWEST)
        T2_NDVI = self.config.T2_NDVI
        F1 = NDVI > T2_NDVI
        CM = self.classificationMask
        CM[F1 & (CM == self._darkFeatures)] = self._vegetation
        CM[F1 & (CM == self._notClassified)] = self._vegetation
        T2_R_B8A_B03 = self.config.T2_R_B8A_B03
        B03 = self.tables.getBand(self.tables.B03)
        rb8b3 = B8A/maximum(B03,self.LOWEST)
        F2 = rb8b3 > T2_R_B8A_B03
        CM[F2 & (CM == self._darkFeatures)] = self._vegetation
        CM[F2 & (CM == self._notClassified)] = self._vegetation
        return
    def L2A_WaterPixelRecovery(self):
        # modified 2015 18 12
        # Sentinel-2 B2/B11 ratio > 4.0 and Band 8 < Band 4
        # for unclassified addtional condition: Band8 < 0.3 (F4)
        B02 = self.tables.getBand(self.tables.B02)
        B04 = self.tables.getBand(self.tables.B04)
        B8A = self.tables.getBand(self.tables.B8A)
        B11 = self.tables.getBand(self.tables.B11)
        R_B02_B11 = B02/maximum(B11,self.LOWEST)
        T3 = 4.0
        F3 = R_B02_B11 > T3
        T_B8A = 0.3
        F4 = B8A < T_B8A
        CM = self.classificationMask
        CM[F3 & (B8A < B04) & (CM == self._darkFeatures)] = self._water
        CM[F3 & (B8A < B04) & F4 & (CM == self._notClassified)] = self._water
        return

    def L2A_WaterPixelCleaningwithDEM(self):
        # modified 2015 18 12
        # clean water pixels detected in topographic shadow or teef slopes
        if (self.tables.hasBand(self.tables.DEM) == True):
            slope = self.tables.getBand(self.tables.SLP)
            shadow = self.tables.getBand(self.tables.SDW)
            T_Shadow = 128
            T_Slope = 15
            clean_area = (shadow < T_Shadow) & (slope > T_Slope)
            CM = self.classificationMask
            CM[clean_area & (CM == self._water)]= self._darkFeatures
        return

    def L2A_CloudShadowPixelCleaningwithDEM(self):
        # modified 2016 02 18
        # clean cloud shadow pixels detected in topographic shadow or teef slopes
        if (self.tables.hasBand(self.tables.DEM) == True):
            shadow = self.tables.getBand(self.tables.SDW)
            T_Shadow = 32
            clean_area = (shadow < T_Shadow) & (shadow != 0) # clean_area excludes shadow values of 0 corresponding to sea (no_data)
            CM = self.classificationMask
            CM[clean_area & (CM == self._cloudShadows)]= self._darkFeatures
        return

#    def L2A_TopographicShadowwithDEM(self):
#        # modified 2016 02 18
#        # change unclassified pixels in topographic shadow or teef slopes
#        if (self.tables.hasBand(self.tables.DEM) == True):
#            shadow = self.tables.getBand(self.tables.SDW)
#            T_Shadow = 128
#            clean_area = (shadow < T_Shadow)
#            CM = self.classificationMask
#            CM[clean_area & (CM == self._notClassified)]= self._darkFeatures
#        return

    def L2A_TopographicShadowwithDEM(self):
        # Process potential topographic shadow over snow/mountainous area
        if (self.tables.hasBand(self.tables.DEM) == True):
            # Get pixels of topographic shadows from DEM geometry
            shadow = self.tables.getBand(self.tables.SDW)
            T_Shadow = 128
            clean_area = (shadow < T_Shadow)
            CM = self.classificationMask

            # Get potential pixels of topographic shadows over snow/mountainous area from radiometry
            B02 = self.tables.getBand(self.tables.B02)
            B8A = self.tables.getBand(self.tables.B8A)
            B04 = self.tables.getBand(self.tables.B04)
            T_B02 = 0.2 # modif JL water TOA reflectance shall be less than 20%
            T_24 = 0.034
            DIFF24_AMB = B02-B04
            F2 = (DIFF24_AMB > T_24) & (B8A < B04) & (B02 > T_B02) # potential topographic shadow over snow
            # Assign darkFeatures class to pixels intersecting geometric and radiometric areas
            potential_pixels = (CM == self._notClassified) | (CM == self._lowProbaClouds) | (CM == self._medProbaClouds)
            CM[clean_area & F2 & potential_pixels] = self._darkFeatures
        return
    def L2A_SnowRecovery(self):
        B03 = self.tables.getBand(self.tables.B03)
        B11 = self.tables.getBand(self.tables.B11)
        CM = self.classificationMask
        snow_mask = (CM == self._snowIce)
        struct = iterate_structure(generate_binary_structure(2,1), 3)
        snow_mask_dil = binary_dilation(snow_mask, struct)
        CM[snow_mask_dil & (B11 < B03) & (CM == self._notClassified)] = self._snowIce
        return
    def L2A_SoilRecovery(self):
        T4 = 0.65
        T_B11 = 0.080 #T4 is too restricitve and some agricultural fields are classifiied as dark features maybe additional class could be added.
        B02 = self.tables.getBand(self.tables.B02)
        B11 = self.tables.getBand(self.tables.B11)
        R_B02_B11 = B02/maximum(B11,self.LOWEST)
        #F4 = (R_B02_B11 < T4) | (B11 > T_B11) # enlarge soil recovery to B11 > T_B11
        F4 = (R_B02_B11 < T4) # T_B11 disturbs cloud edges over water. previous line disabled.
        CM = self.classificationMask
        CM[F4 & (CM == self._darkFeatures)] = self._saturatedDefective #self._bareSoils
        #CM[(CM == self._notClassified)] = self._bareSoils # modified 2015 12 18
        return
    def average(self, oldVal, classifier, count):
        newVal = self.getClassificationPercentage(classifier)
        result = (float32(oldVal) * float32(count) + float32(newVal)) / float32(count + 1.0)
        return format('%f' % result)
    def getClassificationPercentage(self, classificator):
        cm = self.classificationMask
        if(classificator == self._noData):
            # count all for no data pixels:
            nrEntriesTotal = float32(size(cm))
            nrEntriesClassified = float32(size(cm[cm == self._noData]))
            self._sumPercentage = 0.0
        else:
            # count percentage of classified pixels:
            nrEntriesTotal = float32(size(cm[cm != self._noData]))
            nrEntriesClassified = float32(size(cm[cm == classificator]))
        fraction = nrEntriesClassified / nrEntriesTotal
        percentage = fraction * 100
        self._sumPercentage += percentage
        self.logger.debug('Classificator: %d' % classificator)
        self.logger.debug('Percentage: %f' % percentage)
        self.logger.debug('Sum Percentage: %f' % self._sumPercentage)
        if(classificator == self._noData):
            self._sumPercentage = 0.0

        percentageStr = format('%f' % percentage)
        return percentageStr
    def updateQualityIndicators(self, nrTilesProcessed, metadata):
        xp = L2A_XmlParser(self.config, metadata)
        test = True
        if metadata == 'T2A':
            icqi = xp.getTree('Quality_Indicators_Info', 'L2A_Image_Content_QI')
            if icqi == False:
                qii = xp.getRoot('Quality_Indicators_Info')
                icqi = objectify.Element('L2A_Image_Content_QI')
                test = False

            icqi.NODATA_PIXEL_PERCENTAGE = self.getClassificationPercentage(self._noData)
            icqi.SATURATED_DEFECTIVE_PIXEL_PERCENTAGE = self.getClassificationPercentage(self._saturatedDefective)
            icqi.DARK_FEATURES_PERCENTAGE = self.getClassificationPercentage(self._darkFeatures)
            icqi.CLOUD_SHADOW_PERCENTAGE = self.getClassificationPercentage(self._cloudShadows)
            icqi.VEGETATION_PERCENTAGE = self.getClassificationPercentage(self._vegetation)
            icqi.BARE_SOILS_PERCENTAGE = self.getClassificationPercentage(self._bareSoils)
            icqi.WATER_PERCENTAGE = self.getClassificationPercentage(self._water)
            icqi.LOW_PROBA_CLOUDS_PERCENTAGE = self.getClassificationPercentage(self._lowProbaClouds)
            icqi.MEDIUM_PROBA_CLOUDS_PERCENTAGE = self.getClassificationPercentage(self._medProbaClouds)
            icqi.HIGH_PROBA_CLOUDS_PERCENTAGE = self.getClassificationPercentage(self._highProbaClouds)
            icqi.THIN_CIRRUS_PERCENTAGE = self.getClassificationPercentage(self._thinCirrus)
            icqi.SNOW_ICE_PERCENTAGE = self.getClassificationPercentage(self._snowIce)
            icqi.RADIATIVE_TRANSFER_ACCURAY = 0.0
            icqi.WATER_VAPOUR_RETRIEVAL_ACCURACY = 0.0
            icqi.AOT_RETRIEVAL_ACCURACY = 0.0

            if test == False:
                qii.insert(1, icqi)

        elif metadata == 'UP2A':
            icqi = xp.getTree('L2A_Quality_Indicators_Info', 'Image_Content_QI')
            if icqi == False:
                qii = xp.getRoot('L2A_Quality_Indicators_Info')
                icqi = objectify.Element('Image_Content_QI')
                icqi.NODATA_PIXEL_PERCENTAGE = self.getClassificationPercentage(self._noData)
                icqi.SATURATED_DEFECTIVE_PIXEL_PERCENTAGE = self.getClassificationPercentage(self._saturatedDefective)
                icqi.DARK_FEATURES_PERCENTAGE = self.getClassificationPercentage(self._darkFeatures)
                icqi.CLOUD_SHADOW_PERCENTAGE = self.getClassificationPercentage(self._cloudShadows)
                icqi.VEGETATION_PERCENTAGE = self.getClassificationPercentage(self._vegetation)
                icqi.BARE_SOILS_PERCENTAGE = self.getClassificationPercentage(self._bareSoils)
                icqi.WATER_PERCENTAGE = self.getClassificationPercentage(self._water)
                icqi.LOW_PROBA_CLOUDS_PERCENTAGE = self.getClassificationPercentage(self._lowProbaClouds)
                icqi.MEDIUM_PROBA_CLOUDS_PERCENTAGE = self.getClassificationPercentage(self._medProbaClouds)
                icqi.HIGH_PROBA_CLOUDS_PERCENTAGE = self.getClassificationPercentage(self._highProbaClouds)
                icqi.THIN_CIRRUS_PERCENTAGE = self.getClassificationPercentage(self._thinCirrus)
                icqi.SNOW_ICE_PERCENTAGE = self.getClassificationPercentage(self._snowIce)
                icqi.RADIATIVE_TRANSFER_ACCURAY = 0.0
                icqi.WATER_VAPOUR_RETRIEVAL_ACCURACY = 0.0
                icqi.AOT_RETRIEVAL_ACCURACY = 0.0
                qii.append(icqi)
            else:
                icqi.NODATA_PIXEL_PERCENTAGE = self.average(icqi.NODATA_PIXEL_PERCENTAGE, self._noData, nrTilesProcessed)
                icqi.SATURATED_DEFECTIVE_PIXEL_PERCENTAGE = self.average(icqi.SATURATED_DEFECTIVE_PIXEL_PERCENTAGE, self._saturatedDefective, nrTilesProcessed)
                icqi.DARK_FEATURES_PERCENTAGE = self.average(icqi.DARK_FEATURES_PERCENTAGE, self._darkFeatures, nrTilesProcessed)
                icqi.CLOUD_SHADOW_PERCENTAGE = self.average(icqi.CLOUD_SHADOW_PERCENTAGE, self._cloudShadows, nrTilesProcessed)
                icqi.VEGETATION_PERCENTAGE = self.average(icqi.VEGETATION_PERCENTAGE, self._vegetation, nrTilesProcessed)
                icqi.BARE_SOILS_PERCENTAGE = self.average(icqi.BARE_SOILS_PERCENTAGE, self._bareSoils, nrTilesProcessed)
                icqi.WATER_PERCENTAGE = self.average(icqi.WATER_PERCENTAGE, self._water, nrTilesProcessed)
                icqi.LOW_PROBA_CLOUDS_PERCENTAGE = self.average(icqi.LOW_PROBA_CLOUDS_PERCENTAGE, self._lowProbaClouds, nrTilesProcessed)
                icqi.MEDIUM_PROBA_CLOUDS_PERCENTAGE = self.average(icqi.MEDIUM_PROBA_CLOUDS_PERCENTAGE, self._medProbaClouds, nrTilesProcessed)
                icqi.HIGH_PROBA_CLOUDS_PERCENTAGE = self.average(icqi.HIGH_PROBA_CLOUDS_PERCENTAGE, self._highProbaClouds, nrTilesProcessed)
                icqi.THIN_CIRRUS_PERCENTAGE = self.average(icqi.THIN_CIRRUS_PERCENTAGE, self._thinCirrus, nrTilesProcessed)
                icqi.SNOW_ICE_PERCENTAGE = self.average(icqi.SNOW_ICE_PERCENTAGE, self._snowIce, nrTilesProcessed)
                icqi.RADIATIVE_TRANSFER_ACCURAY = 0.0
                icqi.WATER_VAPOUR_RETRIEVAL_ACCURACY = 0.0
                icqi.AOT_RETRIEVAL_ACCURACY = 0.0
        xp.export()
    def process(self):
        #self.config.timestamp('Pre process   ')
        self.preprocess()
        #self.config.timestamp('L2A_SC init   ')
        self.L2A_CSND_1_1()
        #self.config.timestamp('L2A_CSND_1_1  ')
        self.L2A_CSND_1_2()
        #self.config.timestamp('L2A_CSND_1_2  ')
        if(self.tables.sceneCouldHaveSnow() == True):
            self.logger.debug('Snow probability from climatology, detection will be performed')
            self.L2A_CSND_2_0()
            #self.config.timestamp('L2A_CSND_2_0  ')
            self.L2A_CSND_2_1()
            #self.config.timestamp('L2A_CSND_2_1  ')
            # JL 20151217
            self.L2A_CSND_2_1bis()
            #self.config.timestamp('L2A_CSND_2_1_2')
            # JL 20151217
            self.L2A_CSND_2_2()
            #self.config.timestamp('L2A_CSND_2_2  ')
            self.L2A_CSND_2_3()
            #self.config.timestamp('L2A_CSND_2_3  ')
            self.L2A_CSND_2_4()
            #self.config.timestamp('L2A_CSND_2_4  ')
            self.L2A_CSND_2_5()
            #self.config.timestamp('L2A_CSND_2_5  ')
        else:
            self.logger.debug('No snow probability from climatology, detection will be ignored')
        self.L2A_CSND_3()
        #self.config.timestamp('L2A_CSND_3    ')
        #self.L2A_CSND_4()
        #self.config.timestamp('L2A_CSND_4    ')
        self.L2A_CSND_5_1()
        #self.config.timestamp('L2A_CSND_5_1  ')
        self.L2A_CSND_5_2()
        #self.config.timestamp('L2A_CSND_5_2  ')
        self.L2A_CSND_6()
        #self.config.timestamp('L2A_CSND_6    ')
        # JL 20160219
        self.L2A_CSND_6bis()
        #self.config.timestamp('L2A_CSND_6_2  ')
        # JL 20160219
        self.L2A_CSND_7()
        #self.config.timestamp('L2A_CSND_7    ')
        self.L2A_SHD()
        #self.config.timestamp('L2A_SHD       ')
        self.L2A_DarkVegetationRecovery()
        #self.config.timestamp('DV recovery   ')
        self.L2A_WaterPixelRecovery()
        #self.config.timestamp('WP recovery   ')
        if (self.tables.hasBand(self.tables.DEM) == True):
            self.L2A_WaterPixelCleaningwithDEM()
            #self.config.timestamp('Water Pixels cleaning with DEM')
            self.L2A_CloudShadowPixelCleaningwithDEM()
            #self.config.timestamp('Cloud Shadow Pixels cleaning with DEM')
            self.L2A_TopographicShadowwithDEM()
            #self.config.timestamp('Topographic shadows classification over snow in mountainous area with DEM')
        self.L2A_SnowRecovery()
        #self.config.timestamp('Snow recovery ')
        self.L2A_SoilRecovery()
        #self.config.timestamp('Soil recovery ')
        self.postprocess()
        #self.config.timestamp('Post process  ')
        return True

