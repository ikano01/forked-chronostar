"""
This module defines the parameter reading function.

Credit: Mark Krumholz
"""

def update_data_defaults(data_pars):
    """
    Maybe this belongs somewhere else, but... for now....

    Default parameters are stored in this function. If a parameter is
    missing from data_pars, then it is inserted with it's default value.

    Parameters
    ----------
    data_pars : dict

    Returns
    -------
    updated_data_pars : dict
    """
    default_dict = {
        'input_file':'',
        'convert_astrometry':False,

        'astro_main_colnames':None,
        'astro_error_colnames':None,
        'astro_corr_colnames':None,

        'apply_cart_cuts':False,
        'cart_main_colnames':None,
        'cart_error_colnames':None,
        'cart_corr_colnames':None,

        'cut_on_region':False,
        'cut_ref_table':None,
        'cut_assoc_name':None,
        'cut_colname':None,

        'calc_overlaps':False,
        'bg_ref_table':'',
        'bg_main_colnames':None,
        'bg_col_name':None,
        'par_log_file':'data_pars.log',

        'overwrite_datafile':False,
        'output_file':None,

        'return_data_table':True,
    }

    default_dict.update(data_pars)
    return default_dict

def log_used_pars(data_pars):
    """
    Write parameter record to file, making a note which have been
    changed.
    :param data_pars:
    :return:
    """
    # update defaults (no change if already peformed)
    data_pars = update_data_defaults(data_pars)

    # Get default parameters for reference
    default_pars = update_data_defaults(data_pars={})

    with open(data_pars['par_log_file'], 'w') as fp:
        fp.write('# Parameters used\n\n')
        for k in sorted(data_pars.keys()):
            if k not in default_pars.keys():
                msg = '# [NO PROVIDED DEFAULT]'
            elif data_pars[k] != default_pars[k]:
                msg = '# [CHANGED]'
            else:
                msg = ''
            line = '{:25} = {:25} {}\n'.format(k, str(data_pars[k]), msg)
            fp.write(line)


def readParam(paramFile, noCheck=False):
    """
    This function reads a parameter file.

    Parameters
    ----------
    paramFile : string
       A string giving the name of the parameter file
    noCheck : bool
       If True, no checking is performed to make sure that all
       mandatory parameters have been specified

    Returns
    -------
    paramDict : dict
       A dict containing a parsed representation of the input file

    Notes
    -----
    TODO: Work out how to format input for synthetic association
    TODO: maybe just dont? And require the use of a script to intialise things?
    """

    # Prepare an empty dict to hold inputs
    paramDict = {}

    # Try to open the file
    fp = open(paramFile, 'r')

    # Read the file
    for line in fp:

        # Skip blank and comment lines
        if line == '\n':
            continue
        if line.strip()[0] == "#":
            continue

        # Break line up based on equal sign
        linesplit = line.split("=")
        if len(linesplit) < 2:
            print("Error parsing input line: " + line)
            raise IOError
#         if linesplit[1] == '':
#             print("Error parsing input line: " + line)
#             raise IOError

        # Trim trailing comments from portion after equal sign
        linesplit2 = linesplit[1].split('#')

        # Store token-value pairs, as strings for now. Type conversion
        # happens below.
        if linesplit2 != '':
            paramDict[linesplit[0].strip()] = linesplit2[0].strip()

    # Close file
    fp.close

    # Try converting parameters to bools or numbers, for convenience
    for k in paramDict.keys():
        try:
            paramDict[k] = int(paramDict[k])
        except ValueError:
            try:
                paramDict[k] = float(paramDict[k])
            except ValueError:
                pass

        # Order is important, as int(True) -> 1
        try:
            if paramDict[k].lower() == 'true':
                paramDict[k] = True
            elif paramDict[k].lower() == 'false':
                paramDict[k] = False
        except AttributeError:
            pass

    # Find any lists (of floats) and convert accordingly
    # Assumes first char is '[' and last char is ']'
    # Can allow for trailing ','
    for k in paramDict.keys():
        try:
            if paramDict[k][0] == '[':
                # First build list of strings
                paramDict[k] = [val for val in paramDict[k][1:-2].split(',')
                                if val.strip()]
                # Then try converting to floats
                try:
                    paramDict[k] = [float(val) for val in paramDict[k]]
                except ValueError:
                    pass
        except (TypeError, IndexError):
            pass

    # if not noCheck:
    #     mandatory = ['alpha', 'gamma', 'ibc_pres_type', 'ibc_enth_type',
    #                  'ibc_pres_val', 'obc_pres_type', 'obc_enth_type',
    #                  'obc_pres_val']
    #     for m in mandatory:
    #         if not m in paramDict:
    #             raise ValueError("Error: must specify parameter " + m + "!\n")

    # Return the dict
    return paramDict
