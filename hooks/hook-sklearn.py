from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all submodules
hiddenimports = collect_submodules('sklearn')
hiddenimports.extend([
    'sklearn.utils._cython_blas',
    'sklearn.neighbors.quad_tree',
    'sklearn.neighbors.typedefs',
    'sklearn.tree._utils',
    'sklearn.utils._typedefs',
])

# Get data files
datas = collect_data_files('sklearn')
