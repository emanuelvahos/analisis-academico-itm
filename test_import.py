print("Iniciando importacion de api.py...")
try:
    import api
    print("Importacion exitosa.")
except Exception as e:
    import traceback
    print("Error durante la importacion:")
    traceback.print_exc()
