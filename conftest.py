# Racine du repo : sa seule présence ici (sans __init__.py) fait que pytest
# ajoute Jarvis/ à sys.path, nécessaire pour que les tests importent
# `common`, `brain`, `agents` comme le fait le code applicatif.
