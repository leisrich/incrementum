from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all submodules
hiddenimports = collect_submodules('scipy')

# Specifically add the missing module
hiddenimports.extend([
    'scipy._lib.array_api_compat.numpy.fft',
    'scipy._lib.array_api_compat.numpy.linalg',
    'scipy.sparse.csgraph._validation',
    'scipy.sparse.linalg.eigen.arpack',
    'scipy.sparse.linalg.isolve.iterative',
    'scipy.sparse.linalg._expm_multiply',
    'scipy.special._ellip_harm_2',
    'scipy.special._ufuncs',
])

# Get data files
datas = collect_data_files('scipy')
