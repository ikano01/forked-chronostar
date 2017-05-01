#! /usr/bin/env python
import numpy as np
import pdb
import pickle
import scipy.optimize as opt
import matplotlib.pyplot as plt
from fun import *

# Example of how to use optimiser to minimise for m
def orig_func(x):
    return 2*x

xs = np.linspace(0,10,101)
m0 = 2
def fitting_func(m, xs):
    return np.abs(np.sum(m*xs) - np.sum(orig_func(xs)))

res = opt.minimize(fitting_func, m0, (xs))
ms = np.linspace(-1,5,50)

trace_back, n_time_steps, nstars, times, orig =\
    pickle.load(open("data.pkl", 'r'))

def gaussian_fitter(pars, nstars, trace_back):
    npoints = 1000
    mu, sig = pars
    try:
        assert sig > 0
    except:
        pdb.set_trace()
    xs = np.linspace(-1000,1000,npoints)
    
    summed_stars = group_pdf(xs, trace_back)
    gaussian_fit = nstars * gaussian(xs, mu, sig)

    squared_diff = (summed_stars - gaussian_fit)**2
    return np.sum(squared_diff)

def overlap(pars, nstars, trace_back):
    mu, sig = pars
    
    total_overlap = 0
    for i in range(nstars):
        smu  = trace_back[i][0]
        ssig = trace_back[i][1]
        numer = np.exp(-(smu - mu)**2 / (2*(ssig**2 + sig**2)))
        denom = np.sqrt(2*np.pi*(ssig**2 + sig**2))
        total_overlap += np.log(numer/denom)
    # return the negative because we want to maximise the overlap
    # and optimize will minimise output
    return -total_overlap