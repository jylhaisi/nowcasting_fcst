# -*- coding: utf-8 -*-
import interpolate_fcst
import h5py
import numpy as np
import argparse
import datetime
import configparser
import netCDF4
import sys
import os
import time
from eccodes import *
import matplotlib.pyplot as plt
import matplotlib.colors as colors
# from scipy.ndimage.filters import gaussian_filter
# from scipy.ndimage.morphology import distance_transform_edt
import diagnostics_functions





### THESE FUNCTIONS ARE COPIED MANUALLY FROM call_interpolation.py!!!!! ###

def read(image_file,added_hours=0):
    if image_file.endswith(".nc"):
        return read_nc(image_file,added_hours)
    elif image_file.endswith(".grib2"):
        return read_grib(image_file,added_hours)
    elif image_file.endswith(".h5"):
        return read_HDF5(image_file,added_hours)
    else:
        print("unsupported file type for file: %s" % (image_file))
        


def ncdump(nc_fid, verb=True):
    '''
    ncdump outputs dimensions, variables and their attribute information.
    The information is similar to that of NCAR's ncdump utility.
    ncdump requires a valid instance of Dataset.

    Parameters
    ----------
    nc_fid : netCDF4.Dataset
        A netCDF4 dateset object
    verb : Boolean
        whether or not nc_attrs, nc_dims, and nc_vars are printed

    Returns
    -------
    nc_attrs : list
        A Python list of the NetCDF file global attributes
    nc_dims : list
        A Python list of the NetCDF file dimensions
    nc_vars : list
        A Python list of the NetCDF file variables
    '''
    def print_ncattr(key):
        """
        Prints the NetCDF file attributes for a given key

        Parameters
        ----------
        key : unicode
            a valid netCDF4.Dataset.variables key
        """
        try:
            print("\t\ttype:", repr(nc_fid.variables[key].dtype))
            for ncattr in nc_fid.variables[key].ncattrs():
                print('\t\t%s:' % ncattr,\
                      repr(nc_fid.variables[key].getncattr(ncattr)))
        except KeyError:
            print("\t\tWARNING: %s does not contain variable attributes" % key)

    # NetCDF global attributes
    nc_attrs = nc_fid.ncattrs()
    if verb:
        print("NetCDF Global Attributes:")
        for nc_attr in nc_attrs:
            print('\t%s:' % nc_attr, repr(nc_fid.getncattr(nc_attr)))
    nc_dims = [dim for dim in nc_fid.dimensions]  # list of nc dimensions
    # Dimension shape information.
    if verb:
        print("NetCDF dimension information:")
        for dim in nc_dims:
            print("\tName:", dim) 
            print("\t\tsize:", len(nc_fid.dimensions[dim]))
            print_ncattr(dim)
    # Variable information.
    nc_vars = [var for var in nc_fid.variables]  # list of nc variables
    if verb:
        print("NetCDF variable information:")
        for var in nc_vars:
            if var not in nc_dims:
                print('\tName:', var)
                print("\t\tdimensions:", nc_fid.variables[var].dimensions)
                print("\t\tsize:", nc_fid.variables[var].size)
                print_ncattr(var)
    return nc_attrs, nc_dims, nc_vars



def read_nc(image_nc_file,added_hours):
    tempds = netCDF4.Dataset(image_nc_file)
    internal_variable = list(tempds.variables.keys())[-1]
    temps = np.array(tempds.variables[internal_variable][:]) # This picks the actual data
    nodata = tempds.variables[internal_variable].missing_value
    time_var = tempds.variables["time"]
    dtime = netCDF4.num2date(time_var[:],time_var.units) # This produces an array of datetime.datetime values
    
    # Outside of area all the values are missing. Leave them as they are. They're not affected by the motion vector calculations
    mask_nodata = np.ma.masked_where(temps == nodata,temps)
    # Pick min/max values from the data
    temps_min= temps[np.where(~np.ma.getmask(mask_nodata))].min()
    temps_max= temps[np.where(~np.ma.getmask(mask_nodata))].max()
    if type(dtime) == list:
        dtime = [(i+datetime.timedelta(hours=added_hours)) for i in dtime]
    else:
        dtime = dtime+datetime.timedelta(hours=added_hours)

    
    return temps, temps_min, temps_max, dtime, mask_nodata, nodata



def read_grib(image_grib_file,added_hours):

    # check comments from read_nc()
    dtime = []
    tempsl = []
    latitudes = []
    longitudes = []
    
    with GribFile(image_grib_file) as grib:
        for msg in grib:
            #print msg.size()
            #print msg.keys()
            ni = msg["Ni"]
            nj = msg["Nj"]
            #print(msg["dataDate"])
            #print(msg["dataTime"])
            #print(datetime.datetime.strptime("{:d}/{:02d}".format(msg["dataDate"], msg["dataTime"]/100), "%Y%m%d/%H"))
            forecast_time = datetime.datetime.strptime("{:d}/{:02d}".format(msg["dataDate"], int(msg["dataTime"]/100)), "%Y%m%d/%H") + datetime.timedelta(hours=msg["forecastTime"])
            # forecast_time = datetime.datetime.strptime("%s%02d" % (msg["dataDate"], msg["dataTime"]), "%Y%m%d%H%M") + datetime.timedelta(hours=msg["forecastTime"])
            # print(forecast_time)
            dtime.append(forecast_time)
            tempsl.append(np.asarray(msg["values"]).reshape(nj, ni))
            latitudes.append(np.asarray(msg["latitudes"]).reshape(nj, ni))
            longitudes.append(np.asarray(msg["longitudes"]).reshape(nj, ni))

            
    temps = np.asarray(tempsl)
    latitudes = np.asarray(latitudes)
    longitudes = np.asarray(longitudes)
    latitudes = latitudes[0,:,:]
    longitudes = longitudes[0,:,:]
    nodata = 9999

    mask_nodata = np.ma.masked_where(temps == nodata,temps)
    temps_min= temps[np.where(~np.ma.getmask(mask_nodata))].min()
    temps_max= temps[np.where(~np.ma.getmask(mask_nodata))].max()
    if type(dtime) == list:
        dtime = [(i+datetime.timedelta(hours=added_hours)) for i in dtime]
    else:
        dtime = dtime+datetime.timedelta(hours=added_hours)


    return temps, temps_min, temps_max, dtime, mask_nodata, nodata, longitudes, latitudes



def read_HDF5(image_h5_file,added_hours):
    #Read RATE or DBZH from hdf5 file
    print('Extracting data from image h5 file')
    hf = h5py.File(image_h5_file,'r')
    ### hiisi way
    # comp = hiisi.OdimCOMP(image_h5_file, 'r')
    #Look for DBZH or RATE array
    if (str(hf['/dataset1/data1/what'].attrs.__getitem__('quantity')) in ("b'DBZH'","b'RATE'")) == False:
        print('Error: RATE or DBZH array not found in the input image file!')
        sys.exit(1)
    if (str(hf['/dataset1/data1/what'].attrs.__getitem__('quantity')) == "b'DBZH'"):
        quantity_min = options.R_min
        quantity_max = options.R_max
    if (str(hf['/dataset1/data1/what'].attrs.__getitem__('quantity')) == "b'DBZH'"):
        quantity_min = options.DBZH_min
        quantity_max = options.DBZH_max
    
    # Read actual data in
    image_array = hf['/dataset1/data1/data'][:]
    
    #Read nodata/undetect/gain/offset/date/time values from metadata
    nodata = hf['/dataset1/data1/what'].attrs.__getitem__('nodata')
    undetect = hf['/dataset1/data1/what'].attrs.__getitem__('undetect')
    gain = hf['/dataset1/data1/what'].attrs.__getitem__('gain')
    offset = hf['/dataset1/data1/what'].attrs.__getitem__('offset')
    date = str(hf['/what'].attrs.__getitem__('date'))[2:-1]
    time = str(hf['/what'].attrs.__getitem__('time'))[2:-1]
    ### hiisi way below
    # gen = comp.attr_gen('nodata')
    # pair = next(gen)
    # nodata = pair.value
    # gen = comp.attr_gen('undetect')
    # pair = next(gen)
    # undetect = pair.value
    # gen = comp.attr_gen('gain')
    # pair = next(gen)
    # gain = pair.value
    # gen = comp.attr_gen('offset')
    # pair = next(gen)
    # offset = pair.value
    # gen = comp.attr_gen('date')
    # pair = next(gen)
    # date = pair.value
    # gen = comp.attr_gen('time')
    # pair = next(gen)
    # time = pair.value

    timestamp=date+time
    dtime = datetime.datetime.strptime(timestamp, "%Y%m%d%H%M%S")

    # Flip latitude dimension
    image_array = np.flipud(image_array)
    tempsl = []
    tempsl.append(image_array)
    temps = np.asarray(tempsl)
    
    #Masks of nodata and undetect
    mask_nodata = np.ma.masked_where(temps == nodata,temps)
    mask_undetect = np.ma.masked_where(temps == undetect,temps)
    #Change to physical values
    temps=temps*gain+offset
    #Mask undetect values as 0 and nodata values as nodata
    temps[np.where(np.ma.getmask(mask_undetect))] = 0
    temps[np.where(np.ma.getmask(mask_nodata))] = nodata
    
    temps_min= temps[np.where(~np.ma.getmask(mask_nodata))].min()
    temps_max= temps[np.where(~np.ma.getmask(mask_nodata))].max()
    if type(dtime) == list:
        dtime = [(i+datetime.timedelta(hours=added_hours)) for i in dtime]
    else:
        dtime = dtime+datetime.timedelta(hours=added_hours)


    return temps, temps_min, temps_max, dtime, mask_nodata, nodata



def write(interpolated_data,image_file,write_file,variable,predictability):

    if write_file.endswith(".nc"):
        write_nc(interpolated_data,image_file,write_file,variable,predictability)
    elif write_file.endswith(".grib2"):
        write_grib(interpolated_data,image_file,write_file,variable,predictability)
    else:
        print("unsupported file type for file: %s" % (image_file))
        return
    print("wrote file '%s'" % write_file)



def write_grib(interpolated_data,image_grib_file,write_grib_file,variable,predictability):
    # (Almost) all the metadata is copied from modeldata.grib2
    try:
        os.remove(write_grib_file)
    except OSError as e:
        pass

    # Change data type of numpy array
    # interpolated_data = np.round(interpolated_data,2)
    # interpolated_data = interpolated_data.astype('float64')             

    #with GribFile(image_grib_file) as grib:
    #    for msg in grib:
    #        msg["generatingProcessIdentifier"] = 202
    #        msg["centre"] = 86
    #        msg["bitmapPresent"] = True
    #
    #        for i in range(interpolated_data.shape[0]):
    #            msg["forecastTime"] = i
    #            msg["values"] = interpolated_data[i].flatten()
    #
    #            with open(write_grib_file, "a") as out:
    #                msg.write(out)
    #        break # we use only the first grib message as a template

    # This edits each grib message individually
    with GribFile(image_grib_file) as grib:
        i=-1
        for msg in grib:
            msg["generatingProcessIdentifier"] = 202
            msg["centre"] = 86
            msg["bitmapPresent"] = True
            i = i+1 # msg["forecastTime"]
            if (i == interpolated_data.shape[0]):
                break
            msg["values"] = interpolated_data[i,:,:].flatten()
            # print("{} {}: {}".format("histogram of interpolated_data timestep ",i,np.histogram(interpolated_data[i,:,:].flatten(),bins=20,range=(240,300))))
            # print("{} {}: {}".format("histogram of msg[values] timestep ",i,np.histogram(msg["values"],bins=20,range=(240,300))))
            with open(str(write_grib_file), "ab") as out:
                msg.write(out)



def write_nc(interpolated_data,image_nc_file,write_nc_file,variable,predictability):
    
    # All the metadata is copied from modeldata.nc
    nc_f = image_nc_file
    nc_fid = netCDF4.Dataset(nc_f, 'r')
    nc_attrs, nc_dims, nc_vars = ncdump(nc_fid)
    # Open the output file
    w_nc_fid = netCDF4.Dataset(write_nc_file, 'w', format='NETCDF4')
    # Using our previous dimension information, we can create the new dimensions
    data = {}
    # Creating dimensions
    for dim in nc_dims:
        w_nc_fid.createDimension(dim, nc_fid.variables[dim].size)
    # Creating variables
    for var in nc_vars:
        data[var] = w_nc_fid.createVariable(varname=var, datatype=nc_fid.variables[var].dtype,dimensions=(nc_fid.variables[var].dimensions))
        # Assigning attributes for the variables
        for ncattr in nc_fid.variables[var].ncattrs():
            data[var].setncattr(ncattr, nc_fid.variables[var].getncattr(ncattr))
        # Assign the data itself
        if (var in ['time','y','x','lat','lon']):
            w_nc_fid.variables[var][:] = nc_fid.variables[var][:]
        if (var == nc_vars[len(nc_vars)-1]):
            w_nc_fid.variables[var][:] = interpolated_data
    # Creating the global attributes
    w_nc_fid.description = "Blended nowcast forecast, variable %s, predictability %s" %(variable, predictability)
    w_nc_fid.history = 'Created ' + time.ctime(time.time())  
    for attribute in nc_attrs:
        w_nc_fid.setncattr(attribute, nc_fid.getncattr(attribute))
        # w_nc_fid[attribute] = nc_fid.getncattr(attribute)
    # for attribute in nc_attrs:
    #     eval_string = 'w_nc_fid.' + attribute + ' = nc_fid.getncattr("' + attribute + '")'
    #     eval(eval_string)
    # Close the file
    w_nc_fid.close()



def farneback_params_config(config_file_name):
    config = configparser.ConfigParser()
    config.read(config_file_name)
    farneback_pyr_scale  = config.getfloat("optflow", "pyr_scale")
    farneback_levels     = config.getint("optflow", "levels")
    farneback_winsize    = config.getint("optflow", "winsize")
    farneback_iterations = config.getint("optflow", "iterations")
    farneback_poly_n     = config.getint("optflow", "poly_n")
    farneback_poly_sigma = config.getfloat("optflow", "poly_sigma")
    farneback_params = (farneback_pyr_scale,  farneback_levels, farneback_winsize, 
                        farneback_iterations, farneback_poly_n, farneback_poly_sigma, 0)
    return farneback_params



def read_background_data_and_make_mask(image_file, input_mask=None, mask_smaller_than_borders=4, smoother_coefficient=0.2, gaussian_filter_coefficient=3):
    # mask_smaller_than_borders controls how many pixels the initial mask is compared to obs field
    # smoother_coefficient controls how long from the borderline bg field is affecting
    # gaussian_filter_coefficient sets the smoothiness of the weight field
    
    # Read in detectability data field and change all not-nodata values to zero
    image_array4, quantity4_min, quantity4_max, timestamp4, mask_nodata4, nodata4 = read(image_file)
    image_array4[np.where(~np.ma.getmask(mask_nodata4))] = 0
    mask_nodata4_p = np.sum(np.ma.getmask(mask_nodata4),axis=0)>0
    
    # Creating a linear smoother field: More weight for bg near the bg/obs border and less at the center of obs field
    # Gaussian smoother widens the coefficients so initially calculate from smaller mask the values
    used_mask = distance_transform_edt(np.logical_not(mask_nodata4_p)) - distance_transform_edt(mask_nodata4_p)
    # Allow used mask to be bigger or smaller than initial mask given
    used_mask2 = np.where(used_mask <= mask_smaller_than_borders,True,False)
    # Combine with boolean input mask if that is given
    if input_mask is not None:
        used_mask2 = np.logical_or(used_mask2,input_mask)
    used_mask = distance_transform_edt(np.logical_not(used_mask2))
    weights_obs = gaussian_filter(used_mask,gaussian_filter_coefficient)
    weights_obs = weights_obs / (smoother_coefficient*np.max(weights_obs))
    # Cropping values to between 0 and 1
    weights_obs = np.where(weights_obs>1,1,weights_obs)
    # Leaving only non-zero -values which are inside used_mask2
    weights_obs = np.where(np.logical_not(used_mask2),weights_obs,0)
    weights_bg = 1 - weights_obs
    
    return weights_bg



def define_common_mask_for_fields(*args):
    """Calculate a combined mask for each input. Some input values might have several timesteps, but here define a mask if ANY timestep for that particular gridpoint has a missing value"""
    stacked = (np.sum(np.ma.getmaskarray(args[0]),axis=0)>0)
    if (len(args)==0):
        return(stacked)
    for arg in args[1:]:
        try:
            stacked = np.logical_or(stacked,(np.sum(np.ma.getmaskarray(arg),axis=0)>0))
        except:
            raise ValueError("grid sizes do not match!")
    return(stacked)

























def main():

#     # For testing purposes set test datafiles
#     options.obs_data = None # "testdata/latest/obs_tp.grib2"
#     options.model_data = "testdata/latest/fcst_tprate.grib2"
#     options.background_data = "testdata/latest/mnwc_tprate.grib2"
#     options.dynamic_nwc_data = "testdata/latest/mnwc_tprate_full.grib2"
#     options.extrapolated_data = "testdata/latest/ppn_tprate.grib2"
#     options.detectability_data = "testdata/radar_detectability_field_255_280.h5"
#     options.output_data = "testdata/latest/output/interpolated_tprate.grib2"
#     options.parameter = "precipitation_1h_bg"
#     options.mode = "model_fcst_smoothed"
#     options.predictability = 8










if __name__ == '__main__':
    #Parse commandline arguments
    parser = argparse.ArgumentParser(argument_default=None)
    parser.add_argument('--obs_data',
                        help='Observation data field or similar, used as 0h forecast')
    parser.add_argument('--model_data',
                        help='Model data field, towards which the nowcast is smoothed')
    parser.add_argument('--background_data',
                        help='Background data field for the 0h forecast where obsdata is spatially merged to')
    parser.add_argument('--dynamic_nwc_data',
                        help='Dynamic nowcasting model data field, which is smoothed to modeldata. If extrapolated_data is provided, it is spatially smoothed with dynamic_nwc_data. First timestep of 0h should not be included in this data!')
    parser.add_argument('--extrapolated_data',
                        help='Nowcasting model data field acquired using extrapolation methods (like PPN), which is smoothed to modeldata. If dynamic_nwc_data is provided, extrapolated_data is spatially smoothed with it. First timestep of 0h should not be included in this data!')
    parser.add_argument('--detectability_data',
                        default="testdata/radar_detectability_field_255_280.h5",
                        help='Radar detectability field, which is used in spatial blending of obsdata and bgdata')
    parser.add_argument('--output_data',
                        help='Output file name for nowcast data field')
    parser.add_argument('--seconds_between_steps',
                        type=int,
                        default=3600,
                        help='Timestep of output data in seconds')
    parser.add_argument('--predictability',
                        type=int,
                        default='4',
                        help='Predictability in hours. Between the analysis and forecast of this length, forecasts need to be interpolated')
    parser.add_argument('--parameter',
                        help='Variable which is handled.')
    parser.add_argument('--mode',
                        default='analysis_fcst_smoothed',
                        help='Either "analysis_fcst_smoothed" or "model_fcst_smoothed" mode. In "analysis_fcst_smoothed" mode, nowcasts are interpolated between 0h (obs_data/background_data) and predictability hours (model_data). In "model_fcst_smoothed" mode, nowcasts are individually interpolated for each forecast length between dynamic_nwc_data/extrapolated/data and model_data and their corresponding forecasts')
    parser.add_argument('--gaussian_filter_sigma',
                        type=float,
                        default=0.5,
                        help='This parameter sets the blurring intensity of the of the analysis field.')
    parser.add_argument('--R_min',
                        type=float,
                        default=0.1,
                        help='Minimum precipitation intensity for optical flow computations. Values below R_min are set to zero.')
    parser.add_argument('--R_max',
                        type=float,
                        default=30.0,
                        help='Maximum precipitation intensity for optical flow computations. Values above R_max are clamped.')
    parser.add_argument('--DBZH_min',
                        type=float,
                        default=10,
                        help='Minimum DBZH for optical flow computations. Values below DBZH_min are set to zero.')
    parser.add_argument('--DBZH_max', 
                        type=float,
                        default=45,
                        help='Maximum DBZH for optical flow computations. Values above DBZH_max are clamped.')
    parser.add_argument('--farneback_params',
                        default='compute_advinterp.cfg',
                        help='location of farneback params configuration file')
    parser.add_argument('--plot_diagnostics',
                        default='no',
                        help='If this option is set to yes, program plots out several diagnostics to files.')

    options = parser.parse_args()
    main()