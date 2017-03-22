#! /usr/bin/env python
from chronostar.analyser import *
import numpy as np

# Test read_sampler
samples_file = 'logs/gf_bp_2_3_10_10.pkl'
# Check read_sampler returnss some variables
assert(read_sampler(samples_file) != 0), "Read_sampler not functioning"

chain, lnprob, pos, nfree, nfixed, nsteps, npars  = read_sampler(samples_file)
assert(np.size(chain) != 0), "Chain read in as zero"
nwalkers = np.shape(chain)[0]

flatchain = np.reshape(chain, (nwalkers*nsteps,npars))
flatlnprob = np.reshape(lnprob, (nwalkers*nsteps))

assert(nfree == 3 and nfixed == 2)

realigned_samples, permute_count = realign_samples(flatchain, flatlnprob,
                                                   nfree, nfixed, npars)

print("Permutations: {} out of: {}".format(permute_count,
                                           np.shape(flatchain)[0]) )
assert(np.shape(realigned_samples)[1] == np.shape(flatchain)[1]),\
            "Difference: {}".format(np.shape(realigned_samples)[1] -\
                                    np.shape(flatchain)[1])

# Test convert_samples
converted_samples = convert_samples(realigned_samples, nfree, nfixed, npars)
# 6:10 is where the stdevs are, groups are spaced 14 parameters apart
for i in range(nfree):
    assert(np.allclose(  realigned_samples[:, 14*i+6 : 14*i+10],
                       1/converted_samples[:, 14*i+6 : 14*i+10]))

assert(np.shape(converted_samples)[1] == np.shape(flatchain)[1] + 1),\
            "Difference: {}".format(np.shape(realigned_samples)[1] -\
                                    np.shape(flatchain)[1])
assert(np.array_equal(np.sum(converted_samples[:,-(nfree+nfixed):],axis=1),
                      np.ones(nwalkers*nsteps)) )
