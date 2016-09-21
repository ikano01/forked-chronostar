#!/usr/bin/env python
"""
Generates two groups of stars which follow a gaussian distribution
in one dimension at the moment but will extend to 6 dimensions.

Two gaussians are then fitted to the 'data' using MCMC. The gaussians'
properties are extracted from the sampling by taking the modes of the
parameters.

ToDo:
- investigate sofar benign divide by zero error
- introduce consitency with 'weighting' and 'fraction' naming
- get 'align' function to work for arbitrarily many groups
- get plotting to work for arbitrarily many groups
"""

from __future__ import print_function
import emcee
import numpy as np
import math
import argparse


try:
	xrange
except NameError:
	xrange = range

parser = argparse.ArgumentParser()

parser.add_argument('-s', '--nstars', dest='s', default=50,
												help='number of stars')
parser.add_argument('-f', '--fraction', dest='f', default=0.25,
												help='fraction of stars in group 1')
parser.add_argument('-w', '--nwalkers', dest='w', default=150,
												help='number of walkers')
parser.add_argument('-p', '--steps', dest='p', default=500,
												help='number of sampling steps')
parser.add_argument('-b', '--burnin', dest='b', default=500,
												help='number of burn-in steps')
parser.add_argument('-t', '--plot', dest='plot', action='store_true',
											default=False, help='display and save the plots')
parser.add_argument('-o', '--order', dest='order', action='store_true',
		  default=False, help='reorder samples by mean, only 1D, 2 groups')
parser.add_argument('-a', '--table', dest='table', action='store_true',
			default=False, help='print a table of stars with their probs')


args = parser.parse_args()

# Setting parameters
print_table = args.table # Display a pretty table with sstars and their groups
plotit = args.plot      # Will plot some pretty graphs at end
initial_help = False    # If walkers are initialised around desired result
reorder_samples = args.order # If final sample parameters are reordered
nstars = int(args.s)
nwalkers = int(args.w)
fraction = float(args.f)
ndim = 1								# number of phys. dim. being looked at, max 6
ngroups = 3
npar = ngroups*3 - 1		# Number of param. required to define a sample
												# 3 params. per group per dim mean, stdev and weight
burninsteps = args.b	  # Number of burn in steps
samplingsteps = int(args.p)	# Number of sampling steps

# Useful runtime information
print("Finding a fit for {} stars, with {} walkers for {} steps." \
	.format(nstars, nwalkers, samplingsteps))
if (plotit):
	print("Graphs will be plotted...")
if (print_table):
  print("A table will be printed...")
if (reorder_samples):
	print("Each sample will have its paramaters made to be ascending...")

# Simulating 2 groups as [ndim]-dimensional Gaussian...
# ... with hard coded mean position with pos in pc and vel in km/s
means = [[0.0], [20.0], [70.0]]

# ... and some standard deviations
stds = [[5.0], [8.0], [2.0]]

# Cumulative fraction of stars in groups
# i.e. [0, .25, 1.] means 25% of stars in group 1 and 75% in group 2
cum_fracs = [0.0, 0.1, 0.3, 1.]

# Initialising a set of [nstars] stars to have UVWXYZ as determined by 
# means and standard devs
stars = np.zeros((nstars,ndim))
for h in range(ngroups):
	for i in range(int(nstars*cum_fracs[h]), int(nstars*cum_fracs[h+1])):
		for j in range(ndim):
			stars[i][j] = np.random.normal(means[h][j], stds[h][j])

# Gaussian helper function
def gaussian_eval(x, mu, sig):
	res = 1.0/(abs(sig)*math.sqrt(2*math.pi))*np.exp(-(x-mu)**2/(2*sig**2))
	return res


# The prior, used to set bounds on the walkers
def lnprior(pars):
	mu1, sig1, w1, mu2, sig2, w2, mu3, sig3 = pars
	if		-100 < mu1 < 100 and 0.0 < sig1 < 100.0 and 5.0 < w1 < 80.0 \
		and	-100 < mu2 < 100 and 0.0 < sig2 < 100.0 and 5.0 < w2 < 80.0 \
		and	-100 < mu1 < 100 and 0.0 < sig1 < 100.0 and (w1+w2) < 95.0:
		return 0.0
	return -np.inf 

# Defining the probablility distribution to sample
# x encapsulates the mean and std of a proposed model
# i.e. x = [mu, sig]
# the likelihood of the model is the product of probabilities of each star
# given the model, that is evaluate the model gaussian for the given star
# location and product them.
# Since we need the log likelihood, we can take the log of the gaussian at
# each given star and sum them
# for each star, we want to find the value of each gaussian at that point
# and sum them. Every group bar the last has a weighting, the final group's
# weighting is determined such that the total area under the curve stays 
# constant (at the moment total area is [ngroups]
# The awkward multiplicative factor with the weighting is selected
# so that each factor is between 0 and 1.
# Currently each star entry only has one value, will eventually extrapolate
# to many stars

def lnlike(pars, stars):
	nstars = stars.size
	mu1, sig1, w1, mu2, sig2, w2, mu3, sig3 = pars
	sumlnlike = 0

	for i in range(nstars):
		gaus_sum = ( w1 * gaussian_eval(stars[i][0], mu1, sig1)
						   + w2 * gaussian_eval(stars[i][0], mu2, sig2)
							 + (100-w1-w2)*gaussian_eval(stars[i][0], mu3, sig3) )

		sumlnlike += np.log(gaus_sum)
	
	if math.isnan(sumlnlike):
		print("Got a bad'un...")
	return sumlnlike

def lnprob(pars, stars):
	lp = lnprior(pars)
	if not np.isfinite(lp):
		return -np.inf
	return lp + lnlike(pars, stars)

# Takes in [nstars][npar] array where each row is a sample and orders each
# sample's parameter sets such that the parameters representing groups are
# listed in ascending order of means
# Hardcoded for 3D
# It does this by turning each row of 8 parameters into a 3x3 matrix
#  creating a 9th element based of the 3rd and 6th, and then sorts each
#	matrix by row, before converting back into a single row array of length 9
def align_samples(samples):
	print("Samples: {}".format(samples))

	new_samples = []
	
#	weights_zip = zip(abs(samples[:,2]), abs(samples[:,5]))
#	perc1 = np.array([70/(1+x+1/y) + 10 for (x,y) in weights_zip])
#	perc2 = np.array([70/(1+1/x+y) + 10 for (x,y) in weights_zip])
	w3 = 100 - samples[:,2] - samples[:,5] 

	temp_sampl = np.array( zip(samples[:,0], samples[:,1], samples[:,2],
									samples[:,3], samples[:,4], samples[:,5],
									samples[:,6], samples[:,7], w3) )

	tnw_trans = temp_sampl.reshape(-1,3,3)
	tnw_trans.sort(axis=1)
	result = tnw_trans.reshape(-1,9)
	return tnw_trans.reshape(-1,9)

# Choose an intial set of gaussian parameters for the walkers.
# They are 'helped' by being given a similar mean and std
if (initial_help):
	# Walkers are initialised around the vicinity of the groups
	p0 = [
					[np.random.uniform(means[0][0] -5,  means[0][0]+5 ),
					 np.random.uniform(stds[0][0] -0.5, stds[0][0]+0.5),
					 np.random.uniform(2, 3),
					 np.random.uniform(means[1][0] -5,  means[1][0]+5 ),
					 np.random.uniform(stds[1][0] -0.5, stds[1][0]+0.5),
					 np.random.uniform(2, 3),
					 np.random.uniform(means[2][0] -5,  means[2][0]+5 ),
					 np.random.uniform(stds[2][0] -0.5, stds[2][0]+0.5)]
				for i in xrange(nwalkers)]
else:
	# Walkers aren't initialised around the vicinity of the groups
	# It is important that stds are not initialised to 0
	p0 = [np.random.uniform(10,60, [npar]) for i in xrange(nwalkers)]

# Initialise the sampler with the chosen specs.
sampler = emcee.EnsembleSampler(nwalkers, npar, lnprob, args=[stars])

# Run 100 steps as burn-in.
pos, prob, state = sampler.run_mcmc(p0, burninsteps)

# Reset the chain to remove the burn-in samples.
sampler.reset()

# Starting from the final position of the burn-in chain, smaple for 1000
# steps.
sampler.run_mcmc(pos, samplingsteps, rstate0=state)

# Print out the mean acceptance fraction. In general, acceptance_fraction
# has an entry for each walker so, in this case, it is a 250-dimensional
# vector.
print("Mean acceptance fraction:", np.mean(sampler.acceptance_fraction))

# Estimate the integrated autocorrelation time for th eitme series in each
# paramter.
print("Autocorrelation time:", sampler.get_autocorr_time())

# Removes the first 100 iterations of each walker and reshapes
# into an npar*X array where npar is the number of parameters required
# to specify one position, and X is the number of instances
if(reorder_samples):
	samples = np.array(align_samples(sampler.chain[:, :, :].reshape((-1, npar))))
	#samples = np.array(align_samples(sampler.chain[:, burninsteps:, :].reshape((-1, npar))))
else:
	samples = np.array(sampler.chain[:, :, :].reshape((-1, npar)))
	#samples = np.array(sampler.chain[:, burninsteps:, :].reshape((-1, npar)))

model_mu1  = np.median(samples[:,0])
model_sig1 = np.median(abs(samples[:,1]))
model_p1   = np.median(samples[:,2])
model_mu2  = np.median(samples[:,3])
model_sig2 = np.median(abs(samples[:,4]))
model_p2   = np.median(samples[:,5])
model_mu3  = np.median(samples[:,6])
model_sig3 = np.median(abs(samples[:,7]))
model_p3   = np.median(samples[:,8])


# Taking average of sampled means and sampled stds
# Can compare that to the mean and std on which the stars were
# actually formulated

#A = 100.0/(1+model_w1+1.0/model_w2)
#B = 100.0/(1+1.0/model_w1+model_w2)
#C = 100.0 - A - B

print(" ____ GROUP 1 _____ ")
print("Modelled mean: {}, modelled std: {}".format(model_mu1, model_sig1))
print("'True' mean: {}, 'true' std: {}".format(means[0][0], stds[0][0]))
print("With {}% of the stars".format(model_p1))

print(" ____ GROUP 2 _____ ")
print("Modelled mean: {}, modelled std: {}".format(model_mu2, model_sig2))
print("'True' mean: {}, 'true' std: {}".format(means[1][0], stds[1][0]))
print("With {}% of the stars".format(model_p2))

print(" ____ GROUP 3 _____ ")
print("Modelled mean: {}, modelled std: {}".format(model_mu3, model_sig3))
print("'True' mean: {}, 'true' std: {}".format(means[2][0], stds[2][0]))
print("With {}% of the stars".format(model_p3))
#
#b_samp_ind = sampler.flatlnprobability.argmax()
#print("Shape of flatlnprob: {}".format(sampler.flatlnprobability.shape))
#print("Shape of samples: {}".format(samples.shape))
#print("Index: {}".format(b_samp_ind))
#b_samp = samples[b_samp_ind]
#
#print("b_samp: {}".format(b_samp))
#
#print("with logprob of: {}".format(lnprob(b_samp, stars)))
#print("as opposed to... : {}".format(lnprob(samples[30], stars)))
#
#A = 100.0/(1+b_samp[3] + 1.0/b_samp[6])
#B = 100.0/(1+1.0/b_samp[3] + b_samp[6])
#C = 100.0 - A - B
#
#print(" ____ GROUP 1 _____ ")
#print("Modelled mean: {}, modelled std: {}".format(b_samp[0],  b_samp[1]))
#print("'True' mean: {}, 'true' std: {}".format(means[0][0], stds[0][0]))
#print("With {}% of the stars".format(A))
#
#print(" ____ GROUP 2 _____ ")
#print("Modelled mean: {}, modelled std: {}".format(b_samp[2], b_samp[3]))
#print("'True' mean: {}, 'true' std: {}".format(means[1][0], stds[1][0]))
#print("With {}% of the stars".format(B))
#
#print(" ____ GROUP 3 _____ ")
#print("Modelled mean: {}, modelled std: {}".format(b_samp[5], b_samp[6]))
#print("'True' mean: {}, 'true' std: {}".format(means[2][0], stds[2][0]))
#print("With {}% of the stars".format(C))
#

# Print a list of each star and their predicted group by percentage
# also print the success rate - the number of times a probability > 50 %
# is reported for the correct group
if(print_table):
	print("Star #\tGroup 1\tGroup 2\tGroup 3")
	success_cnt = 0.0
	for i, star in enumerate(stars):
		likelihood1 = gaussian_eval(stars[i][0], model_mu1, model_sig1)
		likelihood2 = gaussian_eval(stars[i][0], model_mu2, model_sig2)
		likelihood3 = gaussian_eval(stars[i][0], model_mu3, model_sig3)
		prob1 = likelihood1 / (likelihood1 + likelihood2 + likelihood3) * 100
		prob2 = likelihood2 / (likelihood1 + likelihood2 + likelihood3) * 100
		prob3 = likelihood3 / (likelihood1 + likelihood2 + likelihood3) * 100
		if i<nstars*cum_fracs[1] and prob1>prob2 and prob1>prob3:
			success_cnt += 1.0
		if i>=nstars*cum_fracs[1] and i < nstars*cum_fracs[2]\
				and prob1<prob2 and prob2>prob3:
			success_cnt += 1.0
		if i >= nstars*cum_fracs[2] \
				and prob1<prob3 and prob2<prob3:
			success_cnt += 1.0
		print("{}\t{:5.2f}%\t{:5.2f}%\t{:5.2f}%".format(i, prob1, prob2, prob3))
	print("Success rate of {:6.2f}%".format(success_cnt/nstars * 100))

# Finally, you can plot the porjected histograms of the samples using
# matplotlib as follows
if(plotit):
	try:
		import matplotlib.pyplot as pl
	except ImportError:
		print("Try installing matplotlib to generate some sweet plots...")
	else:
#
#		#calculating percentages from weights:
#		weights_zip = zip(abs(samples[:,2]), abs(samples[:,5]))
#		perc1 = np.array([100/(1+x+1/y) for (x,y) in weights_zip])
#		perc2 = np.array([100/(1+1/x+y) for (x,y) in weights_zip])
#		perc3 = 100 - perc1 - perc2
#
		nbins = 500 
		pl.figure(1)

		# Plotting all sampled means1
		pl.figure(1)
		pl.subplot(331)
		mus = [mu for mu in samples[:,0] if mu > -150 and mu < 150]
		pl.hist(mus, nbins)
		pl.title("Means of group 1")

		# Plotting all sampled stds1
		# Need to take the absolute since emcee samples negative sigmas
		pl.subplot(332)
		sigs = [abs(sig) for sig in samples[:,1] if abs(sig) < 50]
		pl.hist(sigs, nbins)
		pl.title("Stds of group 1")

		# Percentages of group 1
		pl.subplot(333)
		pl.hist(samples[:,2], nbins)
		pl.title("Percentages of group 1")
		
		# Means of group 2
		pl.subplot(334)
		mus = [mu for mu in samples[:,3] if mu > -150 and mu < 150]
		pl.hist(mus, nbins)
		pl.title("Means of group 2")

		# Stds of group 2
		pl.subplot(335)
		sigs = [abs(sig) for sig in samples[:,4] if abs(sig) < 50]
		pl.hist(sigs, nbins)
		pl.title("Stds of group 2")

		# Percentages of group 2
		pl.subplot(336)
		pl.hist(samples[:,5], nbins)
		pl.title("Percentages of group 2")

		# Means of group 3 
		pl.subplot(337)
		mus = [mu for mu in samples[:,6] if mu > -150 and mu < 150]
		pl.hist(mus, nbins)
		pl.title("Means of group 3")

		# Stds of group 3 
		pl.subplot(338)
		sigs = [abs(sig) for sig in samples[:,7] if abs(sig) < 50]
		pl.hist(sigs, nbins)
		pl.title("Stds of group 3")

		# Percentages of group 3
		pl.subplot(339)
		pl.hist(samples[:,8], nbins)
		pl.title("Percentages of group 3")

		pl.savefig("plots/gaussians.png")
		pl.show()
