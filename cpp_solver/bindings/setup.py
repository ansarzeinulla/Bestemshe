import os
import sys
import pybind11
from setuptools import setup, Extension

# Locate pybind11 headers
pybind11_include = pybind11.get_include()

# Base directories
inc_dirs = [pybind11_include, '.']
lib_dirs = []

# Detect macOS and inject Apple Silicon Homebrew paths
if sys.platform == 'darwin':
    print("[RCL-ZERO BUILD] macOS detected. Injecting Homebrew ARM64 paths...")
    inc_dirs.append('/opt/homebrew/include')
    lib_dirs.append('/opt/homebrew/lib')

ext_modules = [
    Extension(
        'bestemshe_oracle',
        ['oracle_bridge.cpp', 'Compressor.cpp'], 
        include_dirs=inc_dirs,
        library_dirs=lib_dirs,
        language='c++',
        extra_compile_args=['-std=c++17', '-O3', '-Wall'],
        extra_link_args=['-lzstd']
    ),
]

setup(
    name='bestemshe_oracle',
    version='1.0.0',
    description='C++ HPC Oracle for Bestemshe',
    ext_modules=ext_modules,
)