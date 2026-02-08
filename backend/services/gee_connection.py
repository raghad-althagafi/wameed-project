import ee

PROJECT_ID = "wameed-gee" 

class GEEConnection:
    __instance = None

    def __init__(self):
        if GEEConnection.__instance is not None:
            raise Exception("Use get_instance() to access GEEConnection")
        self._initialize()

    @staticmethod
    def get_instance():
        if GEEConnection.__instance is None:
            GEEConnection.__instance = GEEConnection()
        return GEEConnection.__instance

    def _initialize(self):
        
        print("✅ Initializing GEE (should happen once)")
        ee.Initialize(project=PROJECT_ID)
        print(f"✅ GEE initialized with project: {PROJECT_ID}")

    def get_ee(self):
        return ee
