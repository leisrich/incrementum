from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Collect all spaCy data files
datas = collect_data_files('spacy')

# Add the spaCy model
datas += collect_data_files('en_core_web_sm')

# Collect all submodules
hiddenimports = collect_submodules('spacy')
hiddenimports += ['en_core_web_sm']
