#TODO: testing

import ee

class EEImageBuilder():

    def __init__(self):
        """
        A class for building and exporting multi-band images in Google Earth Engine, oriented toward the use-case of
        creating training data for machine learning models of biomass with spatial covariates. The image is exposed as a
        property (.image) of the instantiated class.
        """
        #Initialize the image with None
        self.image = None
        #Initialize connection to GEE
        ee.Initialize()

    def filtered_biomass_layer_from_raster(self, biomass_raster, filter_dict):
        """

        Parameters
        ----------
        biomass_raster: string indicating biomass dataset to use. Currently accepts 'Spawn_AGB_tCO2e'.

        filter_dict: dictionary of filters (names as keys) and parameters as the value. Parameters are themselves
        specified as key/value pairs in a dictionary. These are the filters that will be applied to create the mask for
        the result

        Options:
        'forest_non_forest':{'date_range': list of strings,
            ['YYYY-MM-DD', 'YYYY-MM-DD'] beginning and ending of date range}
        'min_forest_age':{'age': int, age in years}
        'very_low_density_rural':{'year': string, 'YYYY', year to get mask for. Allowable values 2010, 2020}
        'forest_loss':{'year': string, 'YYYY', forest loss mask will be calculated from 2000 to this year,
                       'distance': int, meters, distance to forest loss},
        'forest_gain':{'distance': int, meters, distance to forest gain},
        'roads':{'distance':int, meters, distance to roads},
        'fire':{'year':str, 'YYYY', fire mask will be calculated from 2001 to this year}

        -------

        """

        #Create the biomass layer
        if biomass_raster == 'Spawn_AGB_tCO2e':
            # Get Above Ground Biomass band and convert it to tCO2e
            biomass = ee.ImageCollection("NASA/ORNL/biomass_carbon_density/v1").first()
            biomass = biomass.select('agb').multiply(3.66).rename(biomass_raster)

        #Apply filters
        for key in filter_dict:
            if key == 'forest_non_forest':
                #Create a forest/non forest mask using the Global PALSAR-2/PALSAR Forest/Non-Forest Layer.
                dataset_forest = ee.ImageCollection('JAXA/ALOS/PALSAR/YEARLY/FNF').filterDate(
                    filter_dict[key]['date_range']).first()
                # Select the Forest/Non-Forest landcover classification band
                fnf = dataset_forest.select('fnf')
                # Select pixels = 1 (1:forest, 2:nonforest, 3:water)
                mask_forest = fnf.eq(1)
                biomass.updateMask(mask_forest)
            if key == 'min_forest_age':
                #Create a forest age mask using the forest age from
                #"Mapping global forest age from forest inventories, biomass and climate data"
                #https://essd.copernicus.org/articles/13/4881/2021/essd-13-4881-2021.pdf
                dataset_age = ee.Image("projects/es-gis-resources/assets/forestage").select([0], ['forestage'])
                # Get forests older than age
                mask_age = dataset_age.gte(filter_dict[key]['age'])
                biomass.updateMask(mask_age)
            if key == 'very_low_density_rural':
                #Create degree of urbanisation mask using the GHSL - Global Human Settlement Layer:
                #https://ghsl.jrc.ec.europa.eu/ghs_smod2022.php
                #TODO: how did we find and decide to use this?
                year = filter_dict[key]['year']
                dataset_urbanisation = ee.Image(
                    f'projects/ee-mmf-mature-forest-biomass/assets/GHS_SMOD_E{year}_GLOBE_R2022A_54009_1000_V1_0')
                #Mask to pixels belonging to very low density rural grid cells (11)
                mask_urbanisation_degree = dataset_urbanisation.eq(11)
                biomass.updateMask(mask_urbanisation_degree)
            if key == 'forest_loss':
                #Create Forest loss proximity mask using the Hansen Global Forest Change v1.9 (2000-2021)
                #TODO: Review code
                dataset_hansen_loss = ee.Image('UMD/hansen/global_forest_change_2021_v1_9').select('lossyear')
                # Distance from forest loss from before {year}
                year = filter_dict[key]['year']
                distance = filter_dict[key]['distance']
                distance_forest_loss = dataset_hansen_loss.lte(int(year[-2] + year[-1])).distance(
                    ee.Kernel.euclidean(distance, 'meters'))
                mask_forest_loss_proximity = distance_forest_loss.mask().eq(0)
                biomass.updateMask(mask_forest_loss_proximity)
            if key == 'forest_gain':
                #Create Forest gain proximity mask using the Hansen Global Forest Change v1.9 (2000-2021)
                # TODO: Review code
                dataset_hansen_gain = ee.Image('UMD/hansen/global_forest_change_2021_v1_9').select('gain')
                # Distance from forest gain
                distance = filter_dict[key]['distance']
                distance_forest_gain = dataset_hansen_gain.distance(
                    ee.Kernel.euclidean(distance, 'meters'))
                mask_forest_gain_proximity = distance_forest_gain.mask().eq(0)
                biomass.updateMask(mask_forest_gain_proximity)
            if key == 'roads':
                #Create roads proximity mask using the Global Roads Open Access Data Set (gROADS),
                #v1 (1980–2010) dataset
                # TODO: Review code
                dataset_roads = ee.FeatureCollection('projects/ee-mmf-mature-forest-biomass/assets/gROADSv1')
                distance = filter_dict[key]['distance']
                distance_roads = dataset_roads.distance(ee.Number(distance))
                mask_roads_proximity = distance_roads.mask().eq(0)
                biomass.updateMask(mask_roads_proximity)
            if key == 'fire':
                #Create past fires mask using FireCCI51: MODIS Fire_cci Burned Area Pixel Product, Version 5.1
                # TODO: Review code and overall approach
                year = filter_dict[key]['year']
                dataset = ee.ImageCollection('ESA/CCI/FireCCI/5_1').filterDate('2001-01-01', f'{year}-12-31')
                burnedArea = dataset.select('BurnDate')
                maxBA = burnedArea.max()
                mask_past_fires = maxBA.mask().eq(0)
                biomass.updateMask(mask_past_fires)

        #Create the image from this, or add to it if it's there already
        if self.image is None:
            self.image = biomass
        else:
            self.image.addBands(biomass)

    def spatial_covariates(self, covariates):
        """
        Uses an appropriate earth engine asset to add spatial covariate bands to the image

        Parameters
        ----------
        covariates: list of strings, taken from ['ecoregion', 'terraclimate', 'soilgrids', 'bioclim',
        'terrain']

        -------

        """
        #TODO: Update mask once at the end on the whole stack of bands (does this actually need done? If image already
        # created, the mask should be too right? Do a test, count pixels of image)

        # If the biomass image isn't already created, make an empty image
        if self.image is None:
            self.image = ee.Image()

        for covariate in covariates:
            if covariate == 'ecoregion':
                ecoregion_dataset = ee.FeatureCollection("RESOLVE/ECOREGIONS/2017")
                # Use the BIOME_NUM band, convert from double to int to potentially use with stratified sampling
                # The paint function paints the geometries of a collection onto an image.
                ecoregion_image = ee.Image().int().paint(ecoregion_dataset, "BIOME_NUM").rename('BIOME_NUM')
                self.image = self.image.addBands(ecoregion_image)
            if covariate == 'terraclimate':
                # Using 1960 to 1991 to match with BioClim.
                terraclimate_dataset = ee.ImageCollection('IDAHO_EPSCOR/TERRACLIMATE').filter(
                    ee.Filter.date('1960-01-01', '1991-01-01'))
                #Take the mean of these monthly data over this time period (retains all bands of image apparently)
                terraclimate_mean = terraclimate_dataset.reduce(ee.Reducer.mean())
                #Add all bands to output
                self.image = self.image.addBands(terraclimate_mean)
            if covariate == 'soilgrids':
                #TODO: use new data
                0
            if covariate == 'bioclim':
                bioclim_image = ee.Image('WORLDCLIM/V1/BIO')
                self.image = self.image.addBands(bioclim_image)
            if covariate == 'terrain':
                terrain_bands = ['elevation', 'aspect', 'slope', 'hillshade']
                # Updated to use SRTM
                terrain_image = ee.Terrain.products(ee.Image('CGIAR/SRTM90_V4')).select(terrain_bands)
                self.image = self.image.addBands(terrain_image)

    def training_sets(self, polygon_list, buffer):
        #TODO; given a list of polygons specifying test sets, add one band per polygon that has 0s within the polygon
        # and buffer and ones elsewhere
        0

    def tile_and_csv_export(self):
        #TODO
        0


################################
#TODO: Anika I think we can incorporate all the below functionality into the above. For example the above code
# can produce a filtered biomass image, and with some additional methods it can be reduced to percentiles within a
# buffer of the same ecoregion

# Need to add Walker as a data source above
################################

def mature_biomass_spawn(lat, lng, buffer=20):
    """
    Get mature biomass (ymax) in tCO2e/ha including aboveground and belowground biomass from Spawn et al. (2020)

    Parameters
    ---------
    lat : [float]
          latitude in decimal degrees for project location
    lng : [float]
          longitude in decimal degrees for project location
    buffer : [float]
             distance in km over which to search for mature biomass (default = 20 km)

    Returns
    -------
    mature biomass in tCO2e/ha including aboveground and belowground biomass
    """

    # get max from carbon density GEE -----------------
    pt = ee.Geometry.Point(lng, lat)  # x,y
    buffered_pt = pt.buffer(distance=buffer * 1000)
    biomass_image = ee.ImageCollection("NASA/ORNL/biomass_carbon_density/v1").first()

    # if want to swap out geojson shapefile instead of point
    # aoi = ee.FeatureCollection(geojson['features']) #function input should be geojson instead of lat, lng
    # bounds = ee.Geometry(aoi.geometry(maxError=100))
    # buffered_pt = bounds.buffer(distance=buffer*1000, maxError=1000) #distance=20000

    agb_image = biomass_image.select('agb')

    # Take the maximum AGB in a radius of 20km
    sample_agb = agb_image.reduceRegion(
        geometry=buffered_pt,
        reducer=ee.Reducer.max(),
        scale=300)

    bgb_image = biomass_image.select('bgb')

    # Take the maximum AGB in a radius of 20km
    sample_bgb = bgb_image.reduceRegion(
        geometry=buffered_pt,
        reducer=ee.Reducer.max(),
        scale=300)

    data_dict_agb = sample_agb.getInfo()  # gets tC/ha
    data_dict_bgb = sample_bgb.getInfo()  # gets tC/ha

    y_max_agb = data_dict_agb['agb'] * c_to_co2
    y_max_bgb = data_dict_bgb['bgb'] * c_to_co2
    y_max_agb_bgb = y_max_agb + y_max_bgb

    return y_max_agb_bgb

# maximum biomass using Joe's deciles method

def _formatDecileResponse_OLD(features):
    """
    Private function making data out of EE more accessible
    """
    return {p['ECO_ID']: {
        'area': p['SHAPE_AREA'],
        'biome_num': p['BIOME_NUM'],
        'biome_name': p['BIOME_NAME'],
        'eco_num': p['ECO_ID'],
        'eco_name': p['ECO_NAME'],
        'eco_biome_code': p['ECO_BIOME_'],
        'realm': p['REALM'],
        'nature_needs_half': p['NNH'],
        'tCO2e_decile_labels': [5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 95],
        'tCO2e_deciles': [round(d, 2) for d in
                          [p['p5'], p['p10'], p['p20'], p['p30'],
                           p['p40'], p['p50'], p['p60'], p['p70'],
                           p['p80'], p['p90'], p['p95']]],
        'tCO2e_max': round(p['p100'], 2)
    }
        for p in [f['properties'] for f in features['features']]
    }

def _formatDecileResponse(features):
    """
    Private function making data out of EE more accessible
    """
    return {p['ECO_ID']: {
        'area': p['SHAPE_AREA'],
        'biome_num': p['BIOME_NUM'],
        'biome_name': p['BIOME_NAME'],
        'eco_num': p['ECO_ID'],
        'eco_name': p['ECO_NAME'],
        'eco_biome_code': p['ECO_BIOME_'],
        'realm': p['REALM'],
        'nature_needs_half': p['NNH'],
        'tCO2e_decile_labels': [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'tCO2e_deciles': [round(d, 2) for d in
                          [p['p0'], p['p10'], p['p20'], p['p30'],
                           p['p40'], p['p50'], p['p60'], p['p70'],
                           p['p80'], p['p90'], p['p100']]],
        'tCO2e_max': round(p['p100'], 2)
    }
        for p in [f['properties'] for f in features['features']]
    }

def getNearbyMatureForestPercentiles(geojson, buffer=20):
    """
    Take a geojson structure (output from landOS) and get a list of the deciles of biomass (agb+bgb) in tCO2e/ha

    Parameters
    ----------
    geojson : [dict]
               dictionary of shapefile that you get as the output from landOS for the "shapefile"
    buffer : [float]
              buffer distance in km (default = 20 km)

    Returns
    -------
    return[0] : biomass (agb+bgb) in tCO2e/ha from 20km buffer at 5%, 10%, 20%, 30%, 40%, 50%, 60%, 70%, 80%, 90%, 95%
    return[1] : maximum biomass (agb+bgb) in tCO2e/ha from 20km buffer
    """

    aoi = ee.FeatureCollection(geojson['features'])

    ## 1. Find ecoregions that overlap with the AOI
    ecoregions = ee.FeatureCollection('RESOLVE/ECOREGIONS/2017');

    # Get set of ecoregions that occur in the area of interest and limit distance to no more than 20km away
    bounds = ee.Geometry(aoi.geometry(maxError=100))
    buffered = bounds.buffer(distance=buffer * 1000, maxError=1000)  # distance=20000
    searchAreas = ecoregions.filterBounds(bounds).map(
        lambda f: f.intersection(buffered))

    ## 2. Within those ecoregions, find "mature forests"
    # Additional Forest Non/Forest in 20210 from PALSAR
    forestMask = (ee.ImageCollection("JAXA/ALOS/PALSAR/YEARLY/FNF")
                  .filterDate('2009-01-01', '2011-12-31')
                  .first().select('fnf').remap([1], [1], 0))

    # Forest Age as UInt8, 'old growth'==255
    forestAge = ee.Image("projects/es-gis-resources/assets/forestage").select([0], ['forestage']);

    # Find forests that are 50 years old, or at least older than 90% of forests in the ecoregion
    matureForest = forestAge.gte(
        forestAge.reduceRegions(searchAreas, ee.Reducer.percentile([90]))
            .reduceToImage(['p90'], 'first')
            .min(50)
    )

    ## 3. Get the distribution of biomass as deciles of those mature forests
    # Biomass - Spawn dataset: https://www.nature.com/articles/s41597-020-0444-4
    biomass = ee.ImageCollection("NASA/ORNL/biomass_carbon_density/v1").first()
    biomass = (biomass.select('agb').add(biomass.select('bgb'))
               .multiply(3.66).select([0], ['tCO2e']))  # agb_bgb in tCO2e/ha

    # Mask away non forests and young forests, and then get the pdf
    featureDeciles = (biomass.mask(forestMask).mask(matureForest)
                      .reduceRegions(searchAreas,
                                     ee.Reducer.percentile([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]),
                                     scale=100)
                      ).map(lambda f: ee.Feature(None, f.toDictionary()))

    # Return a cleaned-up response
    output_dict = _formatDecileResponse(featureDeciles.getInfo())  # could go back to returning the whole dict

    for eco_id, ecozone in output_dict.items():
        tCO2eha_deciles = ecozone['tCO2e_deciles']
        tCO2eha_max = ecozone['tCO2e_max']

    return tCO2eha_deciles, tCO2eha_max

def getWalkerValues(geojson):
    aoi = ee.FeatureCollection(geojson['features'])

    ## 1. Find ecoregions that overlap with the AOI
    ecoregions = ee.FeatureCollection('RESOLVE/ECOREGIONS/2017');

    # Get set of ecoregions that occur in the area of interest and limit distance to no more than 20km away
    bounds = ee.Geometry(aoi.geometry(maxError=100))
    searchAreas = ecoregions.filterBounds(bounds).map(
        lambda f: f.intersection(bounds))

    ## 2. Within those ecoregions, find "mature forests"
    # Additional Forest Non/Forest in 20210 from PALSAR
    forestMask = (ee.ImageCollection("JAXA/ALOS/PALSAR/YEARLY/FNF")
                  .filterDate('2009-01-01', '2011-12-31')
                  .first().select('fnf').remap([1], [1], 0))

    # Walker Potential C storage
    walker_potC = ee.Image(
        'projects/earthengine-legacy/assets/users/steve_klosterman/Walker_et_al/Base_Pot_AGB_BGB_MgCha_500m')

    # Convert C -> CO2e
    walker_potC = (walker_potC.select('b1')
                   .multiply(3.66)
                   .select([0], ['tCO2e']))  # agb_bgb in tCO2e/ha

    featureValues = walker_potC.sampleRegions(bounds).getInfo()

    test = pd.DataFrame(featureValues['features'])
    test1 = pd.concat([test.drop(['properties'], axis=1), test['properties'].apply(pd.Series)], axis=1)
    test1 = test1[test1.tCO2e > 0]
    test1_pctile = np.percentile(test1['tCO2e'], [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])

    # return tCO2eha_deciles, tCO2eha_max
    return test1, test1_pctile
