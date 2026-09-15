#!/bin/bash
#source {{SOFTWARE}}/intel/oneapi/mkl/latest/env/vars.sh
#ulimit -s unlimited
#export PATH={{SOFTWARE}}/hpc_sdk/Linux_x86_64/25.3/compilers/bin:{{SOFTWARE}}/hpc_sdk/Linux_x86_64/25.3/comm_libs/mpi/bin:{{SOFTWARE}}/vasp.6.4.3/bin:${PATH}
#export LD_LIBRARY_PATH={{SOFTWARE}}/hpc_sdk/Linux_x86_64/25.3/compilers/extras/qd/lib:${LD_LIBRARY_PATH}




# NVHPC 25.8
export NO_STOP_MESSAGE=yes
ulimit -s unlimited
export NVHPC={{SOFTWARE}}/hpc_sdk
source ~/Software/intel/oneapi/mkl/latest/env/vars.sh
export NVHPC_VER=25.3
export PATH=$NVHPC/Linux_x86_64/$NVHPC_VER/compilers/bin:$PATH
export PATH=$NVHPC/Linux_x86_64/$NVHPC_VER/comm_libs/mpi/bin:$PATH
export MANPATH=$NVHPC/Linux_x86_64/$NVHPC_VER/compilers/man:$MANPATH
export LD_LIBRARY_PATH=$NVHPC/Linux_x86_64/$NVHPC_VER/compilers/extras/qd/lib:$LD_LIBRARY_PATH
export PATH={{SOFTWARE}}/vasp.6.4.3/bin:${PATH}

