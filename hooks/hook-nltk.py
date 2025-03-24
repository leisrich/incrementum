from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# Collect all submodules
hiddenimports = collect_submodules('nltk')

# Get data files
datas = collect_data_files('nltk')
