"""
a module for implementing the expectation-maximisation algorithm
in order to fit a multi-gaussian mixture model of moving groups' origins
to a data set of stars tracedback through XYZUVW

todo:
    - implement average error cacluation in lnprobfunc
"""
from __future__ import print_function, division

import sys
from distutils.dir_util import mkpath
import logging
import numpy as np
import os
import pickle
import random

import chronostar.synthesiser as syn
import chronostar.traceorbit as torb

try:
    import matplotlib as mpl
    # prevents displaying plots from generation from tasks in background
    mpl.use('Agg')
    import matplotlib.pyplot as plt
except ImportError:
    print("Warning: matplotlib not imported")
    pass

import chronostar.transform as tf
import groupfitter as gf

def ix_fst(array, ix):
    if array is None:
        return None
    else:
        return array[ix]


def ix_snd(array, ix):
    if array is None:
        return None
    else:
        return array[:, ix]


def calcErrors(chain, perc=34):
    """
    Given a set of aligned (converted?) samples, calculate the median and
    errors of each parameter

    Parameters
    ----------
    chain : [nwalkers, nsteps, npars]
        The chain of samples (in internal encoding)
    """
    npars = chain.shape[-1]  # will now also work on flatchain as input
    flat_chain = np.reshape(chain, (-1, npars))

    #    conv_chain = np.copy(flat_chain)
    #    conv_chain[:, 6:10] = 1/conv_chain[:, 6:10]

    # return np.array( map(lambda v: (v[1], v[2]-v[1], v[1]-v[0]),
    #                 zip(*np.percentile(flat_chain, [16,50,84], axis=0))))
    return np.array(map(lambda v: (v[1], v[2], v[0]),
                        zip(*np.percentile(flat_chain,
                                           [50-perc, 50, 50+perc],
                                           axis=0))))


def checkConvergence(old_best_fits, new_chains,
                     perc=25):
    """Check if the last maximisation step yielded is consistent to new fit

    TODO: incorporate Z into this convergence checking. e.g.
    np.allclose(z_prev, z, rtol=1e-2)

    Convergence is achieved if previous key values fall within +/-"perc" of
    the new fits.

    Parameters
    ----------
    new_best_fit : [15] array
        paraameters (in external encoding) of the best fit from the new run
    old_best_fit : [15] array
        paraameters (in external encoding) of the best fit from the old run
    new_chain : [nwalkers, nsteps, npars] array
        the sampler chain from the new run
    old_chain : [nwalkers, nsteps, npars] array
        the sampler chain from the old run
    perc : int (0, 50)
        the percentage distance that previous values must be within current
        values.

    Returns
    -------
    converged : bool
        If the runs have converged, return true
    """
    each_converged = []

    for old_best_fit, new_chain in zip(old_best_fits, new_chains):
        errors = calcErrors(new_chain, perc=perc)
        upper_contained =\
            old_best_fit.getInternalSphericalPars() < errors[:, 1]
        lower_contained =\
            old_best_fit.getInternalSphericalPars() > errors[:, 2]

        each_converged.append(
            np.all(upper_contained) and np.all(lower_contained))

    return np.all(each_converged)


def calcLnoverlaps(group_pars, star_pars, nstars):
    """Find the lnoverlaps given the parameters of a group

    Parameters
    ----------
    group_pars : [npars] array
        Group parameters (internal encoding, 1/dX... no nstars)
    star_pars : dict
        stars: (nstars) high astropy table including columns as
            documented in the Traceback class.
        times : [ntimes] numpy array
            times that have been traced back, in Myr
        xyzuvw : [nstars, ntimes, 6] array
            XYZ in pc and UVW in km/s
        xyzuvw_cov : [nstars, ntimes, 6, 6] array
            covariance of xyzuvw
    nstars : int
        number of stars in traceback

    Returns
    -------
    lnols : [nstars] array
        The log of the overlap of each star with the provided group
    """
    lnols = None
    return lnols


def calcMembershipProbs(star_lnols):
    """Calculate probabilities of membership for a single star from overlaps

    Parameters
    ----------
    star_lnols : [ngroups] array
        The log of the overlap of a star with each group

    Returns
    -------
    star_memb_probs : [ngroups] array
        The probability of membership to each group, normalised to sum to 1
    """
    ngroups = star_lnols.shape[0]
    star_memb_probs = np.zeros(ngroups)

    for i in range(ngroups):
        star_memb_probs[i] = 1. / np.sum(np.exp(star_lnols - star_lnols[i]))

    return star_memb_probs


def backgroundLogOverlap(star_mean, bg_hists):
    """Calculate the 'overlap' of a star with the background desnity of Gaia

    We assume the Gaia density is approximately constant over the size scales
    of a star's uncertainty, and so approximate the star as a delta function
    at it's central estimate(/mean)

    Parameters
    ----------
    star_mean : [6] float array
        the XYZUVW central estimate of a star, XYZ in pc and UVW in km/s

    bg_hists : 6*[[nbins],[nbins+1]] list
        A collection of histograms desciribing the phase-space density of
        the Gaia catalogue in the vicinity of associaiton in quesiton.
        For each of the 6 dimensions there is an array of bin values and
        an array of bin edges.

        e.g. bg_hists[0][1] is an array of floats describing the bin edges
        of the X dimension 1D histogram, and bg_hists[0][0] is an array of
        integers describing the star counts in each bin
    """
    # get the total area under a histogram
    n_gaia_stars = np.sum(bg_hists[0][0])
    ndim = 6

    lnol = 0
    for i in range(ndim):
        lnol += np.log(
            bg_hists[i][0][np.digitize(star_mean[i], bg_hists[i][1])]
        )

    # Renormalise such that the combined 6D histogram has a hyper-volume
    # of n_gaia_stars
    lnol -= 5 * np.log(n_gaia_stars)
    return lnol


def backgroundLogOverlaps(xyzuvw, bg_hists):
    """Calculate the 'overlaps' of stars with the background desnity of Gaia

    We assume the Gaia density is approximately constant over the size scales
    of a star's uncertainty, and so approximate the star as a delta function
    at it's central estimate(/mean)

    Parameters
    ----------
    xyzuvw: [nstars, 6] float array
        the XYZUVW central estimate of a star, XYZ in pc and UVW in km/s

    bg_hists : 6*[[nbins],[nbins+1]] list
        A collection of histograms desciribing the phase-space density of
        the Gaia catalogue in the vicinity of associaiton in quesiton.
        For each of the 6 dimensions there is an array of bin values and
        an array of bin edges.

        e.g. bg_hists[0][1] is an array of floats describing the bin edges
        of the X dimension 1D histogram, and bg_hists[0][0] is an array of
        integers describing the star counts in each bin
    """
    bg_ln_ols = np.zeros(xyzuvw.shape[0])
    for i in range(bg_ln_ols.shape[0]):
        bg_ln_ols[i] = backgroundLogOverlap(xyzuvw[i], bg_hists)
    return bg_ln_ols


def expectation(star_pars, groups, old_z=None, bg_ln_ols=None):
    """Calculate membership probabilities given fits to each group

    Parameters
    ----------
    star_pars : dict
        stars: (nstars) high astropy table including columns as
                    documented in the Traceback class.
        times : [ntimes] numpy array
            times that have been traced back, in Myr
        xyzuvw : [nstars, ntimes, 6] array
            XYZ in pc and UVW in km/s
        xyzuvw_cov : [nstars, ntimes, 6, 6] array
            covariance of xyzuvw

    groups : [ngroups] syn.Group object list
        a fit for each group (in internal form)

    old_z : [nstars, ngroups (+1)] float array
        Only used to get weights (amplitudes) for each fitted component.
        Tracks membership probabilities of each star to each group. Each
        element is between 0.0 and 1.0 such that each row sums to 1.0
        exactly.
        If bg_hists are also being used, there is an extra column for the
        background. However it is not used in this context

    bg_ln_ols : [nstars] float array
        The overlap the stars have with the (fixed) background distribution

    Returns
    -------
    z : [nstars, ngroups] array
        An array designating each star's probability of being a member to
        each group. It is populated by floats in the range (0.0, 1.0) such
        that each row sums to 1.0, each column sums to the expected size of
        each group, and the entire array sums to the number of stars.
    """
    ngroups = len(groups)
    nstars = len(star_pars['xyzuvw'])

    using_bg = bg_ln_ols is not None

    # if no z provided, assume perfectly equal membership
    if old_z is None:
        old_z = np.ones((nstars, ngroups + using_bg))/(ngroups + using_bg)

    lnols = np.zeros((nstars, ngroups + using_bg))
    for i, group in enumerate(groups):
        # weight is the amplitude of a component, proportional to its expected
        # total of stellar members
        weight = old_z[:,i].sum()
        # threshold = nstars/(2. * (ngroups+1))
        # if weight < threshold:
        #     logging.info("!!! GROUP {} HAS LESS THAN {} STARS, weight: {}".\
        #         format(i, threshold, weight)
        # )
        group_pars = group.getInternalSphericalPars()
        lnols[:, i] =\
            np.log(weight) +\
                gf.getLogOverlaps(group_pars, star_pars)
            # gf.lnlike(group_pars, star_pars,
            #                            old_z, return_lnols=True) #??!??!?!

    # insert one time calculated background overlaps
    if using_bg:
        lnols[:,-1] = bg_ln_ols
    z = np.zeros((nstars, ngroups + using_bg))
    for i in range(nstars):
        z[i] = calcMembershipProbs(lnols[i])
    if np.isnan(z).any():
        logging.info("!!!!!! AT LEAST ONE MEMBERSHIP IS 'NAN' !!!!!!")
        #import pdb; pdb.set_trace()
    return z


def getPointsOnCircle(npoints, v_dist=20, offset=False):
    """
    Little tool to found coordinates of equidistant points around a circle

    Used to initialise UV for the groups.
    :param npoints:
    :return:
    """
    us = np.zeros(npoints)
    vs = np.zeros(npoints)
    if offset:
        init_angle = np.pi / npoints
    else:
        init_angle = 0.

    for i in range(npoints):
        us[i] = v_dist * np.cos(init_angle + 2 * np.pi * i / npoints)
        vs[i] = v_dist * np.sin(init_angle + 2 * np.pi * i / npoints)

    return np.vstack((us, vs)).T


def getInitialGroups(ngroups, xyzuvw, offset=False):
    """
    Generate the parameter list with which walkers will be initialised

    Parameters
    ----------
    ngroups: int
        number of groups
    xyzuvw: [nstars, 6] array
        the mean measurement of stars
    offset : (boolean {False})
        If set, the gorups are initialised in the complementary angular
        positions

    Returns
    -------
    groups: [ngroups] synthesiser.Group object list
        the parameters with which to initialise each group's emcee run
    """
    groups = []

    mean = np.mean(xyzuvw, axis=0)[:6]
    logging.info("Mean is\n{}".format(mean))
#    meanXYZ = np.array([0.,0.,0.])
#    meanW = 0.
    dx = 50.
    dv = 5.
    age = 3.
    # group_pars_base = list([0, 0, 0, None, None, 0, np.log(50),
    #                         np.log(5), 3])
    pts = getPointsOnCircle(npoints=ngroups, v_dist=10, offset=offset)
    logging.info("Points around circle are:\n{}".format(pts))

    for i in range(ngroups):
        mean_w_offset = np.copy(mean)
        mean_w_offset[3:5] += pts[i]
        logging.info("Group {} has init UV of ({},{})".\
                    format(i, mean_w_offset[3], mean_w_offset[4]))
        group_pars = np.hstack((mean_w_offset, dx, dv, age))
        group = syn.Group(group_pars, sphere=True, starcount=False)
        groups.append(group)

    return groups

def decomposeGroup(group):
    """
    Takes a group object and splits it into two components offset by age.

    Parameters
    ----------
    group: synthesiser.Group instance
        the group which is to be decomposed

    Returns
    -------
    all_init_pars: [2, npars] array
        the intenralised parameters with which the walkers will be
        initiallised
    sub_groups: [2] list of Group instances
        the group objects of the resulting decomposition
    """
    internal_pars = group.getInternalSphericalPars()
    mean_now = torb.traceOrbitXYZUVW(group.mean, group.age, single_age=True)
    ngroups = 2
    AGE_OFFSET = 4

    sub_groups = []

    young_age = max(1e-5, group.age - AGE_OFFSET)
    old_age = group.age + AGE_OFFSET

    ages = [young_age, old_age]
    for age in ages:
        mean_then = torb.traceOrbitXYZUVW(mean_now, -age, single_age=True)
        group_pars_int = np.hstack((mean_then, internal_pars[6:8], age))
        sub_groups.append(syn.Group(group_pars_int, sphere=True,
                                    internal=True, starcount=False))
    all_init_pars = [sg.getInternalSphericalPars() for sg in sub_groups]

    return all_init_pars, sub_groups


def fitManyGroups(star_pars, ngroups, rdir='', init_z=None,
                  origins=None, pool=None, init_with_origin=False,
                  offset=False,  bg_hist_file=''):
    """
    Entry point: Fit multiple Gaussians to data set

    Parameters
    ----------
    star_pars: dict
        'xyzuvw': [nstars, 6] numpy array
            the xyzuvw mean values of each star, calculated from astrometry
        'xyzuvw_cov': [nstars, 6, 6] numpy array
            the xyzuvw covarince values of each star, calculated from
            astrometry
        'table': Astropy table (sometimes None)
            The astrometry from which xyzuvw values are calculated. Can
            optionally include more information, like star names etc.
    ngroups: int
        the number of groups to be fitted to the data
    rdir: String {''}
        The directory in which all the data will be stored and accessed
        from
    init_z: [nstars, ngroups] array {None} [UNIMPLEMENTED]
        If some members are already known, the initialsiation process
        could use this.
    origins: [ngroups] synthetic Group
    pool: MPIPool object {None}
        the pool of threads to be passed into emcee
    use_background: Bool {False}
        If set, will use histograms based on Gaia data set to compare
        association memberships to the field. Assumes file is in [rdir]

    Return
    ------
    final_groups: [ngroups, npars] array
        the best fit for each group
    final_med_errs: [ngroups, npars, 3] array
        the median, -34 perc, +34 perc values of each parameter from
        each final sampling chain
    z: [nstars, ngroups] array
        membership probabilities

    TODO: Generalise interventions for more than 2 groups
    """
    # setting up some constants
    BURNIN_STEPS = 1000
    SAMPLING_STEPS = 5000
    C_TOL = 0.5

    use_background = False
    bg_hists = None
    bg_ln_ols = None
    if bg_hist_file:
        use_background = True
        bg_hists = np.load(rdir + bg_hist_file)
        bg_ln_ols = backgroundLogOverlaps(star_pars['xyzuvw'], bg_hists)

    nstars = star_pars['xyzuvw'].shape[0]
    # INITIALISE GROUPS
    if not init_with_origin:
        init_groups = getInitialGroups(ngroups, star_pars['xyzuvw'],
                                       offset=offset)
        # having z = None triggers an equal weighting of groups in
        # expectation step
        z = None
    else:
        init_groups = origins
        z = np.zeros((nstars, ngroups + use_background))
        cnt = 0
        for i in range(ngroups):
            z[cnt:cnt+origins[i].nstars, i] = 1.0
            cnt += origins[i].nstars
        logging.info("Initialising fit with origins and membership\n{}".\
            format(z))

    np.save(rdir + "init_groups.npy", init_groups)

    all_init_pos = ngroups * [None]
    iter_count = 0
    converged = False

    old_groups = init_groups
    all_init_pars = [init_group.getInternalSphericalPars() for init_group
                     in init_groups]

    while not converged:
        # for iter_count in range(10):
        idir = rdir+"iter{}/".format(iter_count)
        logging.info("\n--------------------------------------------------"
                     "\n--------------    Iteration {}    ----------------"
                     "\n--------------------------------------------------".
                     format(iter_count))

        mkpath(idir)

        # EXPECTATION
        z = expectation(star_pars, old_groups, z, bg_ln_ols)
        #if iter_count == 1: # had this to force a decomposition
        #    z[:,0] = 0.01
        #    z[:,1] = 0.99

        logging.info("Membership distribution:\n{}".format(
            z.sum(axis=0)
        ))
# TODO: NEED TO REWRITE THIS VVVVV SO CAN HANDLE MORE THAN 2 GROUPS
#        if (min(z.sum(axis=0)) < 10):
#            logging.info("!!! WARNING, GROUP {} HAS LESS THAN 10 STARS".\
#                         format(np.argmin(z.sum(axis=0))))
#            logging.info("+++++++++++++++++++++++++++++++++++++++++++")
#            logging.info("++++            Intervening            ++++")
#            logging.info("+++++++++++++++++++++++++++++++++++++++++++")
#            logging.info("Decomposing group {}...".format(
#                np.argmax(z.sum(axis=0)))
#            )
#            all_init_pos = [None] * ngroups
#            all_init_pars, sub_groups =\
#                decomposeGroup(old_groups[np.argmax(z.sum(axis=0))])
#            z = expectation(star_pars, sub_groups)
#            np.save(idir+"init_subgroups.npy", sub_groups)
        np.save(idir+"membership.npy", z)

        # MAXIMISE
        #new_groups = np.zeros(old_groups.shape)
        new_groups = []

        all_samples = []
        all_lnprob = []

        for i in range(ngroups):
            logging.info("........................................")
            logging.info("          Fitting group {}".format(i))
            logging.info("........................................")
            gdir = idir + "group{}/".format(i)
            mkpath(gdir)

            best_fit, chain, lnprob = gf.fitGroup(
                xyzuvw_dict=star_pars, burnin_steps=BURNIN_STEPS,
                plot_it=True, pool=pool, convergence_tol=C_TOL,
                plot_dir=gdir, save_dir=gdir, z=z[:, i],
                init_pos=all_init_pos[i],
                init_pars=all_init_pars[i],
            )
            logging.info("Finished fit")
            new_group = syn.Group(best_fit, sphere=True, internal=True,
                                  starcount=False)
            new_groups.append(new_group)
            np.save(gdir + "best_group_fit.npy", new_group)
            np.save(gdir+'final_chain.npy', chain)
            np.save(gdir+'final_lnprob.npy', lnprob)
            all_samples.append(chain)
            all_lnprob.append(lnprob)
            all_init_pos[i] = chain[:, -1, :]

        converged = checkConvergence(old_best_fits=old_groups,
                                     new_chains=all_samples,
                                     #perc=45, # COMMENT OUT THIS LINE
                                     #          # FOR LEGIT FITS!
                                     )
        logging.info("Convergence status: {}".format(converged))
        old_old_groups = old_groups
        old_groups = new_groups

        iter_count += 1

    logging.info("CONVERGENCE COMPLETE")

    np.save(rdir+"final_groups.npy", new_groups)
    np.save(rdir+"prev_groups.npy", old_old_groups) # old grps overwritten by new grps
    np.save(rdir+"memberships.npy", z)

    # PERFORM FINAL EXPLORATION OF PARAMETER SPACE
    final_dir = rdir+"final/"
    mkpath(final_dir)

    final_z = expectation(star_pars, new_groups, z)
    np.save(final_dir+"final_membership.npy", final_z)
    final_best_fits = [None] * ngroups
    final_med_errs = [None] * ngroups

    for i in range(ngroups):
        logging.info("Characterising group {}".format(i))
        final_gdir = final_dir + "group{}/".format(i)
        mkpath(final_gdir)

        best_fit, chain, lnprob = gf.fitGroup(
            xyzuvw_dict=star_pars, burnin_steps=BURNIN_STEPS,
            plot_it=True, pool=pool, convergence_tol=C_TOL,
            plot_dir=final_gdir, save_dir=final_gdir, z=z[:, i],
            init_pos=all_init_pos[i], sampling_steps=SAMPLING_STEPS,
            # init_pars=old_groups[i],
        )
        # run with extremely large convergence tolerance to ensure it only
        # runs once
        logging.info("Finished fit")
        final_best_fits[i] = best_fit
        final_med_errs[i] = calcErrors(chain)
        np.save(gdir + "best_group_fit.npy", new_group)
        np.save(final_gdir + 'final_chain.npy', chain)
        np.save(final_gdir + 'final_lnprob.npy', lnprob)

        all_init_pos[i] = chain[:, -1, :]

    final_groups = [syn.Group(final_best_fit, sphere=True, internal=True,
                              starcount=False)
                    for final_best_fit in final_best_fits]
    np.save(final_dir+'final_groups.npy', final_groups)
    np.save(final_dir+'final_med_errs.npy', final_med_errs)

    logging.info("FINISHED CHARACTERISATION")
    #logging.info("Origin:\n{}".format(origins))
    logging.info("Best fits:\n{}".format(new_groups))
    logging.info("Memberships: \n{}".format(z))

    return final_best_fits, final_med_errs, z

