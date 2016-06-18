%module overlap

%{
  #define SWIG_FILE_WITH_INIT
  #include "overlap.h"
%}

%include "numpy.i"

%init %{
  import_array();
%}

%apply (int DIM1, double* IN_ARRAY1) {(int len1, double* vec1), (int len2, double* vec2)}
%apply (int* ARGOUT_ARRAY1, int DIM1) {(int* rangevec, int n)}
%apply (double* ARGOUT_ARRAY1, int DIM1) {(double* rangevec, int n)}
%apply (double* IN_ARRAY3, int DIM1, int DIM2, int DIM3) \
      {(double* npyArray3D, int npyLength1D, int npyLength2D, int npyLength3D)}

%include "overlap.h"

%clear (double* npyArray3D, int npyLength1D, int npyLength2D, int npyLength3D);
